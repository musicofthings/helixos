"""Run with: python -m unittest mcp/servers/biopython_local/test_server.py"""

import unittest

from server import handle_request


def call(request_id, name, arguments):
    return handle_request(
        {"id": request_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    )


class MalformedInputTest(unittest.TestCase):
    def test_non_string_sequence_returns_error_then_valid_request_works(self):
        bad = call("1", "analyze_sequence", {"sequence": 123})
        self.assertIn("error", bad)
        good = call("2", "analyze_sequence", {"sequence": "ACGT"})
        self.assertEqual(good["result"]["length"], 4)

    def test_params_and_arguments_shape(self):
        self.assertIn("error", handle_request({"id": "1", "method": "tools/call", "params": [1]}))
        self.assertIn(
            "error",
            handle_request({"id": "2", "method": "tools/call", "params": {"name": "analyze_sequence", "arguments": "x"}}),
        )


if __name__ == "__main__":
    unittest.main()
