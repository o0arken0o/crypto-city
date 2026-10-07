import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))


class Resp:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeGitHub:
    """A tiny in-memory issue tracker."""

    def __init__(self):
        self.issues, self.comments = {}, []

    def __call__(self, req, timeout=None):
        path = req.full_url.split("/repos/o/r")[1]
        body = json.loads(req.data) if req.data else None
        if req.method == "GET":
            return Resp([i for i in self.issues.values() if i["state"] == "open"])
        if req.method == "POST" and path == "/issues":
            n = len(self.issues) + 1
            self.issues[n] = {"number": n, "state": "open", **body}
            return Resp(self.issues[n])
        num = int(path.split("/")[2])
        if path.endswith("/comments"):
            self.comments.append((num, body["body"]))
        else:
            self.issues[num].update(body)
        return Resp({})


def state(approvals=(), blockers=()):
    return {"approvals": [{"id": a, "title": f"Pubblica {a}", "status": "pending", "created": "2026-09-01T00:00:00+00:00"} for a in approvals],
            "blockers": [{"id": b, "title": f"Blocco {b}", "status": "open", "owner": "human", "created": "2026-09-02T00:00:00+00:00"} for b in blockers]
            + [{"id": "blk_agent", "title": "lavoro agenti", "status": "open", "owner": "agent", "created": ""}]}


class NotifyTest(unittest.TestCase):
    def test_one_issue_notifies_only_news_and_closes_when_done(self):
        import notify
        fake = FakeGitHub()
        gh = notify.GitHub("tok", "o/r", "https://api.example", opener=fake)
        self.assertEqual(notify.sync(gh, state(), "owner"), "notify: niente in attesa")
        self.assertEqual(fake.issues, {})

        notify.sync(gh, state(["apr_1"], ["blk_1"]), "owner")
        self.assertEqual(len(fake.issues), 1)
        self.assertEqual(fake.issues[1]["title"], notify.TITLE)
        self.assertNotIn("lavoro agenti", fake.issues[1]["body"])  # agent blockers are not the owner's job
        self.assertEqual(len(fake.comments), 1)
        self.assertIn("@owner", fake.comments[0][1])

        notify.sync(gh, state(["apr_1"], ["blk_1"]), "owner")  # nothing new: no new notification
        self.assertEqual(len(fake.comments), 1)

        notify.sync(gh, state(["apr_1", "apr_2"], []), "owner")  # one new item: one comment, only about it
        self.assertEqual(len(fake.comments), 2)
        self.assertIn("apr_2", fake.issues[1]["body"])
        self.assertIn("Pubblica apr_2", fake.comments[1][1])
        self.assertNotIn("Pubblica apr_1", fake.comments[1][1])

        notify.sync(gh, state(), "owner")
        self.assertEqual(fake.issues[1]["state"], "closed")
        self.assertEqual(len(fake.issues), 1)

    def test_title_is_never_a_command(self):
        import notify
        self.assertFalse(notify.TITLE.lower().startswith("mm:"))


if __name__ == "__main__":
    unittest.main()
