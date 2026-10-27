import base64
import hashlib
import http.client
import io
import json
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

from metranscript import google, server, settings
from tests.http_case import ServerCase

REFRESH = "1//refresh-token-secret"
ACCESS = "ya29.access-token-secret"


def jwt(**claims) -> str:
    part = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return f"{part({'alg': 'RS256'})}.{part(claims)}.signature"


class Reply:
    def __init__(self, data: dict | bytes) -> None:
        self.data = data if isinstance(data, bytes) else json.dumps(data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit=-1):
        return self.data


def http_error(status: int, code: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", status, "err", {}, io.BytesIO(json.dumps({"error": code}).encode()))


def token_reply(email="me@gmail.com", **extra) -> dict:
    return {"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600,
            "id_token": jwt(email=email, email_verified=True), **extra}


class GoogleCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for target in (google, settings):
            patcher = mock.patch.object(target, "ROOT", Path(tmp.name))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "123.apps.googleusercontent.com", "GOOGLE_CLIENT_SECRET": "client-secret"})
        patcher.start()
        self.addCleanup(patcher.stop)
        for cache in (google._pending, google._access, google._reconnect):
            cache.clear()
        self.requests: list = []

    def answer(self, *replies):
        """Make the next Google calls return these replies (an exception is raised instead of returned)."""
        queue = list(replies)

        def fake(req):
            self.requests.append(req)
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return Reply(item)

        return mock.patch.object(google, "_open", fake)

    def sign_in(self, email="me@gmail.com") -> str:
        state = urllib.parse.parse_qs(urllib.parse.urlsplit(google.start_login(8765)).query)["state"][0]
        with self.answer(token_reply(email)):
            return google.finish_login(8765, "auth-code", state)


class DpapiTest(unittest.TestCase):
    def test_round_trip_and_the_ciphertext_hides_the_token(self):
        blob = google.protect(REFRESH.encode())
        self.assertNotIn(REFRESH.encode(), blob)
        self.assertEqual(google.unprotect(blob), REFRESH.encode())
        with self.assertRaises(OSError):
            google.unprotect(b"not a protected blob")


class LoginTest(GoogleCase):
    def test_the_login_address_uses_pkce_and_needs_the_client(self):
        url = urllib.parse.urlsplit(google.start_login(8765))
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        self.assertEqual((url.scheme, url.netloc, url.path), ("https", "accounts.google.com", "/o/oauth2/v2/auth"))
        self.assertEqual((q["client_id"], q["redirect_uri"], q["response_type"]), ("123.apps.googleusercontent.com", "http://127.0.0.1:8765/oauth/google", "code"))
        self.assertEqual((q["code_challenge_method"], q["access_type"]), ("S256", "offline"))
        self.assertIn("gmail.send", q["scope"])
        self.assertIn("calendar.readonly", q["scope"])
        verifier = google._pending[q["state"]][0]
        digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(q["code_challenge"], digest)
        self.assertNotIn("client_secret", url.query)
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_SECRET": ""}), self.assertRaises(RuntimeError):
            google.start_login(8765)

    def test_signing_in_stores_an_encrypted_account_and_sends_the_pkce_verifier(self):
        email = self.sign_in("Me@Gmail.com")
        self.assertEqual(email, "me@gmail.com")
        sent = urllib.parse.parse_qs(self.requests[0].data.decode())
        self.assertEqual((sent["grant_type"], sent["code"], sent["client_secret"]), (["authorization_code"], ["auth-code"], ["client-secret"]))
        self.assertEqual(len(sent["code_verifier"][0]), len(google.secrets.token_urlsafe(64)))
        text = google._file().read_text(encoding="utf-8")
        self.assertNotIn(REFRESH, text)
        self.assertNotIn(ACCESS, text)
        self.assertEqual(google.accounts(), [{"email": "me@gmail.com", "sender": True, "needs_reconnect": False}])
        self.assertEqual(google._refresh_token("me@gmail.com"), REFRESH)
        self.assertEqual(google.access_token("me@gmail.com"), ACCESS)  # from the memory cache: no more calls
        self.assertEqual(len(self.requests), 1)

    def test_a_state_works_once_and_expires(self):
        state = urllib.parse.parse_qs(urllib.parse.urlsplit(google.start_login(8765)).query)["state"][0]
        with self.answer(token_reply()):
            google.finish_login(8765, "c", state)
        with self.assertRaises(RuntimeError), self.answer():
            google.finish_login(8765, "c", state)
        with self.assertRaises(RuntimeError), self.answer():
            google.finish_login(8765, "c", "never-issued")
        stale = urllib.parse.parse_qs(urllib.parse.urlsplit(google.start_login(8765)).query)["state"][0]
        google._pending[stale] = (google._pending[stale][0], time.time() - 1)
        with self.assertRaises(RuntimeError), self.answer():
            google.finish_login(8765, "c", stale)
        with self.assertRaises(RuntimeError), self.answer():
            google.finish_login(8765, "", google.start_login(1) and next(iter(google._pending)))

    def test_incomplete_or_odd_replies_save_nothing(self):
        bad = [{"access_token": ACCESS, "id_token": jwt(email="a@b.com")},  # no refresh token
               {**token_reply(), "id_token": "garbage"}, {**token_reply(), "id_token": jwt(nothing=1)},
               {**token_reply(), "id_token": jwt(email="no-at-sign")}, {**token_reply(), "id_token": jwt(email="a@b.com", email_verified=False)},
               {"error": "x"}]
        for reply in bad:
            state = urllib.parse.parse_qs(urllib.parse.urlsplit(google.start_login(8765)).query)["state"][0]
            with self.subTest(reply=list(reply)), self.answer(reply), self.assertRaises(RuntimeError) as ctx:
                google.finish_login(8765, "c", state)
            self.assertNotIn(REFRESH, str(ctx.exception))
        self.assertEqual(google.accounts(), [])

    def test_a_google_error_hides_secrets_and_a_network_error_is_clear(self):
        state = urllib.parse.parse_qs(urllib.parse.urlsplit(google.start_login(8765)).query)["state"][0]
        with self.answer(http_error(400, "invalid_grant")), self.assertRaises(google.GoogleError) as ctx:
            google.finish_login(8765, "c", state)
        self.assertEqual(str(ctx.exception), "Google rejected the request (400 invalid_grant).")
        state = urllib.parse.parse_qs(urllib.parse.urlsplit(google.start_login(8765)).query)["state"][0]
        with self.answer(OSError("offline")), self.assertRaises(RuntimeError) as ctx:
            google.finish_login(8765, "c", state)
        self.assertIn("Cannot reach Google", str(ctx.exception))


