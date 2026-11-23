"""Origin-bound HTTP session shared by opt-in live checks."""

import base64
import http.cookiejar
import json
import math
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SessionError(ValueError):
    """Safe explanation for missing or expired application credentials."""


class Session:
    def __init__(
        self,
        origin: str,
        request_file: Path | None = None,
        *,
        raw_headers: str | None = None,
        on_refresh: Callable[["Session"], None] | None = None,
    ) -> None:
        url = urllib.parse.urlsplit(origin)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
        ):
            raise ValueError("Expected an HTTPS origin")
        if request_file is not None:
            info = request_file.stat()
            if stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > 32768:
                raise ValueError("Request file must be private and bounded")
            raw_headers = request_file.read_text()
        if not raw_headers or len(raw_headers) > 32768:
            raise ValueError("Expected bounded copied request headers")
        headers = {}
        lines = iter(raw_headers.splitlines())
        for line in lines:
            line = line.strip()
            key, separator, value = line.partition(":")
            if not separator and key.lower() in {
                "host",
                "authorization",
                "cookie",
                "user-agent",
            }:
                value = next(lines, "").strip()
                separator = ":"
            if separator and key.lower() in {"host", "authorization", "cookie", "user-agent"}:
                key = key.lower()
                if key in headers:
                    raise ValueError("Duplicate request header")
                headers[key] = value.strip()
        if headers.pop("host", url.netloc) != url.netloc:
            raise ValueError("Request Host does not match origin")
        if not headers.get("authorization", "").startswith("Bearer ") and not headers.get(
            "cookie"
        ):
            raise ValueError("Missing authorization or refresh session cookies")
        self.origin = origin.rstrip("/")
        jar = http.cookiejar.CookieJar()
        for key, value in SimpleCookie(headers.pop("cookie", "")).items():
            jar.set_cookie(
                http.cookiejar.Cookie(
                    version=0,
                    name=key,
                    value=value.value,
                    port=None,
                    port_specified=False,
                    domain=url.hostname,
                    domain_specified=False,
                    domain_initial_dot=False,
                    path="/",
                    path_specified=True,
                    secure=True,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={},
                )
            )
        self.headers = headers
        self.cookies = jar
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(jar),
            NoRedirect(),
        )
        self.user_id: str | None = None
        self.auto_refresh = False
        self.on_refresh = on_refresh
        self._last_refresh = time.monotonic()

    def copied_headers(self) -> str:
        self.cookies.clear_expired_cookies()
        values = {"host": urllib.parse.urlsplit(self.origin).netloc, **self.headers}
        values["cookie"] = "; ".join(f"{cookie.name}={cookie.value}" for cookie in self.cookies)
        return "\n".join(f"{key}: {value}" for key, value in values.items())

    def json(self, path: str, *, method: str = "GET", payload: Any = None) -> Any:
        if not path.startswith("/api/") or "#" in path:
            raise ValueError("Expected a relative application API path")
        is_refresh = path == "/api/auth/refresh"
        if not is_refresh and self.user_id is not None:
            self.ensure_fresh()
        try:
            return self._json(path, method=method, payload=payload)
        except urllib.error.HTTPError as exc:
            if exc.code != 401 or is_refresh or method != "GET" or not self.auto_refresh:
                raise
            exc.close()
        self.refresh()
        # Replay only a read, once. Never automatically replay a chat, upload or deletion.
        return self._json(path, method=method, payload=payload)

    def _json(self, path: str, *, method: str, payload: Any) -> Any:
        request = urllib.request.Request(
            self.origin + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={
                **self.headers,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": self.origin,
            },
            method=method,
        )
        with self.opener.open(request, timeout=30) as response:
            if response.headers.get_content_type() != "application/json":
                if path == "/api/auth/refresh":
                    raise SessionError(
                        "LibreChat could not renew this session. Sign in, reload the page, and "
                        "copy fresh request headers including the full Cookie header in Setup."
                    )
                raise ValueError("Expected application JSON")
            body = response.read(1048577)
            if len(body) > 1048576:
                raise ValueError("Oversized application response")
            return json.loads(body)

    def ensure_fresh(self) -> None:
        if not self.auto_refresh:
            return
        expiry = None
        token = self.headers.get("authorization", "").removeprefix("Bearer ")
        try:
            payload = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            expiry = claims.get("exp")
            if type(expiry) not in (int, float) or not math.isfinite(expiry):
                expiry = None
        except (IndexError, ValueError, TypeError, AttributeError):
            pass
        # Unverified JWT claims are only a scheduling hint, never authentication evidence.
        if (expiry is not None and expiry <= time.time() + 180) or (
            expiry is None and time.monotonic() - self._last_refresh >= 300
        ):
            self.refresh()

    def refresh(self) -> None:
        self.cookies.clear_expired_cookies()
        if not any(cookie.name in {"refreshToken", "connect.sid"} for cookie in self.cookies):
            raise SessionError(
                "Automatic renewal needs the full Cookie request header. "
                "An Authorization bearer token alone cannot refresh the login."
            )
        try:
            result = self._json("/api/auth/refresh", method="POST", payload={})
        except urllib.error.HTTPError as exc:
            if exc.code not in (401, 403):
                raise
            exc.close()
            raise SessionError(
                "LibreChat rejected session renewal. Sign in again and paste fresh "
                "request headers including Cookie in Setup."
            ) from None
        token = result.get("token") if isinstance(result, dict) else None
        if not isinstance(token, str) or not token or "\r" in token or "\n" in token:
            raise SessionError(
                "LibreChat returned no renewed token. Sign in again and save fresh headers."
            )
        self.headers["authorization"] = "Bearer " + token
        self._last_refresh = time.monotonic()
        if self.on_refresh is not None:
            self.on_refresh(self)

    def authenticate(self, *, refresh: bool = False, renew_now: bool = True) -> None:
        if not self.headers.get("user-agent"):
            raise ValueError("Missing browser user-agent")
        self.auto_refresh = refresh
        if refresh and renew_now:
            self.refresh()
        elif refresh:
            self.ensure_fresh()
        user = self.json("/api/user")
        identifier = user.get("id") or user.get("_id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("No authenticated user")
        self.user_id = identifier
