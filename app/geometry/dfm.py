"""DFM warning engine (M4.7) — per-family threshold evaluation.

The catalogue below is DFM-WARNINGS.md verbatim: every warning the sub-spec
pins, its threshold field(s), seed default and toggle default. Values the
sub-spec omits are NOT invented (build-plan M4.7 Decisions). Storage is
metric-native (CLAUDE.md §5: mm / deg; unitless xt multiples stay unitless);
inch defaults are converted x25.4 with the documented inch value in a comment.

v1 gating (GEOMETRY.md / DFM-WARNINGS §Implementation 5): a warning whose
feature the v1 OCCT recognizers (M4.2/M4.4-M4.6) do not emit keeps its
catalogue row flagged ``v1_supported=False`` ("v2/Spatial" in Configure) and
is never evaluated — marked, not silently dropped, because these warnings
drive Review Items and a missing feature is a missing review signal.

The evaluator is pure: (dimensions, family_scalars, features, inputs) →
``feedback: Warning[]`` where each warning is
``{type, count, threshold_used, geometry_refs, can_disable, instances}``
(INTERROGATION-ENGINE-SPEC §2; ``instances`` is additive for the viewer's
per-instance rows). Only warnings that actually fired are emitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contract import (
    FAMILY_LATHE,
    FAMILY_MILLING,
    FAMILY_SHEET_METAL,
    FAMILY_TUBE_LASER,
    Dimensions,
)

_IN = 25.4  # mm per inch — catalogue defaults documented in inches

#: |angle - 90| beyond this counts as a non-90-degree bend (float slack only;
#: the catalogue defines no tolerance — cheap-to-reverse ASSUMED default).
_ANGLE_TOL_DEG = 0.5

#: Positive-area slack for the uncut-faces check (mm²) — mirrors the
#: recognizer's own distance tolerance scale, not a shop threshold.
_AREA_TOL = 1e-6


@dataclass(frozen=True)
class WarningDef:
    """One catalogue row: family → warning → detects → threshold field(s) →
    default → enabled-by-default (DFM-WARNINGS §Implementation 1)."""

    type: str  # stable snake_case code; i18n key for the display name
    detects: str  # the catalogue "Detects" text (reference, English)
    threshold_fields: tuple[str, ...] = ()
    toggle: str | None = None  # should_detect_* key; None = not toggleable
    toggle_default: bool = True
    v1_supported: bool = False  # False = v2/Spatial: shown, never evaluated
    always_on: bool = False  # DFM-WARNINGS §Implementation 3 enforcement


# --------------------------------------------------------------------------- #
# Catalogue — DFM-WARNINGS.md tables, one WarningDef per row
# --------------------------------------------------------------------------- #
_SHEET_METAL_DEFS: tuple[WarningDef, ...] = (
    WarningDef(
        "small_cut",
        "Marked feature below the minimum markable size",
        ("smallest_cutout_size",),
        "should_detect_small_cuts",
    ),
    WarningDef(
        "drilled_hole_feedback",
        "Countersinks/counterbores/simple drilled holes counted as issues",
        (),
        "should_count_drilled_holes_as_feedback",
        toggle_default=False,
    ),
    WarningDef(
        "close_cutouts",
        "Two cut features too close",
        ("close_cutouts_threshold",),
        "should_detect_close_cutouts",
    ),
    WarningDef(
        "cutouts_close_to_edge",
        "Cut feature too near the material edge",
        ("cutout_edge_proximity",),
        "should_detect_cutouts_close_to_edge",
    ),
    WarningDef(
        "close_countersinks_bores",
        "Two countersinks/counterbores too close (edge-edge)",
        ("countersink_bore_proximity_threshold",),
        "should_detect_close_countersinks_bores",
    ),
    WarningDef(
        "countersink_bore_close_to_edge",
        "Countersink/counterbore too near the outer edge",
        ("countersink_bore_edge_proximity_threshold",),
        "should_detect_countersink_bore_close_to_edge",
    ),
    WarningDef(
        "tight_corners",
        "Corner discontinuities from connecting faces",
        (),
        "should_detect_tight_corners",
        toggle_default=False,
    ),
    WarningDef(
        "cut_near_bend",
        "Internal cut too close to a bend",
        ("cut_near_bend_threshold",),
        "should_detect_cut_near_bend",
    ),
    WarningDef(
        "tight_curl",
        "Curl outer radius too small",
        ("tight_curl_threshold",),
        "should_detect_tight_curl",
    ),
    WarningDef(
        "curl_near_bend",
        "Curl too close to a bend",
        ("curl_near_bend_threshold",),
        "should_detect_curl_near_bend",
    ),
    WarningDef(
        "tight_hem",
        "Hem diameter too small",
        ("tight_hem_threshold",),
        "should_detect_tight_hem",
    ),
    WarningDef(
        "short_hem_return",
        "Hem return flange too short",
        ("short_hem_threshold",),
        "should_detect_short_hem_return",
    ),
    WarningDef(
        "hem_near_bend",
        "Hem too close to a bend",
        ("hem_near_bend_threshold",),
        "should_detect_hem_near_bend",
    ),
    WarningDef(
        "large_bend_radius",
        "Bend radius too large (springback risk)",
        ("max_bend_radius",),
        "should_detect_large_bend_radius",
        v1_supported=True,
    ),
    WarningDef(
        "small_bend_radius",
        "Bend radius too small (cracking/orange-peel risk)",
        ("min_bend_radius",),
        "should_detect_small_bend_radius",
        v1_supported=True,
    ),
    WarningDef(
        "bend_relief_issues",
        "No / thin / shallow bend relief",
        ("thin_bend_relief_threshold", "shallow_bend_relief_threshold"),
        "should_detect_bend_relief_issues",
    ),
    WarningDef(
        "short_flange",
        "Flange too short (press marks, tolerance)",
        ("min_flange_length", "short_flange_threshold"),
        "should_detect_short_flanges",
    ),
    WarningDef(
        "short_bend",
        "Bend too short",
        ("min_flange_length",),
        "should_detect_short_bends",
    ),
    WarningDef(
        "abnormal_bend_angle",
        "Bends not at 90 degrees (excluding hems/curls)",
        (),
        "should_detect_non_ninety_bends",
        v1_supported=True,
    ),
    WarningDef(
        "different_bend_directions",
        "Bends formed in different directions in the same plane",
        (),
        "should_detect_different_bend_directions",
    ),
    WarningDef(
        "split_bends",
        "One bend formable as split sections",
        (),
        "should_detect_split_bends",
        toggle_default=False,
    ),
    WarningDef(
        "close_bends",
        "Parallel bends too close (U or Z)",
        (
            "close_bends_same_orientation_threshold",
            "close_bends_opposite_orientation_threshold",
        ),
        "should_detect_close_bends",
    ),
    WarningDef(
        "w_bending_may_be_required",
        "Deep U where shortest-leg / bend-separation exceeds the threshold",
        ("w_bending_threshold",),
        "should_detect_w_bending",
    ),
    WarningDef(
        "additional_operations_required",
        "Faces not hittable with standard/secondary tooling",
        (),
        None,
        always_on=True,
    ),
    WarningDef(
        "exceeds_press_length",
        "Bend length exceeds the press working length",
        ("press_length",),
        None,
        v1_supported=True,
    ),
    WarningDef(
        "dimensions_exceed_limits",
        "Folded or unfolded part too large",
        (
            "max_length",
            "max_width",
            "max_height",
            "max_unfolded_length",
            "max_unfolded_width",
        ),
        "should_detect_size_restrictions",
        v1_supported=True,
    ),
)

_MILLING_DEFS: tuple[WarningDef, ...] = (
    WarningDef(
        "work_envelope_size",
        "Part exceeds the machine envelope",
        ("max_part_length", "max_part_width", "max_part_height"),
        "should_detect_size_restrictions",
        v1_supported=True,
    ),
    WarningDef(
        "deep_hole",
        "Cut-depth to hole-diameter ratio too high",
        ("deep_hole_ratio_threshold",),
        "should_detect_deep_hole",
        v1_supported=True,
    ),
    WarningDef(
        "deep_cut_radiused",
        "Concave profiled face too deep for the tool diameter",
        ("deep_cut_radiused_ratio_threshold", "max_tool_diameter"),
        "should_detect_deep_cut_radiused",
    ),
    WarningDef(
        "deep_circular_pocket",
        "Circular pocket too deep for the tool diameter",
        ("deep_cut_radiused_ratio_threshold", "max_tool_diameter"),
        "should_detect_deep_circular_pocket",
        v1_supported=True,
    ),
    WarningDef(
        "deep_cut_planar",
        "Planar profiled face too deep for the tool diameter",
        ("deep_cut_planar_ratio_threshold", "max_tool_diameter"),
        "should_detect_deep_cut_planar",
        v1_supported=True,
    ),
    WarningDef(
        "small_internal_radius",
        "Internal radius below the minimum",
        ("small_internal_radius_threshold",),
        "should_detect_small_internal_radius",
    ),
    WarningDef(
        "small_hole_diameter",
        "Hole below the minimum diameter",
        ("small_hole_diameter",),
        "should_detect_small_hole_diameter",
        v1_supported=True,
    ),
    WarningDef(
        "tipped_hole",
        "Blind hole with a drill-tip bottom (harder chip clearing)",
        (),
        "should_detect_tipped_hole",
        v1_supported=True,
    ),
    WarningDef(
        "flat_bottom_hole",
        "Blind hole with a flat bottom (harder chip clearing)",
        (),
        "should_detect_flat_bottom_hole",
        v1_supported=True,
    ),
    WarningDef(
        "slanted_hole",
        "Hole entry/exit normal deviates from the axis",
        ("slanted_hole_angle_threshold",),
        "should_detect_slanted_hole",
    ),
    WarningDef(
        "partial_hole",
        "Less than 360-degree tool contact",
        (),
        "should_detect_partial_hole",
    ),
    WarningDef(
        "hole_through_cavity",
        "Coaxial holes split by a cavity",
        (),
        "should_detect_hole_through_cavity",
    ),
    WarningDef(
        "transitions",
        "Concave fillet, convex fillet, chamfer transitions",
        (),
        "should_detect_transitions",
        v1_supported=True,
    ),
    WarningDef(
        "tapered_walls",
        "Slanted plane needing surfacing",
        (),
        "should_detect_tapered_walls",
    ),
    WarningDef(
        "milling_tight_corners",
        "Internal 90-degree corners / square pockets (no round tool)",
        (),
        "should_detect_tight_corners",
    ),
    WarningDef(
        "uncut_faces",
        "Faces inaccessible to 3-axis tooling",
        (),
        None,
        v1_supported=True,
        always_on=True,
    ),
)

_LATHE_DEFS: tuple[WarningDef, ...] = (
    WarningDef(
        "work_envelope_size",
        "Part exceeds the turning envelope",
        ("max_part_length", "max_part_diameter"),
        "should_detect_size_restrictions",
        v1_supported=True,
    ),
    WarningDef(
        "bored_hole_without_relief",
        "Bore relief-distance to diameter ratio too low",
        ("bore_hole_relief_ratio",),
        "should_detect_bored_hole_without_relief",
    ),
    WarningDef(
        "slender_part",
        "Total-length to smallest-diameter ratio too high",
        ("slender_part_ratio",),
        "should_detect_slender_part",
        v1_supported=True,
    ),
    WarningDef(
        "small_internal_radius",
        "Internal radius below the minimum",
        ("small_internal_radius_threshold",),
        "should_detect_small_internal_radius",
        v1_supported=True,
    ),
    WarningDef(
        "steep_profile",
        "External face angle to the axis too steep",
        ("steep_profile_angle_threshold",),
        "should_detect_steep_profile",
    ),
    WarningDef(
        "lathe_tight_corners",
        "Non-radiused internal profiled corner (live tooling)",
        (),
        "should_detect_tight_corners",
    ),
    WarningDef(
        "off_axis_hole",
        "Hole not machinable axially or perpendicular (live tooling)",
        (),
        "should_detect_off_axis_holes",
        v1_supported=True,
    ),
    WarningDef(
        "asymmetric_cavity",
        "Cavity not symmetric about the axis (live tooling)",
        (),
        "should_detect_asymmetric_cavities",
        v1_supported=True,
    ),
)

_TUBE_LASER_DEFS: tuple[WarningDef, ...] = (
    WarningDef(
        "angled_cut",
        "Non-perpendicular cut to the tube axis (extra axis needed)",
        ("max_angled_cut_threshold",),
        "should_detect_angled_cuts",
        v1_supported=True,
    ),
    WarningDef(
        "close_cutouts",
        "Two lasered features too close",
        ("close_cutouts_threshold",),
        "should_detect_close_cutouts",
    ),
    WarningDef(
        "cutouts_close_to_edge",
        "Cutout too near an edge",
        ("cutout_edge_proximity",),
        "should_detect_cutouts_close_to_edge",
    ),
    WarningDef(
        "close_countersinks",
        "Two countersinks too close",
        ("close_countersinks_threshold",),
        "should_detect_close_countersinks",
    ),
    WarningDef(
        "countersinks_close_to_edge",
        "Countersink too near an edge",
        ("countersink_edge_proximity_threshold",),
        "should_detect_countersinks_close_to_edge",
    ),
)

#: family → the full pinned warning catalogue (v1-evaluated AND v2/Spatial).
CATALOGUE: dict[str, tuple[WarningDef, ...]] = {
    FAMILY_SHEET_METAL: _SHEET_METAL_DEFS,
    FAMILY_MILLING: _MILLING_DEFS,
    FAMILY_LATHE: _LATHE_DEFS,
    FAMILY_TUBE_LASER: _TUBE_LASER_DEFS,
}

# --------------------------------------------------------------------------- #
# Threshold + toggle defaults (DFM-WARNINGS tables, metric-native)
# --------------------------------------------------------------------------- #
#: Sheet-metal thresholds are mostly xt multiples (unit-agnostic); absolute
#: lengths are mm (inch defaults x25.4).
_SHEET_METAL_THRESHOLDS: dict[str, float] = {
    "smallest_cutout_size": 1.0,  # xt (laser & punch)
    "close_cutouts_threshold": 1.0,  # xt laser (2.0 punch — flavor-specific)
    "cutout_edge_proximity": 2.0,  # xt
    "countersink_bore_proximity_threshold": 8.0,  # xt
    "countersink_bore_edge_proximity_threshold": 4.0,  # xt
    "cut_near_bend_threshold": 3.0,  # xt + bend radius
    "tight_curl_threshold": 2.0,  # xt
    "curl_near_bend_threshold": 5.0,  # xt
    "tight_hem_threshold": 1.0,  # xt
    "short_hem_threshold": 4.0,  # xt
    "hem_near_bend_threshold": 5.0,  # xt + bend radius
    "max_bend_radius": 150.0,  # xt
    "min_bend_radius": 0.75,  # xt
    "thin_bend_relief_threshold": 1.5,  # xt
    "shallow_bend_relief_threshold": 2.0,  # xt + radius
    "min_flange_length": 4.0,  # xt
    "short_flange_threshold": 1.0,  # L:t
    "close_bends_same_orientation_threshold": 1.0,
    "close_bends_opposite_orientation_threshold": 1.0,
    "w_bending_threshold": 1.0,
    "press_length": 240.0 * _IN,  # 6096 mm (240 in)
    "max_length": 144.0 * _IN,  # 3657.6 mm (144 in)
    "max_width": 144.0 * _IN,
    "max_height": 144.0 * _IN,
    "max_unfolded_length": 144.0 * _IN,
    "max_unfolded_width": 144.0 * _IN,
}

_MILLING_THRESHOLDS: dict[str, float] = {
    "max_part_length": 64.0 * _IN,  # 1625.6 mm (64 in)
    "max_part_width": 38.0 * _IN,  # 965.2 mm (38 in)
    "max_part_height": 32.0 * _IN,  # 812.8 mm (32 in)
    "deep_hole_ratio_threshold": 8.0,
    "deep_cut_radiused_ratio_threshold": 3.0,
    "deep_cut_planar_ratio_threshold": 4.0,
    "max_tool_diameter": 0.5 * _IN,  # 12.7 mm (0.5 in)
    "small_internal_radius_threshold": _IN / 32.0,  # 0.79375 mm (1/32 in)
    "small_hole_diameter": _IN / 16.0,  # 1.5875 mm (1/16 in)
    "slanted_hole_angle_threshold": 2.0,  # deg (0.035 rad; CLAUDE.md §5: deg)
}

_LATHE_THRESHOLDS: dict[str, float] = {
    "max_part_length": 36.0 * _IN,  # 914.4 mm (36 in)
    "max_part_diameter": 18.0 * _IN,  # 457.2 mm (18 in)
    "bore_hole_relief_ratio": 0.25,
    "slender_part_ratio": 8.0,
    "small_internal_radius_threshold": 1.0,  # mm (documented metric-native)
    "steep_profile_angle_threshold": 57.3,  # deg (1 rad)
}

_TUBE_LASER_THRESHOLDS: dict[str, float] = {
    "max_angled_cut_threshold": 45.0,  # deg
    "close_cutouts_threshold": 1.0,  # dist/t
    "cutout_edge_proximity": 2.0,  # dist/t
    "close_countersinks_threshold": 8.0,  # dist/t
    "countersink_edge_proximity_threshold": 4.0,  # dist/t
}

_FAMILY_THRESHOLDS: dict[str, dict[str, float]] = {
    FAMILY_SHEET_METAL: _SHEET_METAL_THRESHOLDS,
    FAMILY_MILLING: _MILLING_THRESHOLDS,
    FAMILY_LATHE: _LATHE_THRESHOLDS,
    FAMILY_TUBE_LASER: _TUBE_LASER_THRESHOLDS,
}

#: Extra toggles that don't belong to exactly one warning row.
_EXTRA_TOGGLES: dict[str, dict[str, bool]] = {
    # Angled Cut on round tubes is separately off by default (DFM-WARNINGS
    # §Tube Laser: ``should_detect_angled_cuts_on_round_tubes`` False).
    FAMILY_TUBE_LASER: {"should_detect_angled_cuts_on_round_tubes": False},
}


def dfm_default_inputs(family: str) -> dict[str, Any]:
    """The seed-default DFM half of ``InterrogationInputs`` for a family:
    every threshold at its catalogue default + every ``should_detect_*``
    toggle at its documented default. Strategy knobs (``is_laser``, milling
    depth thresholds, lathe tool limits, …) live with the recognizers."""
    inputs: dict[str, Any] = dict(_FAMILY_THRESHOLDS.get(family, {}))
    for wdef in CATALOGUE.get(family, ()):
        if wdef.toggle is not None:
            inputs[wdef.toggle] = wdef.toggle_default
    inputs.update(_EXTRA_TOGGLES.get(family, {}))
    return inputs


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def _props(features: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [f.get("properties", {}) for f in features if f.get("name") == name]


class _Emitter:
    """Collects fired warnings for one family, applying toggle gating and the
    v1-supported gate from the catalogue."""

    def __init__(self, family: str, inputs: dict[str, Any]) -> None:
        self._defs = {d.type: d for d in CATALOGUE.get(family, ())}
        self._inputs = inputs
        self.feedback: list[dict[str, Any]] = []

    def enabled(self, wtype: str) -> bool:
        wdef = self._defs[wtype]
        if not wdef.v1_supported:
            return False
        if wdef.toggle is None:
            return True
        return bool(self._inputs.get(wdef.toggle, wdef.toggle_default))

    def threshold(self, name: str, family_defaults: dict[str, float]) -> float:
        value = self._inputs.get(name, family_defaults[name])
        return float(value)

    def emit(
        self,
        wtype: str,
        instances: list[dict[str, Any]],
        threshold_used: dict[str, float],
    ) -> None:
        if not instances:
            return
        wdef = self._defs[wtype]
        self.feedback.append(
            {
                "type": wtype,
                "count": len(instances),
                "threshold_used": threshold_used,
                # face ids arrive with the server-mesh export (M4.1+ viewer
                # seam); instances carry the auditable numbers meanwhile.
                "geometry_refs": [],
                "can_disable": wdef.toggle is not None,
                "instances": instances,
            }
        )


def _evaluate_sheet_metal(
    em: _Emitter,
    dims: Dimensions,
    scalars: dict[str, Any],
    features: list[dict[str, Any]],
    inputs: dict[str, Any],
) -> None:
    thickness = scalars.get("thickness")
    if not isinstance(thickness, int | float) or thickness <= 0:
        return  # unrecognized body: no xt basis, never a fabricated warning
    t = float(thickness)
    th = _SHEET_METAL_THRESHOLDS
    bends = _props(features, "bend")

    if em.enabled("small_bend_radius"):
        limit = em.threshold("min_bend_radius", th)
        hits = [b for b in bends if b["radius"] < limit * t]
        em.emit(
            "small_bend_radius",
            [{"radius": b["radius"], "angle": b["angle"], "length": b["length"]} for b in hits],
            {"min_bend_radius": limit},
        )
    if em.enabled("large_bend_radius"):
        limit = em.threshold("max_bend_radius", th)
        hits = [b for b in bends if b["radius"] > limit * t]
        em.emit(
            "large_bend_radius",
            [{"radius": b["radius"], "angle": b["angle"], "length": b["length"]} for b in hits],
            {"max_bend_radius": limit},
        )
    if em.enabled("abnormal_bend_angle"):
        # The catalogue excludes hems/curls; v1 relies on the recognizer's
        # bend-sweep cap already dropping them (occt _MAX_BEND_SWEEP_DEG) —
        # revisit when hem/curl features land (they are v2 rows above).
        hits = [b for b in bends if abs(b["angle"] - 90.0) > _ANGLE_TOL_DEG]
        em.emit(
            "abnormal_bend_angle",
            [{"angle": b["angle"], "radius": b["radius"]} for b in hits],
            {},
        )
    if em.enabled("exceeds_press_length"):
        limit = em.threshold("press_length", th)
        hits = [b for b in bends if b["length"] > limit]
        em.emit(
            "exceeds_press_length",
            [{"length": b["length"]} for b in hits],
            {"press_length": limit},
        )
    if em.enabled("dimensions_exceed_limits"):
        used: dict[str, float] = {}
        instances: list[dict[str, Any]] = []
        folded = {
            "max_length": dims.max_dim,
            "max_width": dims.med_dim,
            "max_height": dims.min_dim,
        }
        for field, value in folded.items():
            limit = em.threshold(field, th)
            if value > limit:
                used[field] = limit
                instances.append({"dimension": field, "value": value})
        unfolded = {
            "max_unfolded_length": scalars.get("size_x"),
            "max_unfolded_width": scalars.get("size_y"),
        }
        for field, uvalue in unfolded.items():
            if not isinstance(uvalue, int | float):
                continue
            limit = em.threshold(field, th)
            if uvalue > limit:
                used[field] = limit
                instances.append({"dimension": field, "value": float(uvalue)})
        em.emit("dimensions_exceed_limits", instances, used)


def _evaluate_milling(
    em: _Emitter,
    dims: Dimensions,
    scalars: dict[str, Any],
    features: list[dict[str, Any]],
    inputs: dict[str, Any],
) -> None:
    th = _MILLING_THRESHOLDS
    holes = _props(features, "hole")
    circular_pockets = _props(features, "circular_pocket")
    pockets = _props(features, "pocket")

    if em.enabled("work_envelope_size"):
        used: dict[str, float] = {}
        instances: list[dict[str, Any]] = []
        for field, value in (
            ("max_part_length", dims.max_dim),
            ("max_part_width", dims.med_dim),
            ("max_part_height", dims.min_dim),
        ):
            limit = em.threshold(field, th)
            used[field] = limit
            if value > limit:
                instances.append({"dimension": field, "value": value})
        em.emit("work_envelope_size", instances, used)
    if em.enabled("deep_hole"):
        limit = em.threshold("deep_hole_ratio_threshold", th)
        hits = [h for h in holes if h["diameter"] > 0 and h["depth"] / h["diameter"] > limit]
        em.emit(
            "deep_hole",
            [
                {
                    "depth": h["depth"],
                    "diameter": h["diameter"],
                    "ratio": h["depth"] / h["diameter"],
                }
                for h in hits
            ],
            {"deep_hole_ratio_threshold": limit},
        )
    if em.enabled("small_hole_diameter"):
        limit = em.threshold("small_hole_diameter", th)
        hits = [h for h in holes if h["diameter"] < limit]
        em.emit(
            "small_hole_diameter",
            [{"diameter": h["diameter"], "depth": h["depth"]} for h in hits],
            {"small_hole_diameter": limit},
        )
    if em.enabled("tipped_hole"):
        hits = [h for h in holes if h["bottom_type"] == "tipped"]
        em.emit(
            "tipped_hole",
            [{"diameter": h["diameter"], "depth": h["depth"]} for h in hits],
            {},
        )
    if em.enabled("flat_bottom_hole"):
        hits = [h for h in holes if h["bottom_type"] == "flat"]
        em.emit(
            "flat_bottom_hole",
            [{"diameter": h["diameter"], "depth": h["depth"]} for h in hits],
            {},
        )
    if em.enabled("deep_circular_pocket"):
        ratio = em.threshold("deep_cut_radiused_ratio_threshold", th)
        tool = em.threshold("max_tool_diameter", th)
        hits = [p for p in circular_pockets if tool > 0 and p["depth"] / tool > ratio]
        em.emit(
            "deep_circular_pocket",
            [{"depth": p["depth"], "diameter": p["diameter"]} for p in hits],
            {"deep_cut_radiused_ratio_threshold": ratio, "max_tool_diameter": tool},
        )
    if em.enabled("deep_cut_planar"):
        ratio = em.threshold("deep_cut_planar_ratio_threshold", th)
        tool = em.threshold("max_tool_diameter", th)
        hits = [p for p in pockets if tool > 0 and p["max_depth"] / tool > ratio]
        em.emit(
            "deep_cut_planar",
            [{"depth": p["max_depth"], "area": p["area"]} for p in hits],
            {"deep_cut_planar_ratio_threshold": ratio, "max_tool_diameter": tool},
        )
    if em.enabled("transitions"):
        hits = [p for p in pockets if p.get("has_transition")]
        em.emit(
            "transitions",
            [{"area": p["area"], "depth": p["max_depth"]} for p in hits],
            {},
        )
    # Always-on (DFM-WARNINGS §Implementation 3): faces no 3-axis direction
    # reaches — the recognizer's uncovered-area accounting (M4.4).
    uncovered = scalars.get("uncovered_area")
    if isinstance(uncovered, int | float) and uncovered > _AREA_TOL:
        em.emit("uncut_faces", [{"area": float(uncovered)}], {})


def _evaluate_lathe(
    em: _Emitter,
    dims: Dimensions,
    scalars: dict[str, Any],
    features: list[dict[str, Any]],
    inputs: dict[str, Any],
) -> None:
    th = _LATHE_THRESHOLDS
    stock_length = scalars.get("stock_length")
    stock_radius = scalars.get("stock_radius")
    if not isinstance(stock_length, int | float) or not isinstance(stock_radius, int | float):
        return  # not a turnable body — recognizer emitted nothing

    if em.enabled("work_envelope_size"):
        max_len = em.threshold("max_part_length", th)
        max_dia = em.threshold("max_part_diameter", th)
        instances = []
        if stock_length > max_len:
            instances.append({"dimension": "max_part_length", "value": float(stock_length)})
        if 2.0 * stock_radius > max_dia:
            instances.append({"dimension": "max_part_diameter", "value": 2.0 * stock_radius})
        em.emit(
            "work_envelope_size",
            instances,
            {"max_part_length": max_len, "max_part_diameter": max_dia},
        )
    if em.enabled("slender_part"):
        limit = em.threshold("slender_part_ratio", th)
        # smallest turned diameter — exposed by the recognizer (M4.7); the
        # catalogue ratio is total-length / smallest-diameter.
        min_r = scalars.get("min_external_radius")
        if isinstance(min_r, int | float) and min_r > 0:
            ratio = float(stock_length) / (2.0 * float(min_r))
            if ratio > limit:
                em.emit(
                    "slender_part",
                    [{"length": float(stock_length), "min_diameter": 2.0 * float(min_r)}],
                    {"slender_part_ratio": limit},
                )
    if em.enabled("small_internal_radius"):
        limit = em.threshold("small_internal_radius_threshold", th)
        hits = [
            c
            for c in _props(features, "internal_cut")
            if isinstance(c.get("radius"), int | float) and c["radius"] < limit
        ]
        em.emit(
            "small_internal_radius",
            [{"radius": c["radius"], "depth": c.get("depth")} for c in hits],
            {"small_internal_radius_threshold": limit},
        )
    if em.enabled("off_axis_hole"):
        em.emit("off_axis_hole", _props(features, "off_axis_hole"), {})
    if em.enabled("asymmetric_cavity"):
        em.emit("asymmetric_cavity", _props(features, "asymmetric_cavity"), {})


def _evaluate_tube_laser(
    em: _Emitter,
    dims: Dimensions,
    scalars: dict[str, Any],
    features: list[dict[str, Any]],
    inputs: dict[str, Any],
) -> None:
    th = _TUBE_LASER_THRESHOLDS
    if em.enabled("angled_cut"):
        on_round = bool(inputs.get("should_detect_angled_cuts_on_round_tubes", False))
        if scalars.get("stock_type") != "round" or on_round:
            limit = em.threshold("max_angled_cut_threshold", th)
            cuts = _props(features, "angled_cut")
            em.emit(
                "angled_cut",
                [
                    {
                        "angle": c["angle"],
                        "cut_length": c.get("cut_length"),
                        "machining_required": c.get("machining_required", False),
                    }
                    for c in cuts
                ],
                {"max_angled_cut_threshold": limit},
            )


def evaluate_feedback(
    family: str | None,
    dimensions: Dimensions,
    family_scalars: dict[str, Any],
    features: list[dict[str, Any]],
    inputs: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Evaluate one body's recognized geometry against the resolved
    ``InterrogationInputs`` → the fired ``Warning[]`` (empty for families
    without a catalogue, bodies the recognizer rejected, and clean parts)."""
    if family not in CATALOGUE:
        return []
    resolved = {**dfm_default_inputs(family), **(inputs or {})}
    em = _Emitter(family, resolved)
    if family == FAMILY_SHEET_METAL:
        _evaluate_sheet_metal(em, dimensions, family_scalars, features, resolved)
    elif family == FAMILY_MILLING:
        _evaluate_milling(em, dimensions, family_scalars, features, resolved)
    elif family == FAMILY_LATHE:
        _evaluate_lathe(em, dimensions, family_scalars, features, resolved)
    elif family == FAMILY_TUBE_LASER:
        _evaluate_tube_laser(em, dimensions, family_scalars, features, resolved)
    return em.feedback
