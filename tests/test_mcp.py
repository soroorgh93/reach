"""Reach as an MCP server (reach/mcp.py), offline with recorded Qloo answers.  python -m unittest discover -s tests"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("REACH_OFFLINE", "1"); os.environ.setdefault("REACH_LLM", "off")

from reach import mcp  # noqa: E402
from server import app as A  # noqa: E402


def deps():
    lena = A.persona("lena")
    def resolve(prof):                     # stands in for Qloo search: the recorded persona's ids
        prof["favorites"] = [dict(f) for f in lena["favorites"]]; prof["id"] = "lena"; return prof
    return {"resolve": resolve, "council": A.COUNCIL, "protocols": A.protocols, "bench": lambda: {"ran": False},
            "after": lambda prof, need: {"goal": need, "when": "today", "city": prof.get("city"), "places": [{"name": "Rose Garden", "category": "park", "km": 1.2, "because": [{"name": "Bluey"}]}], "food": [], "read": []},
            "base": "https://reach.example"}


def call(name, args):
    return mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}, deps())["result"]


class McpTest(unittest.TestCase):
    def test_handshake(self):
        r = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}, deps())["result"]
        self.assertEqual(r["protocolVersion"], "2025-03-26")
        self.assertIn("tools", r["capabilities"])
        self.assertIsNone(mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, deps()))
        names = [t["name"] for t in mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, deps())["result"]["tools"]]
        self.assertEqual(names, ["compose_session", "after_the_music", "explain_evidence", "reach_vs_chatbot"])

    def test_compose_session(self):
        r = call("compose_session", {"favourites": ["Thomas & Friends"], "need": "sleep", "city": "San Jose"})
        self.assertFalse(r["isError"], r)
        d = r["structuredContent"]
        self.assertEqual(d["need"], "sleep")
        self.assertTrue(d["qloo_picks"] and d["evidence"])
        self.assertEqual(d["evidence"][0]["grade"], "A")
        self.assertTrue(d["open_in_app"].startswith("https://reach.example/?love="))
        self.assertIn("need=sleep", d["open_in_app"])
        text = r["content"][0]["text"]
        self.assertIn("Sleep descent", text); self.assertIn("Play it:", text)

    def test_bad_input_is_a_tool_error_not_a_crash(self):
        self.assertTrue(call("compose_session", {"favourites": [], "need": "sleep"})["isError"])
        self.assertTrue(call("compose_session", {"favourites": ["x"], "need": "rm -rf"})["isError"])
        self.assertTrue(call("after_the_music", {"favourites": ["x"], "need": "calm", "city": ""})["isError"])
        bad = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope"}}, deps())
        self.assertEqual(bad["error"]["code"], -32602)

    def test_after_and_evidence(self):
        r = call("after_the_music", {"favourites": ["Bluey"], "need": "calm", "city": "San Jose"})
        self.assertIn("Rose Garden", r["content"][0]["text"]); self.assertIn("Never suggested: bars", r["content"][0]["text"])
        e = call("explain_evidence", {"need": "sleep"})
        self.assertIn("grade A", e["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
