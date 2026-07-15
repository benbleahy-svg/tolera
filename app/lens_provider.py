"""Lens model providers (M3.1 — spec ``#lens-models``: configurable, never hard-coded).

v1 production provider = the **Anthropic Claude API** under a zero-data-retention
agreement (spec ``#ai-settings``); the pinned vision model + versioned prompts
come from :class:`~app.config.Settings`. Requests carry ``inference_geo`` so
inference stays in the configured DPA region (DACH delta — the *default* path;
export-controlled files never reach ANY provider, enforced upstream in
:mod:`app.lens_extract`).

``register``/``resolve`` mirror :mod:`app.task_resources`: tests (and, later,
alternative deployments) register a provider instance; a worker process falls
back to building the settings-configured one.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from anthropic import AsyncAnthropic
from pydantic import ValidationError

from .config import Settings, get_settings
from .lens import PROMPT_VERSION, LensProvider, RawFinding, RawLineItem

logger = logging.getLogger("app.lens_provider")

#: The Claude API caps requests at 32 MB; base64 expands the PDF by 4/3, and
#: prompt/schema/JSON framing rides on top — 20 MiB raw (~26.7 MiB encoded)
#: leaves real headroom under the cap.
MAX_PROVIDER_PDF_BYTES = 20 * 1024 * 1024


class LensProviderError(Exception):
    """A deterministic model outcome (refusal, truncation, malformed JSON) —
    retrying is waste, so the task maps this to a bound failure dict instead of
    letting ``BaseTask``'s infra retries burn identical API calls."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_registered: LensProvider | None = None


def register(provider: LensProvider | None) -> None:
    """Install (or clear) the process-wide provider — tests and ``create_app``."""
    global _registered
    _registered = provider


def resolve() -> LensProvider:
    """The provider for the current process (registered, else from settings)."""
    if _registered is not None:
        return _registered
    return make_provider(get_settings())


def make_provider(settings: Settings) -> LensProvider:
    """Build the settings-configured provider (the configurability seam)."""
    if settings.lens_provider != "anthropic":
        raise RuntimeError(f"Unknown LENS_PROVIDER {settings.lens_provider!r}")
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set — live Lens extraction needs it "
            "(tests register a fake provider instead)."
        )
    return AnthropicLensProvider(
        api_key=settings.anthropic_api_key,
        model=settings.lens_model,
        inference_geo=settings.lens_inference_geo or None,
    )


# --------------------------------------------------------------------------- #
# Versioned prompts (PROMPT_VERSION in app.lens) — German-title-block aware,
# ISO GPS GD&T, mm-native (spec #lens-models DACH notes).
# --------------------------------------------------------------------------- #
_NEVER_HALLUCINATE = (
    "Report ONLY values that are literally present in the document. Never invent, "
    "infer, or complete a value that is not printed — omitting a field is always "
    "correct; inventing one is never correct. `raw_text` must be the verbatim "
    "source snippet the finding came from."
)

_CLASSIFY_PROMPT = (
    f"[{PROMPT_VERSION}] For each page of the attached document, decide whether it "
    "is an engineering drawing / technical print (title block, views, dimensions) "
    "as opposed to e.g. a cover letter, terms, or a photo. Title blocks are often "
    "German (Zeichnung, Werkstoff, Maßstab, Blatt). Answer as JSON."
)

_QUOTE_SETUP_PROMPT = (
    f"[{PROMPT_VERSION}] Extract quote-setup fields from the attached document as "
    "findings: part_number, revision, description, drawing_number, document_units "
    "(mm or in), tables, bom_tables, export_controlled keywords, pii. Title blocks "
    "may be German (Zeichnungsnummer, Benennung, Werkstoff, Maßstab, Blatt, Rev). "
    f"{_NEVER_HALLUCINATE}"
)

