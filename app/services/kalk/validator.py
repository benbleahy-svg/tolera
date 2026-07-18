"""Kalk static validation — the AST allowlist.

Everything not explicitly allowed here is rejected before execution: node
types, operators, underscore identifiers/attributes, unknown names, container
literals beyond list/tuple, and declaration calls inside blocks. Size/depth
caps run iteratively *before* the recursive walk so a pathological tree can
never blow the validator's own recursion.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from app.services.kalk.errors import KalkError
from app.services.kalk.limits import Limits

# var/table_var/… must be called at the top level of the formula
# (KALK-REFERENCE §3), never inside if/elif/else, loops, or lambdas.
DECLARATION_NAMES = frozenset(
    {"var", "table_var", "table_lookup", "variable_group", "drop_down_var"}
)

ALLOWED_BINOPS: dict[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Pow: "**",
}
ALLOWED_UNARYOPS = (ast.UAdd, ast.USub, ast.Not)
ALLOWED_CMPOPS = (
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
)

_CONST_TYPES = (int, float, str, bool, type(None))


def _err(code: str, message: str, node: ast.AST | None = None) -> KalkError:
    line = getattr(node, "lineno", None)
    col = getattr(node, "col_offset", None)
    return KalkError(code=code, message=message, line=line, col=col)


def parse_and_validate(
    source: str,
    known_names: Iterable[str],
    limits: Limits,
    *,
    allow_dict_literals: bool = False,
) -> tuple[ast.Module | None, list[KalkError]]:
    """Parse ``source`` and validate it against the Kalk grammar.

    Returns the parsed module (for the transform step) plus all errors found;
    the module is ``None`` when parsing itself failed or size caps fired.
    """
    if len(source.encode("utf-8")) > limits.max_source_bytes:
        return None, [
            KalkError(
                code="source_too_large",
                message=f"formula exceeds {limits.max_source_bytes} bytes",
            )
        ]

    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        return None, [
            KalkError(
                code="syntax",
                message=f"syntax error: {exc.msg}",
                line=exc.lineno,
                col=exc.offset,
            )
        ]
    except (RecursionError, MemoryError, ValueError, OverflowError):
        return None, [KalkError(code="syntax", message="formula could not be parsed")]

    # Iterative size/depth caps first — the recursive walk below relies on them.
    node_count = 0
    max_depth = 0
    stack: list[tuple[ast.AST, int]] = [(tree, 0)]
    while stack:
        node, depth = stack.pop()
        node_count += 1
        max_depth = max(max_depth, depth)
        if node_count > limits.max_ast_nodes or depth > limits.max_ast_depth:
            return None, [
                KalkError(
                    code="source_too_large",
                    message="formula is too large or too deeply nested",
                )
            ]
        stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))

    validator = _Validator(
        known_names=set(known_names), limits=limits, allow_dict_literals=allow_dict_literals
    )
    validator.run(tree)
    return tree, validator.errors


class _Validator:
    def __init__(
        self, known_names: set[str], limits: Limits, *, allow_dict_literals: bool = False
    ) -> None:
        self.limits = limits
        self.errors: list[KalkError] = []
        self.known = known_names
        # operation_generation only (M4.10): the KB contract passes
        # ``operation_properties`` as a dict literal — every other context
        # keeps the ban.
        self.allow_dict_literals = allow_dict_literals

    def run(self, tree: ast.Module) -> None:
        # Pass 1: module-level exec scope — any name assigned anywhere in the
        # formula is a global. (Use-before-assign surfaces as a runtime error.)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                self.known.add(node.id)
            elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                self.known.add(node.target.id)
        for stmt in tree.body:
            self._stmt(stmt, in_block=False)

    def _add(self, code: str, message: str, node: ast.AST) -> None:
        self.errors.append(_err(code, message, node))

    def _forbidden(self, node: ast.AST, what: str) -> None:
        self._add("forbidden_node", f"{what} is not allowed in Kalk", node)

    # -- statements ---------------------------------------------------------

    def _stmt(self, node: ast.stmt, in_block: bool) -> None:
        if isinstance(node, ast.Expr):
            self._expr(node.value, in_block, set())
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._name(target)
                else:
                    self._forbidden(target, "assignment to anything but a plain name")
            self._expr(node.value, in_block, set())
        elif isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name):
                self._forbidden(node.target, "assignment to anything but a plain name")
            else:
                self._name(node.target)
            if type(node.op) not in ALLOWED_BINOPS:
                self._forbidden(node, f"operator {type(node.op).__name__}")
            self._expr(node.value, in_block, set())
        elif isinstance(node, ast.If):
            self._expr(node.test, in_block, set())
            for child in node.body + node.orelse:
                self._stmt(child, in_block=True)
        elif isinstance(node, ast.For):
            if node.orelse:
                self._forbidden(node, "for/else")
            if not isinstance(node.target, ast.Name):
                self._forbidden(node.target, "loop target other than a plain name")
            else:
                self._name(node.target)
            self._expr(node.iter, in_block, set())
            for child in node.body:
                self._stmt(child, in_block=True)
        elif isinstance(node, ast.Break | ast.Continue | ast.Pass):
            pass
        else:
            self._forbidden(node, _STMT_LABELS.get(type(node), type(node).__name__))

    # -- expressions --------------------------------------------------------

    def _expr(self, node: ast.expr, in_block: bool, local: set[str]) -> None:
        if isinstance(node, ast.Constant):
            self._constant(node)
        elif isinstance(node, ast.Name):
            self._name(node, local)
        elif isinstance(node, ast.BinOp):
            if type(node.op) not in ALLOWED_BINOPS:
                self._forbidden(node, f"operator {type(node.op).__name__}")
            self._expr(node.left, in_block, local)
            self._expr(node.right, in_block, local)
        elif isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, ALLOWED_UNARYOPS):
                self._forbidden(node, f"operator {type(node.op).__name__}")
            self._expr(node.operand, in_block, local)
        elif isinstance(node, ast.BoolOp):
            for value in node.values:
                self._expr(value, in_block, local)
        elif isinstance(node, ast.Compare):
            for op in node.ops:
                if not isinstance(op, ALLOWED_CMPOPS):
                    self._forbidden(node, f"comparison {type(op).__name__}")
            self._expr(node.left, in_block, local)
            for comparator in node.comparators:
                self._expr(comparator, in_block, local)
        elif isinstance(node, ast.Call):
            self._call(node, in_block, local)
        elif isinstance(node, ast.Attribute):
            self._attribute(node, in_block, local)
        elif isinstance(node, ast.List | ast.Tuple):
            for elt in node.elts:
                if isinstance(elt, ast.Starred):
                    self._forbidden(elt, "starred expression")
                else:
                    self._expr(elt, in_block, local)
        elif isinstance(node, ast.Lambda):
            self._lambda(node, local)
        elif isinstance(node, ast.Dict) and self.allow_dict_literals:
            for key in node.keys:
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    self._forbidden(key or node, "dict key other than a string constant")
                else:
                    self._constant(key)
            for value in node.values:
                self._expr(value, in_block, local)
        else:
            self._forbidden(node, _EXPR_LABELS.get(type(node), type(node).__name__))

    def _call(self, node: ast.Call, in_block: bool, local: set[str]) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in DECLARATION_NAMES and in_block:
            self._add(
                "declaration_in_block",
                f"{node.func.id}() must be declared at the top level of the "
                "formula, not inside if/else, loops, or lambdas",
                node,
            )
        self._expr(node.func, in_block, local)
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                self._forbidden(arg, "starred argument")
            else:
                self._expr(arg, in_block, local)
        for kw in node.keywords:
            if kw.arg is None:
                self._forbidden(node, "**kwargs")
            elif kw.arg.startswith("_"):
                self._add("forbidden_name", f"keyword argument {kw.arg!r} is not allowed", node)
            self._expr(kw.value, in_block, local)

    def _attribute(self, node: ast.Attribute, in_block: bool, local: set[str]) -> None:
        if not isinstance(node.ctx, ast.Load):
            self._forbidden(node, "attribute assignment")
            return
        if node.attr.startswith("_"):
            self._add(
                "forbidden_attribute",
                f"attribute {node.attr!r} is not accessible in Kalk",
                node,
            )
        self._expr(node.value, in_block, local)

    def _lambda(self, node: ast.Lambda, local: set[str]) -> None:
        args = node.args
        if args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or args.defaults:
            self._forbidden(node, "lambda with anything but plain positional parameters")
            return
        params = {a.arg for a in args.args}
        for name in params:
            if name.startswith("_"):
                self._add("forbidden_name", f"name {name!r} is not allowed", node)
        # a lambda body is a block for declaration purposes
        self._expr(node.body, True, local | params)

    def _name(self, node: ast.Name, local: set[str] | None = None) -> None:
        if node.id.startswith("_"):
            self._add("forbidden_name", f"name {node.id!r} is not allowed", node)
            return
        if isinstance(node.ctx, ast.Load):
            known = self.known if local is None else self.known | local
            if node.id not in known:
                self._add("unknown_name", f"unknown name {node.id!r}", node)

    def _constant(self, node: ast.Constant) -> None:
        value = node.value
        if not isinstance(value, _CONST_TYPES):
            self._add(
                "invalid_constant",
                f"{type(value).__name__} literals are not allowed in Kalk",
                node,
            )
            return
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            self._add("invalid_constant", "non-finite number literal", node)
        elif isinstance(value, str) and len(value) > self.limits.max_str_len:
            self._add("invalid_constant", "string literal too long", node)
        elif (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value.bit_length() > self.limits.max_int_bits
        ):
            self._add("invalid_constant", "number literal too large", node)


_STMT_LABELS: dict[type[ast.AST], str] = {
    ast.Import: "import",
    ast.ImportFrom: "import",
    ast.FunctionDef: "def",
    ast.AsyncFunctionDef: "async def",
    ast.ClassDef: "class",
    ast.While: "while",
    ast.Try: "try/except",
    ast.TryStar: "try/except*",
    ast.Raise: "raise",
    ast.Assert: "assert",
    ast.With: "with",
    ast.AsyncWith: "async with",
    ast.AsyncFor: "async for",
    ast.Global: "global",
    ast.Nonlocal: "nonlocal",
    ast.Delete: "del",
    ast.Return: "return",
    ast.AnnAssign: "annotated assignment",
    ast.Match: "match",
}

_EXPR_LABELS: dict[type[ast.AST], str] = {
    ast.Subscript: "subscripting ([...])",
    ast.Dict: "dict literal",
    ast.Set: "set literal",
    ast.ListComp: "comprehension",
    ast.SetComp: "comprehension",
    ast.DictComp: "comprehension",
    ast.GeneratorExp: "generator expression",
    ast.JoinedStr: "f-string ({}.format is the Kalk way)",
    ast.FormattedValue: "f-string",
    ast.IfExp: "conditional expression (use if/else statements)",
    ast.NamedExpr: "walrus operator",
    ast.Await: "await",
    ast.Yield: "yield",
    ast.YieldFrom: "yield",
    ast.Starred: "starred expression",
    ast.Slice: "slicing",
}
