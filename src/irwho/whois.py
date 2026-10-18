"""Low level WHOIS client with retries, backoff and politeness limiting."""

from __future__ import annotations

import re
import socket
import threading
import time
from typing import List, Optional, Tuple

from .models import Info, Result, Status

DEFAULT_SERVER = "whois.nic.ir"
DEFAULT_PORT = 43


class RateLimiter:
    """Makes sure no two requests are closer than ``interval`` seconds.

    Thread-safe, so a whole thread pool shares a single limiter.
    """

    def __init__(self, interval: float = 0.0) -> None:
        self.interval = max(0.0, interval)
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            time.sleep(delay)


# Responses that clearly say "this domain is registered".
_TAKEN_PATTERNS: Tuple["re.Pattern[str]", ...] = (
    re.compile(r"^\s*domain name\s*:", re.I | re.M),
    re.compile(r"^\s*domain\s*:\s*\S+\.\w{2,}", re.I | re.M),
    re.compile(r"^\s*registrant\s*:", re.I | re.M),
    re.compile(r"^\s*nserver\s*:", re.I | re.M),
    re.compile(r"^\s*name server\s*:", re.I | re.M),
    re.compile(r"^\s*registrar\s*:", re.I | re.M),
    re.compile(r"^\s*creation date\s*:", re.I | re.M),
    re.compile(r"^\s*created\s*:", re.I | re.M),
    re.compile(r"^\s*expire\s*:", re.I | re.M),
    re.compile(r"^\s*registry expiry date\s*:", re.I | re.M),
)

_AVAILABLE_MARKERS: Tuple[str, ...] = (
    "no entries found",
    "no match",
    "not found",
    "no data found",
    "available for registration",
    "is free",
    "is available",
)

_BLOCKED_MARKERS: Tuple[str, ...] = (
    "too many",
    "rate limit",
    "query limit",
    "exceeded",
    "access denied",
    "try again later",
    "temporarily blocked",
    "you are not allowed",
)


class WhoisClient:
    """Talks to a WHOIS server over port 43."""

    def __init__(
        self,
        server: str = DEFAULT_SERVER,
        port: int = DEFAULT_PORT,
        *,
        timeout: float = 8.0,
        retries: int = 2,
        backoff: float = 1.5,
        delay: float = 0.5,
    ) -> None:
        self.server = server
        self.port = port
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff = backoff
        self._limiter = RateLimiter(delay)

    # -- transport -------------------------------------------------
    @staticmethod
    def _encode_query(domain: str) -> bytes:
        payload = domain + "\r\n"
        try:
            return payload.encode("idna")  # turns ünïcode names into punycode
        except UnicodeError:
            return payload.encode("ascii", errors="ignore")

    def _query_once(self, domain: str) -> str:
        with socket.create_connection((self.server, self.port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            sock.sendall(self._encode_query(domain))

            chunks: List[bytes] = []
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    break
                if not data:
                    break
                chunks.append(data)
        return b"".join(chunks).decode("utf-8", errors="ignore")

    @staticmethod
    def _looks_blocked(text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in _BLOCKED_MARKERS)

    def query(self, domain: str) -> Tuple[str, int, Optional[str]]:
        """Return ``(response, attempts, last_error)``."""
        last_error: Optional[str] = None
        attempts = 0
        for attempt in range(self.retries + 1):
            attempts = attempt + 1
            self._limiter.wait()
            try:
                text = self._query_once(domain)
            except (OSError, TimeoutError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(self.backoff * attempts)
                continue

            if not text.strip():
                last_error = "empty response from whois server"
                time.sleep(self.backoff * attempts)
                continue

            if self._looks_blocked(text) and attempt < self.retries + 1:
                last_error = "whois server throttled the query"
                time.sleep(self.backoff * attempts * 2)
                continue

            return text, attempts, None

        return "", attempts, last_error or "unknown whois error"

    # -- verdict ---------------------------------------------------
    @staticmethod
    def classify(response: str) -> Status:
        """Turn a raw WHOIS response into a :class:`Status`."""
        text = response.strip()
        if not text:
            return Status.ERROR

        lowered = text.lower()
        if any(marker in lowered for marker in _BLOCKED_MARKERS):
            return Status.ERROR

        # Strong "this domain exists" evidence always wins.
        if any(pattern.search(text) for pattern in _TAKEN_PATTERNS):
            return Status.TAKEN

        if any(marker in lowered for marker in _AVAILABLE_MARKERS):
            return Status.AVAILABLE

        return Status.UNKNOWN

    def lookup(self, domain: str) -> Result:
        """Full pipeline for one domain: query, classify and parse."""
        started = time.perf_counter()
        try:
            text, attempts, error = self.query(domain)
        except Exception as exc:  # a bad domain must not kill a whole scan
            return Result(
                domain=domain.lower(),
                status=Status.ERROR,
                attempts=1,
                latency=time.perf_counter() - started,
                error=f"{type(exc).__name__}: {exc}",
            )
        latency = time.perf_counter() - started

        if error and not text.strip():
            return Result(
                domain=domain.lower(),
                status=Status.ERROR,
                raw=text,
                attempts=attempts,
                latency=latency,
                error=error,
            )

        return Result(
            domain=domain.lower(),
            status=self.classify(text),
            raw=text,
            info=Info.from_text(text),
            attempts=attempts,
            latency=latency,
            error=error,
        )