_REQUIREMENTS_PROMPT = (
    f"[{PROMPT_VERSION}] Extract manufacturing requirements from page {{page_no}} of "
    "the attached print as findings across the taxonomy: requirements "
    "(process_keywords, material with DIN/EN Werkstoffnummer, specifications, "
    "global_tolerances such as ISO 2768, flag_notes), features (hole, thread, "
    "countersink, counterbore, control_frame with ISO GPS symbols, datum, chamfer, "
    "surface_finish, bend_lines, welds), dimensions (length/diameter/radius/angle "
    "with value, tolerance kind unilateral|bilateral|limit, role basic|"
    "critical_to_quality|reference), and regions (title_block, notes_list, view "
    "captions). Units default to the document's units (mm unless stated). "
    "Bounding boxes are unrotated pdf-unit page coordinates. "
    f"{_NEVER_HALLUCINATE}"
)

_FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "quote_setup",
                            "requirements",
                            "features",
                            "dimensions",
                            "regions",
                        ],
                    },
                    "type": {"type": "string"},
                    "raw_text": {"type": ["string", "null"]},
                    "value": {"type": ["string", "null"]},
                    "normalized_value": {"type": ["string", "null"]},
                    "units": {"type": ["string", "null"]},
                    "tolerance": {
                        "type": ["object", "null"],
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": ["unilateral", "bilateral", "limit"],
                            },
                            "upper": {"type": ["string", "null"]},
                            "lower": {"type": ["string", "null"]},
                        },
                        "required": ["kind", "upper", "lower"],
                        "additionalProperties": False,
                    },
                    "role": {
                        "type": ["string", "null"],
                        "enum": ["basic", "critical_to_quality", "reference", None],
                    },
                    "gdt": {
                        "type": ["object", "null"],
                        "properties": {
                            "symbol": {"type": "string"},
                            "datum_refs": {"type": "array", "items": {"type": "string"}},
                            "material_condition": {"type": ["string", "null"]},
                        },
                        "required": ["symbol", "datum_refs", "material_condition"],
                        "additionalProperties": False,
                    },
                    "bbox": {
                        "type": ["object", "null"],
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                        },
                        "required": ["x", "y", "width", "height"],
                        "additionalProperties": False,
                    },
                    "confidence": {"type": "number"},
                    "page": {"type": ["integer", "null"]},
                },
                "required": [
                    "category",
                    "type",
                    "raw_text",
                    "value",
                    "normalized_value",
                    "units",
                    "tolerance",
                    "role",
                    "gdt",
                    "bbox",
                    "confidence",
                    "page",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}

_CLASSIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"is_print": {"type": "array", "items": {"type": "boolean"}}},
    "required": ["is_print"],
    "additionalProperties": False,
}

# ---- Email-body parts-list parse (M3.4 — AI-LENS §3, text LLM, no vision) ---- #
#: Version stamp for the parts-list prompt (the M3 pin-prompts convention).
#: Lives here (not app.email_parts) to keep the import direction one-way.
PARTS_PROMPT_VERSION = "email-parts-v1"

_PARTS_LIST_PROMPT = (
    "[{version}] Below are the plain-text body of a customer RFQ email "
    "(German or English) and the filenames of its attachments. Extract the "
    "requested parts list. For each requested line item report: part_number "
    "(verbatim, as written in the body or as it appears in an attachment "
    "filename), revision (only if stated), description (only if stated "
    "verbatim), quantities (every requested lot size, as integers), "
    "requested_date_raw (the verbatim date text, if a delivery date is "
    "stated) and requested_date (its ISO 8601 yyyy-mm-dd form), and a "
    "confidence between 0 and 1. German RFQs often write lot sizes as "
    "'Losgroessen 1, 5, 20 Stk.' and dates as dd.mm.yyyy. "
    f"{_NEVER_HALLUCINATE}"
).format(version=PARTS_PROMPT_VERSION)

_PARTS_LIST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "part_number": {"type": "string"},
                    "revision": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "quantities": {"type": "array", "items": {"type": "integer"}},
                    "requested_date": {"type": ["string", "null"]},
                    "requested_date_raw": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "part_number",
                    "revision",
                    "description",
                    "quantities",
                    "requested_date",
                    "requested_date_raw",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


