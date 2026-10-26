import http.client
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from ata import enhance, settings

MEETING = {"title": "Kickoff", "started_at": "2026-10-26T14:30:00", "lang": "en", "notes": "- prazo",
           "transcript": "[00:00:01] **Outros:** Deadline is Friday.\n", "ata": "## Prazo\n- sexta",
           "chat": [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}]}


def response(content: str) -> io.BytesIO:
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


class EnhanceTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-secret"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_summary_messages(self):
        system, user = enhance.summary_messages(MEETING)
        self.assertEqual(system["content"], enhance.SUMMARY_PROMPT.read_text(encoding="utf-8"))
        self.assertIn("Idioma: English", user["content"])
        self.assertIn("<anotacoes>\n- prazo\n</anotacoes>", user["content"])
        self.assertIn("Deadline is Friday.", user["content"])

    def test_empty_parts_are_explicit(self):
        _, user = enhance.summary_messages({**MEETING, "title": "", "notes": " ", "transcript": ""})
        self.assertIn("Título: sem título", user["content"])
        self.assertIn("(nenhuma)", user["content"])
        self.assertIn("(vazia)", user["content"])

    def test_chat_messages_carry_summary_history_and_message(self):
        msgs = enhance.chat_messages(MEETING, "mais curto")
        self.assertIn("<resumo_atual>\n## Prazo\n- sexta\n</resumo_atual>", msgs[1]["content"])
        self.assertEqual([m["content"] for m in msgs[-3:]],
                         ["q1", '{"reply": "a1", "summary": null}', "mais curto"])
        self.assertTrue(all(json.loads(m["content"]) for m in msgs[2:-1] if m["role"] == "assistant"))

    def test_chat_parses_reply_and_optional_summary(self):
        with mock.patch("urllib.request.urlopen", return_value=response('{"reply": "Sexta [00:00:01]", "summary": null}')):
            self.assertEqual(enhance.chat(MEETING, "prazo?"), {"reply": "Sexta [00:00:01]", "summary": None})
        with mock.patch("urllib.request.urlopen", return_value=response('{"reply": "Encurtei.", "summary": "## Prazo"}')):
            self.assertEqual(enhance.chat(MEETING, "mais curto")["summary"], "## Prazo")
        for bad in ["not json", '{"summary": "x"}', '{"reply": 3, "summary": null}']:
            with mock.patch("urllib.request.urlopen", return_value=response(bad)):
                with self.assertRaises(RuntimeError):
                    enhance.chat(MEETING, "x")

    def test_api_key_from_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(settings, "ROOT", Path(tmp)):
            with self.assertRaises(RuntimeError):
                enhance.api_key()
            (Path(tmp) / ".env").write_text('OTHER=1\nDEEPSEEK_API_KEY="sk-test"\n', encoding="utf-8")
            self.assertEqual(enhance.api_key(), "sk-test")

    def test_summarize_and_http_error_hides_key(self):
        with mock.patch("urllib.request.urlopen", return_value=response(" ## Resumo\nok ")):
            self.assertEqual(enhance.summarize(MEETING), "## Resumo\nok")
        err = urllib.error.HTTPError(enhance.API, 401, "Unauthorized", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(RuntimeError) as ctx:
                enhance.summarize(MEETING)
        self.assertIn("chave inválida", str(ctx.exception))
        self.assertNotIn("sk-secret", str(ctx.exception))

    def test_network_failures_become_clear_errors(self):
        for err in [ConnectionResetError(), http.client.RemoteDisconnected("x"), TimeoutError()]:
            with mock.patch("urllib.request.urlopen", side_effect=err):
                with self.assertRaisesRegex(RuntimeError, "Sem conexão"):
                    enhance.summarize(MEETING)
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(b"<html>")):
            with self.assertRaisesRegex(RuntimeError, "formato inesperado"):
                enhance.summarize(MEETING)

    def test_rejects_huge_transcript(self):
        with self.assertRaisesRegex(RuntimeError, "longa demais"):
            enhance.summary_messages({**MEETING, "transcript": "x" * (enhance.MAX_TRANSCRIPT + 1)})


if __name__ == "__main__":
    unittest.main()
