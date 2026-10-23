"""Admin session, CSRF protection and login throttling."""

import hashlib
import hmac
import math
import secrets
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Annotated

from fastapi import Form, HTTPException, Request

from app.config import Settings

if TYPE_CHECKING:
    from collections.abc import Callable


class AdminRequired(Exception):
    """Raised by `require_admin`; the app turns it into a redirect to the login page."""


def settings_of(request: Request) -> Settings:
    settings = request.app.state.settings
    assert isinstance(settings, Settings)
    return settings


def client_ip(request: Request) -> str:
    # Behind a reverse proxy run uvicorn with --proxy-headers so this is the visitor's address.
    return request.client.host if request.client else "unknown"


def _digest(settings: Settings, message: str) -> str:
    return hmac.new(settings.secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()


def ip_hash(request: Request) -> str:
    return _digest(settings_of(request), "ip:" + client_ip(request))[:32]


def _session_marker(settings: Settings) -> str:
    # Stored in the session on login. Changing the password in .env invalidates every existing session.
    return _digest(settings, f"admin:{settings.admin_username}:{settings.admin_password}")


def check_credentials(settings: Settings, username: str, password: str) -> bool:
    user_ok = hmac.compare_digest(username.encode(), settings.admin_username.encode())
    pass_ok = hmac.compare_digest(password.encode(), settings.admin_password.encode())
    return user_ok and pass_ok


def log_in(request: Request) -> None:
    request.session.clear()
    request.session["admin"] = _session_marker(settings_of(request))
    request.session["csrf"] = secrets.token_urlsafe(32)


def log_out(request: Request) -> None:
    request.session.clear()


def is_admin(request: Request) -> bool:
    marker = request.session.get("admin")
    return isinstance(marker, str) and hmac.compare_digest(marker, _session_marker(settings_of(request)))


def require_admin(request: Request) -> None:
    if not is_admin(request):
        raise AdminRequired


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not isinstance(token, str):
        token = request.session["csrf"] = secrets.token_urlsafe(32)
    return token


def csrf_valid(request: Request, submitted: str) -> bool:
    expected = request.session.get("csrf")
    return isinstance(expected, str) and hmac.compare_digest(submitted.encode(), expected.encode())


def verify_csrf(request: Request, csrf_token: Annotated[str, Form()] = "") -> None:
    if not csrf_valid(request, csrf_token):
        raise HTTPException(403, "Сессия устарела. Обновите страницу и повторите действие.")


def safe_next(target: str | None, default: str) -> str:
    """Only allow redirects to paths on this site."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return default


class LoginThrottle:
    """In-memory limits for login attempts (per process, which is fine for a single uvicorn worker).

    * per IP: at most one attempt per `min_interval` seconds (very fast repeats are rejected);
    * per IP: after `max_failures` wrong passwords within `window` seconds, wait until the oldest expires;
    * globally: after `global_max_failures` wrong passwords within `window`, everyone waits (slows down
      attacks spread over many addresses).
    """

    def __init__(
        self,
        *,
        min_interval: float = 1.0,
        max_failures: int = 5,
        global_max_failures: int = 100,
        window: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = min_interval
        self.max_failures = max_failures
        self.global_max_failures = global_max_failures
        self.window = window
        self._clock = clock
        self._lock = threading.Lock()
        self._last_attempt: dict[str, float] = {}
        self._failures: dict[str, deque[float]] = {}
        self._all_failures: deque[float] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        while self._all_failures and self._all_failures[0] <= cutoff:
            self._all_failures.popleft()
        for ip in list(self._failures):
            fails = self._failures[ip]
            while fails and fails[0] <= cutoff:
                fails.popleft()
            if not fails:
                del self._failures[ip]
        for ip, at in list(self._last_attempt.items()):
            if now - at >= self.min_interval:
                del self._last_attempt[ip]

    def check(self, ip: str) -> int:
        """Register an attempt from `ip`. Returns 0 if it may proceed, otherwise the seconds to wait."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            fails = self._failures.get(ip)
            if fails and len(fails) >= self.max_failures:
                return max(1, math.ceil(fails[0] + self.window - now))
            if len(self._all_failures) >= self.global_max_failures:
                return max(1, math.ceil(self._all_failures[0] + self.window - now))
            last = self._last_attempt.get(ip)
            self._last_attempt[ip] = now  # hammering keeps resetting the interval
            if last is not None and now - last < self.min_interval:
                return max(1, math.ceil(self.min_interval - (now - last)))
            return 0

    def failure(self, ip: str) -> None:
        with self._lock:
            now = self._clock()
            self._failures.setdefault(ip, deque()).append(now)
            self._all_failures.append(now)

    def success(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)