class AnthropicLensProvider:
    """Vision-LLM extraction on the Claude API (structured JSON outputs).

    Determinism posture per the M3 test plan: pinned model + versioned prompts.
    (The plan's "temperature 0" predates the current API — sampling parameters
    are rejected on the pinned model generation, so prompts/model pinning carry
    the reproducibility; M3.11 gates quality on thresholds, never exact-match.)
    """

    def __init__(self, *, api_key: str, model: str, inference_geo: str | None) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._inference_geo = inference_geo

    async def _ask(self, prompt: str, pdf: bytes, schema: dict[str, Any]) -> dict[str, Any]:
        if len(pdf) > MAX_PROVIDER_PDF_BYTES:
            # 200 MB uploads are allowed platform-wide, but the provider's
            # request ceiling is 32 MB and base64 expands by 4/3 — cap BEFORE
            # encoding so a big drawing pack can't balloon worker memory.
            raise LensProviderError("provider_document_too_large")
        return await self._complete(
            [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(pdf).decode("ascii"),
                    },
                },
                {"type": "text", "text": prompt},
            ],
            schema,
        )

    async def _complete(
        self, content: list[dict[str, Any]], schema: dict[str, Any]
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 16000,
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
            "messages": [{"role": "user", "content": content}],
        }
        if self._inference_geo:
            params["inference_geo"] = self._inference_geo
        response = await self._client.messages.create(**params)
        # Deterministic non-answers must not hit infra retries (ship-review):
        # a refusal has empty content; max_tokens means truncated (broken) JSON.
        if response.stop_reason == "refusal":
            raise LensProviderError("provider_refusal")
        if response.stop_reason == "max_tokens":
            raise LensProviderError("provider_truncated")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise LensProviderError("provider_empty_response")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LensProviderError("provider_invalid_json") from exc
        if not isinstance(payload, dict):
            # json.loads can yield a list/scalar — same deterministic bucket.
            raise LensProviderError("provider_invalid_json")
        return payload

    def _parse_findings(self, payload: dict[str, Any]) -> list[RawFinding]:
        findings: list[RawFinding] = []
        invalid = 0
        for item in payload.get("findings", []):
            try:
                findings.append(RawFinding.model_validate(item))
            except ValidationError:
                invalid += 1
        if invalid:
            logger.warning("lens_provider_invalid_findings", extra={"invalid": invalid})
        return findings

    async def classify_print_pages(self, pdf: bytes, page_texts: list[str]) -> list[bool]:
        payload = await self._ask(_CLASSIFY_PROMPT, pdf, _CLASSIFY_SCHEMA)
        flags = [bool(f) for f in payload.get("is_print", [])]
        # Pad/trim defensively — the guard against a miscounting model.
        flags = flags[: len(page_texts)]
        flags += [False] * (len(page_texts) - len(flags))
        return flags

    async def extract_quote_setup(self, pdf: bytes, page_texts: list[str]) -> list[RawFinding]:
        payload = await self._ask(_QUOTE_SETUP_PROMPT, pdf, _FINDINGS_SCHEMA)
        return self._parse_findings(payload)

    async def extract_requirements(
        self, pdf: bytes, page_no: int, page_text: str
    ) -> list[RawFinding]:
        prompt = _REQUIREMENTS_PROMPT.format(page_no=page_no)
        payload = await self._ask(prompt, pdf, _FINDINGS_SCHEMA)
        findings = self._parse_findings(payload)
        for finding in findings:
            finding.page = page_no
        return findings

    async def parse_email_parts_list(
        self, body_text: str, attachment_filenames: list[str]
    ) -> list[RawLineItem]:
        """M3.4 — text-LLM parts-list parse of an RFQ email body (AI-LENS §3).
        Same EU ``inference_geo`` routing as every Lens call; the guard in
        :mod:`app.email_parts` enforces never-hallucinate on the result."""
        filenames = "\n".join(attachment_filenames) or "(none)"
        payload = await self._complete(
            [
                {
                    "type": "text",
                    "text": (
                        f"{_PARTS_LIST_PROMPT}\n\nATTACHMENT FILENAMES:\n{filenames}"
                        f"\n\nEMAIL BODY:\n{body_text}"
                    ),
                }
            ],
            _PARTS_LIST_SCHEMA,
        )
        items: list[RawLineItem] = []
        invalid = 0
        for item in payload.get("items", []):
            try:
                items.append(RawLineItem.model_validate(item))
            except ValidationError:
                invalid += 1
        if invalid:
            logger.warning("lens_provider_invalid_line_items", extra={"invalid": invalid})
        return items
