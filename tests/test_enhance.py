import http.client
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from metranscript import enhance, privacy, settings, store
from metranscript.privacy import Mask

MEETING = {"title": "Kickoff", "started_at": "2026-10-26T14:30:00", "lang": "en", "notes": "- deadline",
           "transcript": "[00:00:01] **Others:** Deadline is Friday.\n", "summary": "## Deadline\n- Friday",
           "chat": [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}]}


def response(content: str) -> io.BytesIO:
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


class EnhanceTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-secret"})
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = mock.patch.object(privacy, "ROOT", Path(tmp.name))
        root.start()
        self.addCleanup(root.stop)

    def test_summary_messages(self):
        system, user = enhance.summary_messages(MEETING, Mask())
        self.assertEqual(system["content"], enhance.SUMMARY_PROMPT.read_text(encoding="utf-8"))
        self.assertIn("Language: English", user["content"])
        self.assertIn("Language: Brazilian Portuguese", enhance.summary_messages({**MEETING, "lang": "pt"}, Mask())[1]["content"])
        self.assertIn("<notes>\n- deadline\n</notes>", user["content"])
        self.assertIn("Deadline is Friday.", user["content"])

    def test_the_summary_prompt_asks_for_accuracy_and_keeps_next_steps_last(self):
        system = enhance.summary_messages(MEETING, Mask())[0]["content"]
        for rule in ("Never invent", "most plausible", "Do not expand an acronym", '"(?)"', "always the very last section"):
            self.assertIn(rule, system)
        summary = "## Overview\n- x\n\n## Open questions\n- y\n\n## Decisions\n- z\n\n## Próximos passos\n- Eu: enviar (sexta)"
        self.assertEqual(store.split_summary(summary)[1], "- Eu: enviar (sexta)")

    def test_the_summary_request_is_precise_and_roomy(self):
        with mock.patch.object(enhance, "_complete", return_value="## A") as complete:
            enhance.summarize(MEETING, Mask())
        self.assertEqual((complete.call_args.kwargs["temperature"], complete.call_args.kwargs["max_tokens"]), (0.2, 8000))

    def test_empty_parts_are_explicit(self):
        _, user = enhance.summary_messages({**MEETING, "title": "", "notes": " ", "transcript": ""}, Mask())
        self.assertIn("Title: untitled", user["content"])
        self.assertIn("(none)", user["content"])
        self.assertIn("(empty)", user["content"])

    def test_chat_messages_carry_summary_history_and_message(self):
        msgs = enhance.chat_messages(MEETING, "shorter", Mask())
        self.assertIn("<current_summary>\n## Deadline\n- Friday\n</current_summary>", msgs[1]["content"])
        self.assertEqual([m["content"] for m in msgs[-3:]],
                         ["q1", '{"reply": "a1", "summary": null}', "shorter"])
        self.assertTrue(all(json.loads(m["content"]) for m in msgs[2:-1] if m["role"] == "assistant"))

    def test_chat_parses_reply_and_optional_summary(self):
        with mock.patch("urllib.request.urlopen", return_value=response('{"reply": "Friday [00:00:01]", "summary": null}')):
            self.assertEqual(enhance.chat(MEETING, "deadline?", Mask()), {"reply": "Friday [00:00:01]", "summary": None})
        with mock.patch("urllib.request.urlopen", return_value=response('{"reply": "Shortened.", "summary": "## Deadline"}')):
            self.assertEqual(enhance.chat(MEETING, "shorter", Mask())["summary"], "## Deadline")
        for bad in ["not json", '{"summary": "x"}', '{"reply": 3, "summary": null}']:
            with mock.patch("urllib.request.urlopen", return_value=response(bad)):
                with self.assertRaises(RuntimeError):
                    enhance.chat(MEETING, "x", Mask())

    def test_api_key_from_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(settings, "ROOT", Path(tmp)):
            with self.assertRaises(RuntimeError):
                enhance.api_key()
            (Path(tmp) / ".env").write_text('OTHER=1\nDEEPSEEK_API_KEY="sk-test"\n', encoding="utf-8")
            self.assertEqual(enhance.api_key(), "sk-test")

    def test_summarize_and_http_error_hides_key(self):
        with mock.patch("urllib.request.urlopen", return_value=response(" ## Resumo\nok ")):
            self.assertEqual(enhance.summarize(MEETING, Mask()), "## Resumo\nok")
        err = urllib.error.HTTPError(enhance.API, 401, "Unauthorized", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(RuntimeError) as ctx:
                enhance.summarize(MEETING, Mask())
        self.assertIn("invalid key", str(ctx.exception))
        self.assertNotIn("sk-secret", str(ctx.exception))

    def test_network_failures_become_clear_errors(self):
        for err in [ConnectionResetError(), http.client.RemoteDisconnected("x"), TimeoutError()]:
            with mock.patch("urllib.request.urlopen", side_effect=err):
                with self.assertRaisesRegex(RuntimeError, "Cannot reach"):
                    enhance.summarize(MEETING, Mask())
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(b"<html>")):
            with self.assertRaisesRegex(RuntimeError, "unexpected format"):
                enhance.summarize(MEETING, Mask())

    def test_rejects_huge_transcript(self):
        with self.assertRaisesRegex(RuntimeError, "too long"):
            enhance.summary_messages({**MEETING, "transcript": "x" * (enhance.MAX_TRANSCRIPT + 1)}, Mask())


SECRET_MEETING = {
    **MEETING, "title": "Acme renewal",
    "notes": "- ask joao.silva@acme.com about the R$ 250 mil plan",
    "transcript": "[00:00:01] **Others:** Acme wants the Falcon launch moved. See https://acme.com/deal.\n",
    "summary": "## Acme\n- Falcon moves",
    "chat": [{"role": "user", "content": "what did Acme say?"}, {"role": "assistant", "content": "Acme asked for Falcon."}],
}


class ProtectionTest(EnhanceTest):
    def mask(self):
        privacy.save_terms("Acme\nFalcon")
        return Mask()

    def sent_text(self, urlopen) -> str:
        return urlopen.call_args.args[0].data.decode()

    def test_nothing_sensitive_is_in_the_messages(self):
        mask = self.mask()
        everything = json.dumps(enhance.summary_messages(SECRET_MEETING, mask)[1:] + enhance.chat_messages(SECRET_MEETING, "Is Acme ok?", mask)[1:])
        for leaked in ("Acme", "Falcon", "acme.com", "joao.silva", "250 mil"):
            self.assertNotIn(leaked, everything)
        self.assertIn("[TERM_1]", everything)

    def test_summary_comes_back_with_the_real_names(self):
        mask = self.mask()
        with mock.patch("urllib.request.urlopen", return_value=response("## [TERM_1]\n- [TERM_2] moves, mail [EMAIL_1]")) as call:
            summary = enhance.summarize(SECRET_MEETING, mask)
        self.assertEqual(summary, "## Acme\n- Falcon moves, mail joao.silva@acme.com")
        self.assertNotIn("Acme", self.sent_text(call))

    def test_chat_reply_and_summary_come_back_with_the_real_names(self):
        mask = self.mask()
        body = '{"reply": "[TERM_1] said yes", "summary": "## [TERM_1]"}'
        with mock.patch("urllib.request.urlopen", return_value=response(body)) as call:
            result = enhance.chat(SECRET_MEETING, "tell me about Acme", mask)
        self.assertEqual(result, {"reply": "Acme said yes", "summary": "## Acme"})
        self.assertNotIn("Acme", self.sent_text(call))
        self.assertEqual(len(mask), 5)


if __name__ == "__main__":
    unittest.main()
