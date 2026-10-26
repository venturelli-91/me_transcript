import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from ata import store


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
        self.assertEqual((m["title"], m["lang"], m["private"], m["notes"], m["ata"]), ("Kickoff", "pt", False, "", ""))
        self.assertIsNone(m["ended_at"])

    def test_same_minute_does_not_collide(self):
        when = datetime(2026, 10, 26, 14, 30)
        self.assertEqual(store.create("a", "pt", now=when), "2026-10-26_1430")
        self.assertEqual(store.create("b", "pt", now=when), "2026-10-26_1430-2")
        self.assertEqual(store.create("c", "en", now=when), "2026-10-26_1430-3")

    def test_list_newest_first(self):
        store.create("old", "pt", now=datetime(2026, 10, 1, 9, 0))
        new = store.create("new", "en", now=datetime(2026, 10, 26, 9, 0))
        store.save_ata(new, "# Ata")
        listed = store.list_meetings()
        self.assertEqual([m["title"] for m in listed], ["new", "old"])
        self.assertEqual([m["has_ata"] for m in listed], [True, False])

    def test_notes_segments_and_finish(self):
        mid = store.create("", "pt")
        store.save_notes(mid, "- decidir preço")
        store.append_segments(mid, [{"t": 83.7, "who": "Outros", "text": " Fechado,\nentão. "}])
        store.append_segments(mid, [{"t": 3725, "who": "Eu", "text": "Ok."}])
        store.finish(mid)
        m = store.load(mid)
        self.assertEqual(m["notes"], "- decidir preço")
        self.assertEqual(m["transcript"], "[00:01:23] **Outros:** Fechado, então.\n[01:02:05] **Eu:** Ok.\n")
        self.assertIsNotNone(m["ended_at"])

    def test_ata_versions_and_undo(self):
        mid = store.create("", "pt")
        store.save_ata(mid, "v1")
        self.assertFalse(store.load(mid)["can_undo"])
        store.save_ata(mid, "v2")
        store.save_ata(mid, "v3")
        store.undo_ata(mid)
        self.assertEqual(store.load(mid)["ata"], "v2")
        store.undo_ata(mid)
        m = store.load(mid)
        self.assertEqual((m["ata"], m["can_undo"]), ("v1", False))
        with self.assertRaises(RuntimeError):
            store.undo_ata(mid)

    def test_chat_is_saved(self):
        mid = store.create("", "pt")
        self.assertEqual(store.load(mid)["chat"], [])
        store.append_chat(mid, {"role": "user", "content": "prazo?"}, {"role": "assistant", "content": "sexta"})
        store.append_chat(mid, {"role": "user", "content": "ok"})
        self.assertEqual([c["content"] for c in store.load(mid)["chat"]], ["prazo?", "sexta", "ok"])

    def test_rejects_unknown_or_malicious_id(self):
        store.create("", "pt", now=datetime(2026, 10, 26, 14, 30))
        for bad in ["../etc", "2026-10-27_1430", "2026-10-26_1430\n", "x"]:
            with self.assertRaises(KeyError):
                store.load(bad)


if __name__ == "__main__":
    unittest.main()
