from __future__ import annotations

import unittest

from scripts.check_eval_leakage import find_leaks, similarity


class EvalLeakageTests(unittest.TestCase):
    def test_identical_prompt_is_detected(self) -> None:
        left = [{"id": "A", "prompt": "Review the API contract now"}]
        right = [{"id": "B", "prompt": "Review the API contract now"}]
        self.assertEqual(1, len(find_leaks(left, right, 0.8)))

    def test_distinct_prompts_do_not_match(self) -> None:
        self.assertLess(similarity("rename one variable", "audit production security"), 0.8)


if __name__ == "__main__":
    unittest.main()
