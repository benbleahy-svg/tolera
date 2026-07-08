"""Kalk instrumentation — rewrites validated ASTs onto guarded runtime hooks.

Runs *after* validation, so user code can never contain the underscore hook
names it injects:

* ``a <op> b``      → ``_k_binop('<op>', a, b)``  (operand guards + tick)
* ``obj.attr``      → ``_k_getattr(obj, 'attr')`` (attribute allowlist)
* ``for x in it:``  → ``for x in _k_iter(it):``   (iteration caps + deadline)
"""

from __future__ import annotations

import ast

from app.services.kalk.validator import ALLOWED_BINOPS

BINOP_HOOK = "_k_binop"
GETATTR_HOOK = "_k_getattr"
ITER_HOOK = "_k_iter"


class Instrument(ast.NodeTransformer):
    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        call = ast.Call(
            func=ast.Name(id=BINOP_HOOK, ctx=ast.Load()),
            args=[
                ast.Constant(value=ALLOWED_BINOPS[type(node.op)]),
                node.left,
                node.right,
            ],
            keywords=[],
        )
        return ast.copy_location(call, node)

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        # x += y  →  x = _k_binop('+', x, y): same guards as the plain form.
        self.generic_visit(node)
        assert isinstance(node.target, ast.Name)  # enforced by the validator
        read = ast.Name(id=node.target.id, ctx=ast.Load())
        call = ast.Call(
            func=ast.Name(id=BINOP_HOOK, ctx=ast.Load()),
            args=[ast.Constant(value=ALLOWED_BINOPS[type(node.op)]), read, node.value],
            keywords=[],
        )
        assign = ast.Assign(targets=[node.target], value=call)
        return ast.copy_location(assign, node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        call = ast.Call(
            func=ast.Name(id=GETATTR_HOOK, ctx=ast.Load()),
            args=[node.value, ast.Constant(value=node.attr)],
            keywords=[],
        )
        return ast.copy_location(call, node)

    def visit_For(self, node: ast.For) -> ast.AST:
        self.generic_visit(node)
        node.iter = ast.copy_location(
            ast.Call(
                func=ast.Name(id=ITER_HOOK, ctx=ast.Load()),
                args=[node.iter],
                keywords=[],
            ),
            node.iter,
        )
        return node


def instrument(tree: ast.Module) -> ast.Module:
    new_tree = Instrument().visit(tree)
    ast.fix_missing_locations(new_tree)
    assert isinstance(new_tree, ast.Module)
    return new_tree
