import json
import unittest
from unittest import mock

from metranscript import enhance, privacy, server, store
from tests.http_case import ServerCase


class PrivacyRoutesTest(ServerCase):
    def setUp(self):
        self.addCleanup(lambda: (privacy.ROOT / "sensitive-terms.txt").unlink(missing_ok=True))

    def meeting(self, **kw) -> str:
        mid = store.create("Acme renewal", "en", **kw)
        store.append_segments(mid, [{"t": 1, "who": "Others", "text": "Acme wants Falcon moved."}])
        return mid

    def test_terms_can_be_read_and_saved(self):
        self.assertEqual(self.call("GET", "/api/privacy"), (200, {"terms": []}))
        status, body = self.call("PUT", "/api/privacy", {"terms": "Acme\n\nFalcon\nacme"})
        self.assertEqual((status, body), (200, {"terms": ["Acme", "Falcon"]}))
        self.assertEqual(self.call("GET", "/api/privacy")[1], {"terms": ["Acme", "Falcon"]})

    def test_glossary_can_be_read_and_saved_and_accepts_short_acronyms(self):
        self.addCleanup(lambda: (privacy.ROOT / "glossary.txt").unlink(missing_ok=True))
        self.assertEqual(self.call("GET", "/api/glossary"), (200, {"terms": []}))
        status, body = self.call("PUT", "/api/glossary", {"terms": "GCP\nControl-M\nPH\ngcp"})
        self.assertEqual((status, body), (200, {"terms": ["GCP", "Control-M", "PH"]}))
        self.assertEqual(privacy.glossary(), ["GCP", "Control-M", "PH"])
        self.assertEqual(self.call("PUT", "/api/glossary", {"terms": 5})[0], 400)
        self.assertEqual(self.call("PUT", "/api/glossary", {"terms": "x"})[0], 400)
        self.assertEqual(self.call("GET", "/api/privacy")[1], {"terms": []})  # a separate list

    def test_bad_terms_are_rejected(self):
        self.assertEqual(self.call("PUT", "/api/privacy", {"terms": 5})[0], 400)
        self.assertEqual(self.call("PUT", "/api/privacy", {"terms": "x" * 101})[0], 400)
        self.assertEqual(self.call("GET", "/api/privacy")[1], {"terms": []})

    def test_routes_are_guarded(self):
        self.assertEqual(self.call("GET", "/api/privacy", headers={"Host": "evil.com"})[0], 403)
        self.assertEqual(self.call("PUT", "/api/privacy", {}, headers={"Content-Type": "text/plain"})[0], 415)

    def test_summary_is_made_from_masked_text_and_comes_back_readable(self):
        privacy.save_terms("Acme\nFalcon")
        mid = self.meeting()
        with mock.patch.object(enhance, "_complete", return_value="## [TERM_1]\n- [TERM_2] moves") as complete:
            server.summarize(mid)
        sent = json.dumps(complete.call_args.args[0])
        self.assertNotIn("Acme", sent)
        self.assertNotIn("Falcon", sent)
        loaded = store.load(mid)
        self.assertEqual(loaded["summary"], "## Acme\n- Falcon moves")
        self.assertEqual(loaded["protected"], 2)

    def test_chat_is_masked_too_and_keeps_the_biggest_count(self):
        privacy.save_terms("Acme\nFalcon")
        mid = self.meeting()
        store.set_protected(mid, 9)
        with mock.patch.object(enhance, "_complete", return_value='{"reply": "[TERM_1] is fine", "summary": null}') as complete:
            result = server.chat(mid, "How is Acme?")
        self.assertNotIn("Acme", json.dumps(complete.call_args.args[0]))
        self.assertEqual(result["chat"][-1]["content"], "Acme is fine")
        self.assertEqual(result["protected"], 9)

    def test_old_private_meetings_are_still_never_sent(self):
        mid = self.meeting(private=True)
        with mock.patch.object(enhance, "_complete") as complete:
            with self.assertRaises(RuntimeError):
                server.summarize(mid)
        complete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
