import os, unittest
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
import ai

class RouterTest(unittest.TestCase):
    def setUp(self):
        self.old = ai.PROVIDERS.copy()
        ai.PROVIDERS = {
            "groq": ("GROQ_API_KEY", "https://groq.test/v1", "openai"),
            "openai": ("OPENAI_API_KEY", "https://openai.test/v1", "openai"),
        }
        os.environ["GROQ_API_KEY"] = "g"
        os.environ["OPENAI_API_KEY"] = "o"
        os.environ["MM_PERSIST_STATE"] = "0"  # never touch the real learning state file

    def tearDown(self):
        ai.PROVIDERS = self.old
        for k in ("GROQ_API_KEY", "OPENAI_API_KEY", "MM_FREE_ONLY", "MM_PERSIST_STATE"):
            os.environ.pop(k, None)

    def test_discovery_and_heavy_model_selection(self):
        calls = []
        def fake(url, key, method="GET", body=None, headers=None):
            calls.append((url, key, method))
            if method == "GET":
                if "groq.test" in url:
                    return 200, {"data": [{"id": "openai/gpt-oss-120b", "context_length": 131072},
                                         {"id": "openai/gpt-oss-20b", "context_length": 131072}]}, {}
                return 200, {"data": [{"id": "gpt-5.6", "context_length": 200000}]}, {}
            if "openai.test" in url:
                raise ai.AIError("quota", 429, True)
            return 200, {"choices": [{"message": {"role": "assistant", "content": "ok"}}],
                         "usage": {"prompt_tokens": 10, "completion_tokens": 5}}, {}
        old = ai._json
        ai._json = fake
        try:
            r = ai.Router()
            self.assertEqual(r.available()[0].id, "gpt-5.6")
            result = r.call([{"role":"user","content":"x"}], tier=3)
            self.assertEqual(result["message"]["content"], "ok")
        finally:
            ai._json = old

    def test_score_does_not_reject_chat_models(self):
        self.assertGreaterEqual(ai._score("gpt-5.6"), 82)
        self.assertLess(ai._score("text-embedding-3-small"), 0)

    def test_free_only_filters_paid_provider(self):
        os.environ["MM_FREE_ONLY"] = "1"
        os.environ.pop("GROQ_API_KEY", None)
        old = ai._json
        ai._json = lambda url,key,method="GET",body=None,headers=None: (200, {"data":[{"id":"gpt-5.6","context_length":100000}]}, {})
        try:
            r=ai.Router()
            self.assertEqual(r.candidates(tier=3), [])
        finally:
            ai._json=old

if __name__ == "__main__":
    unittest.main()

# CI smoke: provider router tests are intentionally network-free.
