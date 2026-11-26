"""ppi_agent parse_actions unit checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from parse_actions import extract_json_array, extract_reason, parse_actions


class ParseActionsTests(unittest.TestCase):
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

    def test_extract_array(self) -> None:
        text = '前置\n[{"function":"stand","params":{}}]\n后置'
        arr = extract_json_array(text)
        self.assertIsNotNone(arr)
        assert arr is not None
        self.assertEqual(arr[0]["function"], "stand")

    def test_unknown_function_skipped(self) -> None:
        raw = '[{"function":"fly","params":{}},{"function":"stand","params":{}}]'
        valid, errors, reason = parse_actions(raw, self.actions, 1, 5)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["action_def"]["function"], "stand")
        self.assertTrue(any("unknown" in e for e in errors))
        self.assertIsNone(reason)

    def test_number_param_coercion(self) -> None:
        raw = '[{"function":"forward","params":{"x":"3.5"}}]'
        valid, errors, reason = parse_actions(raw, self.actions, 1, 5)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["params"]["x"], 3.5)
        self.assertIsNone(reason)

    def test_object_with_reason_and_actions(self) -> None:
        raw = (
            '{"reason":"前方有人先站稳",'
            '"actions":[{"function":"stand","params":{}},'
            '{"function":"forward","params":{"x":2}}]}'
        )
        valid, errors, reason = parse_actions(raw, self.actions, 1, 5)
        self.assertEqual(reason, "前方有人先站稳")
        self.assertEqual(len(valid), 2)
        self.assertEqual(valid[0]["action_def"]["function"], "stand")
        self.assertEqual(valid[1]["params"]["x"], 2.0)
        self.assertEqual(errors, [])

    def test_extract_reason(self) -> None:
        self.assertEqual(
            extract_reason('{"reason":"观察一下","actions":[]}'),
            "观察一下",
        )
        self.assertIsNone(extract_reason('[{"function":"stand"}]'))


if __name__ == "__main__":
    unittest.main()
