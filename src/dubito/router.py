"""Select verification layers from the problem class. Never compiles solver code."""

from __future__ import annotations

from dubito.classes import (
    IMPLEMENTED_LAYERS,
    PROFILES,
    ClassProfile,
    RoutedLayers,
)
from dubito.problem import ProblemSpec, as_linear_ir, as_residual_ir


def profile_for(problem_class: str) -> ClassProfile:
    if problem_class not in PROFILES:
        raise KeyError(f"unknown problem class {problem_class!r}")
    return PROFILES[problem_class]


def route(
    problem: ProblemSpec,
    *,
    check_dual: bool = True,
    check_properties: bool = True,
    n_formulations: int = 0,
) -> RoutedLayers:
    """Return which layers will run, which are off, and which are skipped."""

    profile = profile_for(problem.problem_class)
    routed = RoutedLayers(profile=profile, planned=profile.layers)
    linear = as_linear_ir(problem)
    residual = as_residual_ir(problem)

    for layer in profile.layers:
        if layer not in IMPLEMENTED_LAYERS:
            routed.mark_skipped(layer, "not-implemented")
            continue
        if layer == "code":
            routed.status["code"] = "pending"
            continue
        if layer == "exchange":
            if n_formulations < 2:
                routed.mark_skipped("exchange", "single-formulation")
            else:
                routed.status["exchange"] = "pending"
            continue
        if layer == "smt":
            if linear is None:
                routed.mark_skipped("smt", "no-linear-ir")
            else:
                routed.status["smt"] = "pending"
            continue
        if layer == "dual":
            if not check_dual:
                routed.mark_off("dual")
            elif linear is None:
                routed.mark_skipped("dual", "no-linear-ir")
            else:
                routed.status["dual"] = "pending"
            continue
        if layer == "residual":
            if residual is None:
                routed.mark_skipped("residual", "no-residual-ir")
            else:
                routed.status["residual"] = "pending"
            continue
        if layer == "properties":
            if not check_properties:
                routed.mark_off("properties")
            elif problem.properties is None:
                routed.mark_skipped("properties", "no-properties-block")
            else:
                routed.status["properties"] = "pending"
            continue
        routed.mark_skipped(layer, "not-implemented")

    return routed


def capabilities(problem_class: str) -> tuple[str, ...]:
    """Advisory backend families for independent formulations. Not a compiler."""

    return profile_for(problem_class).backends


def layer_pending(routed: RoutedLayers, layer: str) -> bool:
    return routed.status.get(layer) == "pending"
