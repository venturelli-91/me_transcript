import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from metranscript import store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_root = store.ROOT
        store.ROOT = Path(self.tmp.name)

    def tearDown(self):
        store.ROOT = self.original_root
        self.tmp.cleanup()

    def test_create_and_load(self):
        mid = store.create("Kickoff", "pt", now=datetime(2026, 10, 26, 14, 30))
        self.assertEqual(mid, "2026-10-26_1430")
        m = store.load(mid)
        self.assertEqual((m["title"], m["lang"], m["private"], m["notes"], m["summary"]), ("Kickoff", "pt", False, "", ""))
        self.assertIsNone(m["ended_at"])

    def test_same_minute_does_not_collide(self):
        when = datetime(2026, 10, 26, 14, 30)
        self.assertEqual(store.create("a", "pt", now=when), "2026-10-26_1430")
        self.assertEqual(store.create("b", "pt", now=when), "2026-10-26_1430-2")
        self.assertEqual(store.create("c", "en", now=when), "2026-10-26_1430-3")

    def test_list_newest_first(self):
        store.create("old", "pt", now=datetime(2026, 10, 1, 9, 0))
        new = store.create("new", "en", now=datetime(2026, 10, 26, 9, 0))
        store.save_summary(new, "# Summary")
        listed = store.list_meetings()
        self.assertEqual([m["title"] for m in listed], ["new", "old"])
        self.assertEqual([m["has_summary"] for m in listed], [True, False])

    def test_notes_segments_and_finish(self):
        mid = store.create("", "pt")
        store.save_notes(mid, "- decide pricing")
        store.append_segments(mid, [{"t": 83.7, "who": "Others", "text": " Deal,\nthen. "}])
        store.append_segments(mid, [{"t": 3725, "who": "Me", "text": "Ok."}])
        store.finish(mid)
        m = store.load(mid)
        self.assertEqual(m["notes"], "- decide pricing")
        self.assertEqual(m["transcript"], "[00:01:23] **Others:** Deal, then.\n[01:02:05] **Me:** Ok.\n")
        self.assertIsNotNone(m["ended_at"])

    def test_ata_versions_and_undo(self):
        mid = store.create("", "pt")
        store.save_summary(mid, "v1")
        self.assertFalse(store.load(mid)["can_undo"])
        store.save_summary(mid, "v2")
        store.save_summary(mid, "v3")
        store.undo_summary(mid)
        self.assertEqual(store.load(mid)["summary"], "v2")
        store.undo_summary(mid)
        m = store.load(mid)
        self.assertEqual((m["summary"], m["can_undo"]), ("v1", False))
        with self.assertRaises(RuntimeError):
            store.undo_summary(mid)

    def test_chat_is_saved(self):
        mid = store.create("", "pt")
        self.assertEqual(store.load(mid)["chat"], [])
        store.append_chat(mid, {"role": "user", "content": "deadline?"}, {"role": "assistant", "content": "Friday"})
        store.append_chat(mid, {"role": "user", "content": "ok"})
        self.assertEqual([c["content"] for c in store.load(mid)["chat"]], ["deadline?", "Friday", "ok"])

    def test_email_status(self):
        mid = store.create("", "pt")
        store.set_email_status(mid, "no connection")
        m = store.load(mid)
        self.assertEqual((m.get("emailed_at"), m["email_error"]), (None, "no connection"))
        store.set_email_status(mid)
        m = store.load(mid)
        self.assertIsNotNone(m["emailed_at"])
        self.assertNotIn("email_error", m)

    def test_list_has_rich_fields(self):
        mid = store.create("Launch", "pt", private=True, app="Meet")
        store.finish(mid)
        store.save_summary(mid, "## Topic\n- a\n\n## Next steps\n- Me: x")
        [m] = store.list_meetings()
        self.assertEqual((m["app"], m["private"], m["has_summary"], m["has_next_steps"]), ("Meet", True, True, True))
        self.assertIsNotNone(m["ended_at"])

    def test_next_steps_heading_variants(self):
        for text in ["## Next steps", "## próximos passos  ", "x\n## NEXT STEPS\n- y"]:
            self.assertTrue(store.has_next_steps(text), text)
        for text in ["### Next steps", "## Next steps and risks", ""]:
            self.assertFalse(store.has_next_steps(text), text)

    def test_split_summary(self):
        self.assertEqual(store.split_summary("## A\n- x\n\n## Next steps\n- Me: y"), ("## A\n- x", "- Me: y"))
        self.assertEqual(store.split_summary("## A\n- x"), ("## A\n- x", None))
        self.assertEqual(store.split_summary("## A\n### Next steps\n- z"), ("## A\n### Next steps\n- z", None))
        self.assertEqual(store.split_summary("## Topic\n## próximos passos  \n- w"), ("## Topic", "- w"))
        self.assertEqual(store.split_summary("## A\n- x\n## Next steps"), ("## A\n- x", None))
        self.assertEqual(store.split_summary("## Next steps\n- a\n## B\n## Next steps\n- c")[1], "- c")
        self.assertEqual(store.split_summary(""), ("", None))

    def test_load_returns_the_split_summary(self):
        mid = store.create("", "pt")
        store.save_summary(mid, "## Topic\n- a\n\n## Next steps\n- Me: x")
        m = store.load(mid)
        self.assertEqual((m["summary_body"], m["next_steps"]), ("## Topic\n- a", "- Me: x"))
        self.assertIn("## Next steps", m["summary"])

    def test_rename_normalizes_and_truncates_the_title(self):
        mid = store.create("Old", "pt")
        store.rename(mid, "  New \n  title  ")
        self.assertEqual(store.load(mid)["title"], "New title")
        self.assertEqual(store.list_meetings()[0]["title"], "New title")
        store.rename(mid, "x" * 300)
        self.assertEqual(len(store.load(mid)["title"]), 200)
        store.rename(mid, "")
        self.assertEqual(store.load(mid)["title"], "")

    def test_rename_keeps_other_meta(self):
        mid = store.create("Old", "en", private=True, app="Meet")
        store.finish(mid)
        store.rename(mid, "New")
        m = store.load(mid)
        self.assertEqual((m["lang"], m["private"], m["app"]), ("en", True, "Meet"))
        self.assertIsNotNone(m["ended_at"])

    def test_delete_removes_the_whole_meeting(self):
        mid = store.create("Gone", "pt")
        store.save_notes(mid, "- n")
        store.save_summary(mid, "## S")
        keep = store.create("Keep", "pt", now=datetime(2026, 1, 1, 9, 0))
        store.delete(mid)
        self.assertEqual([m["id"] for m in store.list_meetings()], [keep])
        with self.assertRaises(KeyError):
            store.load(mid)
        with self.assertRaises(KeyError):
            store.delete(mid)

    def test_old_meta_without_app_or_private(self):
        mid = store.create("Old", "en")
        folder = store.meeting_dir(mid)
        (folder / "meta.json").write_text('{"title": "Old", "lang": "en", "started_at": "2026-10-01T09:00:00", "ended_at": null}', encoding="utf-8")
        [m] = store.list_meetings()
        self.assertEqual((m["app"], m["private"], m["has_next_steps"]), (None, False, False))

    def test_rejects_unknown_or_malicious_id(self):
        store.create("", "pt", now=datetime(2026, 10, 26, 14, 30))
        for bad in ["../etc", "2026-10-27_1430", "2026-10-26_1430\n", "x"]:
            with self.assertRaises(KeyError):
                store.load(bad)


if __name__ == "__main__":
    unittest.main()