class TokensTest(GoogleCase):
    def test_an_expired_access_token_is_refreshed_and_invalid_grant_asks_to_sign_in_again(self):
        self.sign_in()
        google._access["me@gmail.com"] = (ACCESS, time.time() + 10)  # about to expire
        with self.answer({"access_token": "ya29.new", "expires_in": 3600}):
            self.assertEqual(google.access_token("me@gmail.com"), "ya29.new")
        sent = urllib.parse.parse_qs(self.requests[-1].data.decode())
        self.assertEqual((sent["grant_type"], sent["refresh_token"]), (["refresh_token"], [REFRESH]))
        with self.answer(http_error(400, "invalid_grant")), self.assertRaises(google.ReconnectNeeded):
            google.access_token("me@gmail.com", force=True)
        self.assertEqual(google.accounts()[0]["needs_reconnect"], True)
        with self.answer({"access_token": "ya29.again", "expires_in": 3600}):
            google.access_token("me@gmail.com", force=True)
        self.assertEqual(google.accounts()[0]["needs_reconnect"], False)

    def test_other_google_errors_do_not_mark_the_account(self):
        self.sign_in()
        with self.answer(http_error(500, "backendError")), self.assertRaises(google.GoogleError):
            google.access_token("me@gmail.com", force=True)
        self.assertFalse(google.accounts()[0]["needs_reconnect"])


