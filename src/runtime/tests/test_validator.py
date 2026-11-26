"""Validator unit checks (stdlib unittest)."""

from __future__ import annotations

import unittest

from src.runtime.validator import ActionValidator, extract_json_array


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.actions = [
            {"function": "stand", "action": "站立", "params": []},
            {
                "function": "forward",
                "action": "前进一步",
                "params": [
                    {"name": "x", "type": "number", "default": 5.0},
                ],
            },
        ]
        self.v = ActionValidator(self.actions, min_actions=1, max_actions=5)

    def test_extract_array(self) -> None:
        text = '前置\n[{"function":"stand","params":{}}]\n后置'
        arr = extract_json_array(text)
        self.assertIsNotNone(arr)
        assert arr is not None
        self.assertEqual(arr[0]["function"], "stand")

    def test_unknown_function_skipped(self) -> None:
        raw = '[{"function":"fly","params":{}},{"function":"stand","params":{}}]'
        valid, errors = self.v.parse_and_validate(raw)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["action_def"]["function"], "stand")
        self.assertTrue(any("unknown" in e for e in errors))

    def test_number_param_coercion(self) -> None:
        raw = '[{"function":"forward","params":{"x":"3.5"}}]'
        valid, errors = self.v.parse_and_validate(raw)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["params"]["x"], 3.5)


if __name__ == "__main__":
    unittest.main()
