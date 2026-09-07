#!/usr/bin/env python3
"""Validate candidate budget defaults and monotonic mode ceilings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from scripts.json_strict import loads as strict_json_loads
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads


ROOT_FIELDS = {"schema_version", "approval_status", "precedence", "classes", "risk_tiers", "stop_conditions"}
PRECEDENCE = ["live_runtime_limit", "user_approved_limit", "risk_specific_limit", "class_default"]
CLASS_FIELDS = {
    "max_subagents",
    "max_retries_per_task",
    "max_tokens",
    "max_elapsed_seconds",
    "max_cost_usd",
    "verification_reserve",
}
RISK_FIELDS = {"independent_verifier_required"}


def validate(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        return ["budget root/schema_version is invalid"]
    if set(data) != ROOT_FIELDS:
        errors.append(f"budget fields must be exactly {sorted(ROOT_FIELDS)}")
    if data.get("approval_status") not in {"candidate-defaults", "product-owner-approved"}:
        errors.append("approval_status must be explicit")
    if data.get("precedence") != PRECEDENCE:
        errors.append(f"precedence must be exactly {PRECEDENCE}")
    classes = data.get("classes")
    names = ("direct", "scout-assisted", "multi-workstream")
    if not isinstance(classes, dict) or set(classes) != set(names):
        return [*errors, "classes must define exactly direct, scout-assisted, and multi-workstream"]
    for name in names:
        item = classes[name]
        if not isinstance(item, dict):
            errors.append(f"{name} must be an object")
            continue
        expected_fields = CLASS_FIELDS | ({"max_active_fraction"} if name == "multi-workstream" else set())
        if set(item) != expected_fields:
            errors.append(f"{name} fields must be exactly {sorted(expected_fields)}")
        for field in ("max_subagents", "max_retries_per_task", "max_tokens", "max_elapsed_seconds", "verification_reserve"):
            value = item.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"{name}.{field} must be a non-negative integer")
        cost = item.get("max_cost_usd")
        if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0:
            errors.append(f"{name}.max_cost_usd must be a non-negative number")
        if isinstance(item.get("max_subagents"), int) and item["max_subagents"] > 4:
            errors.append(f"{name}.max_subagents must not exceed 4")
        if isinstance(item.get("max_retries_per_task"), int) and item["max_retries_per_task"] > 2:
            errors.append(f"{name}.max_retries_per_task must not exceed 2")
        reserve = item.get("verification_reserve")
        subagents = item.get("max_subagents")
        if isinstance(reserve, int) and isinstance(subagents, int) and reserve > subagents:
            errors.append(f"{name}.verification_reserve must not exceed max_subagents")
    active_fraction = classes.get("multi-workstream", {}).get("max_active_fraction") if isinstance(classes.get("multi-workstream"), dict) else None
    if not isinstance(active_fraction, (int, float)) or isinstance(active_fraction, bool) or not 0 < active_fraction <= 1:
        errors.append("multi-workstream.max_active_fraction must be a number in (0, 1]")
    if isinstance(classes.get("direct"), dict) and classes["direct"].get("max_subagents") != 0:
        errors.append("direct.max_subagents must equal zero")
    for field in ("max_subagents", "max_retries_per_task", "max_tokens", "max_elapsed_seconds", "max_cost_usd", "verification_reserve"):
        values = [classes[name].get(field) for name in names if isinstance(classes.get(name), dict)]
        if len(values) == 3 and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values) and not (values[0] <= values[1] <= values[2]):
            errors.append(f"{field} must be monotonic across modes")
    risk_tiers = data.get("risk_tiers")
    if not isinstance(risk_tiers, dict) or set(risk_tiers) != {"R0", "R1", "R2", "R3"}:
        errors.append("risk_tiers must define exactly R0, R1, R2, and R3")
    else:
        for tier, item in risk_tiers.items():
            expected_fields = RISK_FIELDS | ({"explicit_authority_required"} if tier == "R3" else set())
            if not isinstance(item, dict) or set(item) != expected_fields:
                errors.append(f"{tier} fields must be exactly {sorted(expected_fields)}")
                continue
            if not isinstance(item.get("independent_verifier_required"), bool):
                errors.append(f"{tier}.independent_verifier_required must be boolean")
        if isinstance(risk_tiers.get("R2"), dict) and risk_tiers["R2"].get("independent_verifier_required") is not True:
            errors.append("R2 must require an independent verifier")
        if isinstance(risk_tiers.get("R3"), dict):
            if risk_tiers["R3"].get("independent_verifier_required") is not True:
                errors.append("R3 must require an independent verifier")
            if risk_tiers["R3"].get("explicit_authority_required") is not True:
                errors.append("R3 must require explicit authority")
    stop_conditions = data.get("stop_conditions")
    if (
        not isinstance(stop_conditions, list)
        or len(stop_conditions) < 5
        or not all(isinstance(item, str) and item.strip() for item in stop_conditions)
        or len(stop_conditions) != len(set(stop_conditions))
    ):
        errors.append("stop_conditions must contain at least five unique non-empty strings")
    return errors


def main() -> int:
    path = Path(__file__).resolve().parents[1] / "config" / "budgets.json"
    try:
        errors = validate(strict_json_loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"validate_budgets: FAIL ({exc})")
        return 1
    for error in errors:
        print(f"ERROR {error}")
    print(f"validate_budgets: {'PASS' if not errors else 'FAIL'} ({len(errors)} errors)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
