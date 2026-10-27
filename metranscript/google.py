"""Google accounts: sign-in (OAuth 2.0 authorization code + PKCE, with this app's own loopback address as the redirect),
stored logins and access tokens. The Gmail and Calendar calls live in mail.py and agenda.py and use `api()`."""
import base64
import ctypes
import hashlib
import http.client
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from pathlib import Path

from metranscript.settings import env

log = logging.getLogger("metranscript")
ROOT = Path(__file__).resolve().parent.parent
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPES = "openid email https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/calendar.events.readonly"
STATE_TTL = 600
EMAIL_RE = re.compile(r"[^\s@<>/?#\\%&=+]+@[^\s@<>/?#\\%&=+]+")
NEEDED_SCOPES = ("https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/calendar.events.readonly")
MAX_REPLY = 5_000_000

_LOCK = threading.Lock()
_pending: dict[str, tuple[str, float]] = {}  # state -> (PKCE verifier, expires at)
_access: dict[str, tuple[str, float]] = {}  # email -> (access token, expires at); never written to disk
_reconnect: set[str] = set()  # accounts whose login Google no longer accepts


class GoogleError(RuntimeError):
    """Google answered with an error. The message carries the status and Google's error code, never a token or a secret."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(f"Google rejected the request ({status}{' ' + code if code else ''}).")
        self.status, self.code = status, code


class ReconnectNeeded(RuntimeError):
    pass


# ---------- Windows DPAPI: the refresh tokens on disk can only be read by this Windows user ----------
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


CRYPT32 = ctypes.WinDLL("crypt32")
KERNEL32 = ctypes.WinDLL("kernel32")
CRYPT32.CryptProtectData.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob), ctypes.c_void_p,
                                     ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
CRYPT32.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p,
                                       ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
KERNEL32.LocalFree.argtypes = [ctypes.c_void_p]


CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _crypt(fn, data: bytes, description) -> bytes:
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    out = _Blob()
    if not fn(ctypes.byref(_Blob(len(data), buf)), description, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise OSError("Windows could not protect or read the stored login.")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        KERNEL32.LocalFree(out.pbData)


def protect(data: bytes) -> bytes:
    return _crypt(CRYPT32.CryptProtectData, data, "MeTranscript")


def unprotect(blob: bytes) -> bytes:
    return _crypt(CRYPT32.CryptUnprotectData, blob, None)


# ---------- stored accounts ----------
def _file() -> Path:
    return ROOT / "google-accounts.json"


def _load(for_update: bool = False) -> dict:
    """The stored accounts. Reading tolerates a damaged file; before changing it, a file that cannot be read is
    kept aside (or the change is refused) so one write never wipes the other accounts."""
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("accounts", []), list):
            raise ValueError("unexpected shape")
    except FileNotFoundError:
        data = {}
    except ValueError:
        if for_update:
            try:
                os.replace(_file(), _file().with_name(_file().name + ".bad"))
            except OSError:
                raise RuntimeError("The stored Google logins are damaged and could not be set aside.") from None
        data = {}
    except OSError:
        if for_update:
            raise RuntimeError("The stored Google logins are in use by another program. Try again.") from None
        data = {}
    accounts = [a for a in data.get("accounts", []) if isinstance(a, dict)
                and isinstance(a.get("email"), str) and isinstance(a.get("token"), str)]
    return {"accounts": accounts, "send_from": data.get("send_from") if isinstance(data.get("send_from"), str) else None}


def _dump(data: dict) -> None:
    path = _file()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def emails() -> list[str]:
    return [a["email"] for a in _load()["accounts"]]


def accounts() -> list[dict]:
    """What the page may see: the address, whether it sends the summaries, whether it must sign in again. No tokens."""
    sender = send_account()
    return [{"email": e, "sender": e == sender, "needs_reconnect": e in _reconnect} for e in emails()]


def send_account() -> str | None:
    found, chosen = emails(), _load()["send_from"]
    return chosen if chosen in found else (found[0] if found else None)


def set_sender(email: str) -> None:
    with _LOCK:
        data = _load(for_update=True)
        if email not in [a["email"] for a in data["accounts"]]:
            raise ValueError("That Google account is not connected.")
        data["send_from"] = email
        _dump(data)


def _save(email: str, refresh_token: str) -> None:
    token = base64.b64encode(protect(refresh_token.encode())).decode()
    with _LOCK:
        data = _load(for_update=True)
        data["accounts"] = [a for a in data["accounts"] if a["email"] != email] + [{"email": email, "token": token}]
        _dump(data)
        _reconnect.discard(email)


def _refresh_token(email: str) -> str:
    for a in _load()["accounts"]:
        if a["email"] == email:
            return unprotect(base64.b64decode(a["token"])).decode()
    raise KeyError("That Google account is not connected.")


# ---------- talking to Google ----------
def _open(req: urllib.request.Request):
    return urllib.request.urlopen(req, timeout=30)


def _call(req: urllib.request.Request) -> dict:
    try:
        with _open(req) as res:
            raw = res.read(MAX_REPLY)
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read(100_000)).get("error")
        except (OSError, ValueError, AttributeError):
            err = None
        if isinstance(err, dict):
            err = err.get("status")
        raise GoogleError(e.code, err if isinstance(err, str) else "") from None
    except (OSError, http.client.HTTPException):
        raise RuntimeError("Cannot reach Google. Check your connection and try again.") from None
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        raise RuntimeError("Google replied in an unexpected format.") from None


def _form(url: str, data: dict) -> dict:
    return _call(urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST",
                                        headers={"Content-Type": "application/x-www-form-urlencoded"}))


def client() -> tuple[str, str]:
    client_id, secret = env("GOOGLE_CLIENT_ID"), env("GOOGLE_CLIENT_SECRET")
    if not (client_id and secret):
        raise RuntimeError("Add your Google client ID and secret in Settings first.")
    return client_id, secret


def configured() -> bool:
    return bool(env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"))


def redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}/oauth/google"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def start_login(port: int) -> str:
    """The Google address the page sends the user to. The PKCE verifier and the state stay here, in memory."""
    client_id, _ = client()
    verifier, state, now = secrets.token_urlsafe(64), secrets.token_urlsafe(24), time.time()
    with _LOCK:
        for old in [s for s, (_, exp) in _pending.items() if exp < now]:
            del _pending[old]
        _pending[state] = (verifier, now + STATE_TTL)
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri(port), "response_type": "code", "scope": SCOPES,
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
        "state": state, "access_type": "offline", "prompt": "select_account consent"})


def _email_of(id_token: str) -> str:
    # The token came straight from Google over TLS in the reply to our own request, so its payload is trusted without a signature check.
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        email = claims["email"]
    except (IndexError, ValueError, KeyError, TypeError, AttributeError):
        raise RuntimeError("Google did not say which account signed in. Try again.") from None
    if not isinstance(email, str) or not EMAIL_RE.fullmatch(email) or len(email) > 254 or claims.get("email_verified") is not True:
        raise RuntimeError("Google did not confirm that account's address. Try again.")
    return email.lower()


def _seconds(reply: dict) -> float:
    try:
        return float(reply.get("expires_in", 3600))
    except (TypeError, ValueError):
        return 3600.0


def finish_login(port: int, code: str, state: str) -> str:
    """Trade the code for a login and keep it. Returns the account's address."""
    with _LOCK:
        verifier, expires = _pending.pop(state, ("", 0.0))
    if not verifier or expires < time.time() or not code:
        raise RuntimeError("This sign-in link expired or was already used. Start again from Settings.")
    client_id, secret = client()
    reply = _form(TOKEN_URL, {"client_id": client_id, "client_secret": secret, "code": code, "code_verifier": verifier,
                              "redirect_uri": redirect_uri(port), "grant_type": "authorization_code"})
    refresh, access = reply.get("refresh_token"), reply.get("access_token")
    if not isinstance(refresh, str) or not isinstance(access, str):
        raise RuntimeError("Google did not give a lasting login. Remove the app's access in your Google Account and try again.")
    if not all(scope in str(reply.get("scope", "")).split() for scope in NEEDED_SCOPES):
        try:
            _form(REVOKE_URL, {"token": refresh})
        except RuntimeError:
            log.warning("Could not revoke a Google login that lacked a permission")
        raise RuntimeError("Google did not give every permission MeTranscript needs (send email and read calendar). Sign in again and tick all the boxes.")
    email = _email_of(str(reply.get("id_token", "")))
    _save(email, refresh)
    _access[email] = (access, time.time() + _seconds(reply))
    return email


