"""scripts/cycle.sh: when Claude is out of quota (429) the cycle runs with the AI router instead of being skipped."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLAUDE_429 = """#!/bin/sh
echo '{"type":"result","is_error":true,"api_error_status":429,"result":"You have hit your weekly limit"}'
exit 1
"""
ROUTER_STUB = """import os, sys
open(os.path.join(os.environ["MM_ROOT"], "router_ran"), "w").write(" ".join(sys.argv[1:]))
print('{"result":"ciclo fatto dal router"}')
"""


class CycleFallbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for d in ("scripts", "engine", "bin", ".claude-plugin", "agents", "commands", "skills", "hooks"):
            if os.path.isdir(os.path.join(ROOT, d)):
                shutil.copytree(os.path.join(ROOT, d), os.path.join(self.tmp, d), ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(self.tmp, "engine", "agent_runner.py"), "w") as f:
            f.write(ROUTER_STUB)
        self.claude = os.path.join(self.tmp, "fake-claude")
        with open(self.claude, "w") as f:
            f.write(CLAUDE_429)
        os.chmod(self.claude, os.stat(self.claude).st_mode | stat.S_IEXEC)
        subprocess.run(["python3", os.path.join(self.tmp, "engine", "mm.py"), "init"], cwd=self.tmp, capture_output=True,
                       env={**os.environ, "MM_ROOT": self.tmp})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cycle(self, **extra):
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and k not in ("CLAUDE_CODE_OAUTH_TOKEN", "MM_LIVE_TOKEN")}
        env.update({"MM_ROOT": self.tmp, "MM_ENGINE": "claude", "CLAUDE": self.claude, "CLAUDE_CODE_OAUTH_TOKEN": "x", "MM_FORCE": "1"}, **extra)
        return subprocess.run(["bash", os.path.join(self.tmp, "scripts", "cycle.sh")], cwd=self.tmp, env=env, capture_output=True, text=True, timeout=120)

    def log(self):
        with open(os.path.join(self.tmp, "state", "state.json"), encoding="utf-8") as f:
            return [l["msg"] for l in json.load(f)["log"]]

    def test_falls_back_to_the_router_when_a_key_is_configured(self):
        r = self.run_cycle(GROQ_API_KEY="gsk_test")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "router_ran")), r.stdout)
        self.assertIn("router AI", r.stdout)
        self.assertTrue(any("router AI" in m for m in self.log()))
        self.assertFalse(any("saltato: limite di utilizzo" in m for m in self.log()))

    def test_skips_as_before_without_router_keys(self):
        r = self.run_cycle()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "router_ran")))
        self.assertIn("limite di utilizzo Claude", r.stdout)

    def test_fallback_can_be_turned_off(self):
        r = self.run_cycle(GROQ_API_KEY="gsk_test", MM_FALLBACK="off")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "router_ran")))
        self.assertIn("limite di utilizzo Claude", r.stdout)


if __name__ == "__main__":
    unittest.main()