class AccountsTest(GoogleCase):
    def test_the_sender_defaults_to_the_first_account_and_follows_the_choice(self):
        self.sign_in("a@gmail.com")
        self.sign_in("b@gmail.com")
        self.assertEqual(google.send_account(), "a@gmail.com")
        google.set_sender("b@gmail.com")
        self.assertEqual([a["sender"] for a in google.accounts()], [False, True])
        with self.assertRaises(ValueError):
            google.set_sender("stranger@gmail.com")

    def test_disconnect_revokes_forgets_and_moves_the_sender(self):
        self.sign_in("a@gmail.com")
        self.sign_in("b@gmail.com")
        google.set_sender("b@gmail.com")
        with self.answer({}):
            google.disconnect("b@gmail.com")
        self.assertEqual(urllib.parse.parse_qs(self.requests[-1].data.decode()), {"token": [REFRESH]})
        self.assertEqual(google.emails(), ["a@gmail.com"])
        self.assertEqual(google.send_account(), "a@gmail.com")
        self.assertNotIn("b@gmail.com", google._access)
        with self.answer(OSError("offline")):  # a failed revoke still disconnects
            google.disconnect("a@gmail.com")
        self.assertEqual((google.emails(), google.send_account()), ([], None))
        google.disconnect("nobody@gmail.com")  # unknown: nothing happens

    def test_signing_in_again_replaces_the_account(self):
        self.sign_in("a@gmail.com")
        self.sign_in("a@gmail.com")
        self.assertEqual(google.emails(), ["a@gmail.com"])

    def test_a_broken_accounts_file_is_ignored(self):
        for text in ("not json", "[]", '{"accounts": [1, {"email": 5}, {"email": "a@b.com"}], "send_from": 3}'):
            google._file().write_text(text, encoding="utf-8")
            self.assertEqual(google.accounts(), [])
        google._file().write_text('{"accounts": [{"email": "a@b.com", "token": "x"}]}', encoding="utf-8")
        self.assertEqual(google.emails(), ["a@b.com"])


class GoogleRoutesTest(ServerCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(google, "ROOT", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        for cache in (google._pending, google._access, google._reconnect):
            cache.clear()

    def callback(self, query: str, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", "/oauth/google" + query, headers={"Host": host or f"127.0.0.1:{self.port}"})
        res = conn.getresponse()
        res.read()
        conn.close()
        return res.status, res.getheader("Location")

    def test_status_never_carries_a_token(self):
        status, body = self.call("GET", "/api/google")
        self.assertEqual((status, body), (200, {"configured": False, "accounts": []}))
        google._save("me@gmail.com", REFRESH)
        body = self.call("GET", "/api/google")[1]
        self.assertEqual(body["accounts"], [{"email": "me@gmail.com", "sender": True, "needs_reconnect": False}])
        self.assertNotIn(REFRESH, json.dumps(body))

    def test_login_needs_the_client_and_returns_the_google_address(self):
        status, body = self.call("POST", "/api/google/login", {})
        self.assertEqual((status, body["error"]), (409, "Add your Google client ID and secret in Settings first."))
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "1.apps.googleusercontent.com", "GOOGLE_CLIENT_SECRET": "s"}):
            status, body = self.call("POST", "/api/google/login", {})
        self.assertEqual(status, 200)
        self.assertTrue(body["url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?"))
        self.assertIn(f"127.0.0.1%3A{server.PORT}%2Foauth%2Fgoogle", body["url"])

    def test_the_callback_redirects_back_to_settings_with_a_short_outcome(self):
        with mock.patch.object(google, "finish_login", return_value="me@gmail.com") as finish:
            self.assertEqual(self.callback("?code=abc&state=xyz"), (302, "/?google=connected#/settings"))
        finish.assert_called_once_with(server.PORT, "abc", "xyz")
        with mock.patch.object(google, "finish_login", side_effect=RuntimeError("Google rejected the request (400 invalid_grant).")):
            self.assertEqual(self.callback("?code=abc&state=xyz"), (302, "/?google=error#/settings"))
        with mock.patch.object(google, "finish_login") as finish:
            self.assertEqual(self.callback("?error=access_denied"), (302, "/?google=denied#/settings"))
            self.assertEqual(self.callback("?error=server_error"), (302, "/?google=error#/settings"))
        finish.assert_not_called()
        self.assertEqual(self.callback("?code=abc&state=xyz", host="evil.com")[0], 403)

    def test_sender_and_disconnect_validate_their_input(self):
        google._save("a@gmail.com", REFRESH)
        google._save("b@gmail.com", REFRESH)
        self.assertEqual(self.call("POST", "/api/google/sender", {"email": 5})[0], 400)
        self.assertEqual(self.call("POST", "/api/google/sender", {"email": "x@gmail.com"})[0], 400)
        status, body = self.call("POST", "/api/google/sender", {"email": "b@gmail.com"})
        self.assertEqual((status, [a["sender"] for a in body["accounts"]]), (200, [False, True]))
        with mock.patch.object(google, "_open", return_value=Reply({})):
            status, body = self.call("POST", "/api/google/disconnect", {"email": "b@gmail.com"})
        self.assertEqual((status, [a["email"] for a in body["accounts"]]), (200, ["a@gmail.com"]))
        self.assertEqual(self.call("POST", "/api/google/disconnect", {"email": "a@gmail.com"}, headers={"Content-Type": "text/plain"})[0], 415)


if __name__ == "__main__":
    unittest.main()
