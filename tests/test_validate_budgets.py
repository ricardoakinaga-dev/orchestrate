from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.validate_budgets import validate


ROOT = Path(__file__).resolve().parents[1]


class ValidateBudgetsTests(unittest.TestCase):
    def test_repository_budgets_pass(self) -> None:
        data = json.loads((ROOT / "config" / "budgets.json").read_text(encoding="utf-8"))
        self.assertEqual([], validate(data))

    def test_direct_cannot_spawn(self) -> None:
        data = json.loads((ROOT / "config" / "budgets.json").read_text(encoding="utf-8"))
        data["classes"]["direct"]["max_subagents"] = 1
        self.assertIn("direct.max_subagents must equal zero", validate(data))

    def test_malformed_active_fraction_and_empty_stops_are_rejected(self) -> None:
        data = json.loads((ROOT / "config" / "budgets.json").read_text(encoding="utf-8"))
        data["classes"]["multi-workstream"]["max_active_fraction"] = "invalid"
        data["stop_conditions"] = []
        errors = validate(data)
        self.assertTrue(any("max_active_fraction" in error for error in errors))
        self.assertTrue(any("stop_conditions" in error for error in errors))

    def test_unknown_fields_and_unsafe_risk_tiers_are_rejected(self) -> None:
        data = json.loads((ROOT / "config" / "budgets.json").read_text(encoding="utf-8"))
        data["unexpected"] = True
        data["risk_tiers"]["R3"]["explicit_authority_required"] = False
        errors = validate(data)
        self.assertTrue(any("budget fields" in error for error in errors))
        self.assertIn("R3 must require explicit authority", errors)


if __name__ == "__main__":
    unittest.main()
