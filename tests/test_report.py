import unittest
from datetime import datetime

from metranscript import report, store
from tests.http_case import ServerCase

MEETING = {"title": "Reunião <Q4> & mais", "started_at": "2026-10-26T14:00:00", "ended_at": "2026-10-26T14:42:00", "app": "Meet", "lang": "pt",
           "summary": "## Visão geral\nUm **resumo** com `código`.\n\n- item um\n- item <dois>\n\n## Próximos passos\n- Maria: spec"}


class ReportTest(unittest.TestCase):
    def test_markdown_has_the_title_the_meta_line_and_the_summary(self):
        md = report.markdown(MEETING)
        self.assertTrue(md.startswith("# Reunião <Q4> & mais\n\n2026-10-26 14:00 · 42 min · Meet\n\n## Visão geral"))
        self.assertTrue(md.endswith("- Maria: spec\n"))

    def test_html_escapes_everything_it_prints(self):
        page = report.page(MEETING)
        self.assertIn("<h1>Reunião &lt;Q4&gt; &amp; mais</h1>", page)
        self.assertIn("<li>item &lt;dois&gt;</li>", page)
        self.assertIn("<strong>resumo</strong>", page)
        self.assertIn("<code>código</code>", page)
        self.assertNotIn("<dois>", page)
        self.assertIn('<html lang="pt">', page)

    def test_filename_is_ascii_and_dated(self):
        self.assertEqual(report.filename(MEETING, "pdf"), "Reuniao-Q4-mais-2026-10-26.pdf")
        self.assertEqual(report.filename({**MEETING, "title": "???"}, "md"), "meeting-2026-10-26.md")

    @unittest.skipUnless(report.browser(), "needs Edge or Chrome")
    def test_pdf_is_a_real_pdf(self):
        self.assertTrue(report.pdf(MEETING).startswith(b"%PDF"))


class ReportRouteTest(ServerCase):
    def test_download_markdown_and_refuse_a_meeting_without_summary(self):
        mid = store.create("Weekly", "en", now=datetime(2026, 1, 2, 9, 0))
        status, body = self.call("GET", f"/api/meetings/{mid}/report.md")
        self.assertEqual((status, body["error"]), (400, "There is no summary to download yet."))
        store.save_summary(mid, "## Overview\nAll good.")
        status, body = self.call("GET", f"/api/meetings/{mid}/report.md")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith("# Weekly\n\n2026-01-02 09:00\n\n## Overview"))
        self.assertEqual(self.call("GET", "/api/meetings/2026-01-01_0000/report.md")[0], 404)
        self.assertEqual(self.call("GET", f"/api/meetings/{mid}/report.md", headers={"Host": "evil.com"})[0], 403)


if __name__ == "__main__":
    unittest.main()