def access_token(email: str, force: bool = False) -> str:
    cached = _access.get(email)
    if cached and cached[1] - time.time() > 60 and not force:
        return cached[0]
    client_id, secret = client()
    try:
        reply = _form(TOKEN_URL, {"client_id": client_id, "client_secret": secret, "grant_type": "refresh_token",
                                  "refresh_token": _refresh_token(email)})
    except OSError:  # the stored login cannot be opened here (copied from another Windows user or machine)
        _reconnect.add(email)
        _access.pop(email, None)
        raise ReconnectNeeded(f"The stored login for {email} cannot be read on this computer. Sign in again in Settings.") from None
    except GoogleError as e:
        if e.code == "invalid_grant":
            _reconnect.add(email)
            _access.pop(email, None)
            raise ReconnectNeeded(f"Google no longer accepts the login for {email}. Sign in again in Settings.") from None
        raise
    token = reply.get("access_token")
    if not isinstance(token, str):
        raise RuntimeError("Google replied in an unexpected format.")
    _reconnect.discard(email)
    _access[email] = (token, time.time() + _seconds(reply))
    return token


def api(email: str, url: str, *, params: dict | None = None, body: dict | None = None) -> dict:
    """A Google API call as this account (GET, or POST with a JSON body). A rejected access token is refreshed once."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in (0, 1):
        headers = {"Authorization": f"Bearer {access_token(email, force=bool(attempt))}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers,
                                     method="GET" if body is None else "POST")
        try:
            return _call(req)
        except GoogleError as e:
            if e.status != 401 or attempt:
                raise
    raise AssertionError("unreachable")


def disconnect(email: str) -> bool:
    """Forget the account here and tell Google to cancel the login. A network failure must not keep it connected, so the
    answer says whether Google confirmed (False: remove the app at myaccount.google.com/permissions)."""
    revoked = True
    try:
        _form(REVOKE_URL, {"token": _refresh_token(email)})
    except (RuntimeError, KeyError, OSError):
        revoked = False
        log.warning("Could not revoke the Google login for %s; it is removed here anyway", email)
    with _LOCK:
        data = _load(for_update=True)
        data["accounts"] = [a for a in data["accounts"] if a["email"] != email]
        if data["send_from"] == email:
            data["send_from"] = None
        _dump(data)
    _access.pop(email, None)
    _reconnect.discard(email)
    return revoked
