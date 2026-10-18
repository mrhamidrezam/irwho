"""Data structures returned by irwho."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple


class Status(str, Enum):
    """Verdict for a single domain."""

    AVAILABLE = "available"
    TAKEN = "taken"
    UNKNOWN = "unknown"
    ERROR = "error"

    def __str__(self) -> str:
        return self.value


_FIELD_PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "domain": re.compile(r"^\s*domain(?: name)?\s*:\s*(\S+)", re.I | re.M),
    "registrar": re.compile(r"^\s*registrar(?: name)?\s*:\s*(.+)", re.I | re.M),
    "registrant": re.compile(r"^\s*registrant(?: organization| org)?\s*:\s*(.+)", re.I | re.M),
    "created": re.compile(r"^\s*(?:created|creation date)\s*:\s*(\S+)", re.I | re.M),
    "expires": re.compile(r"^\s*(?:expire|expires|registry expiry date)\s*:\s*(\S+)", re.I | re.M),
    "updated": re.compile(r"^\s*(?:last[- ]updated|updated date)\s*:\s*(\S+)", re.I | re.M),
}
_NS_PATTERN = re.compile(r"^\s*(?:nserver|name server)\s*:\s*(\S+)", re.I | re.M)
_STATUS_PATTERN = re.compile(r"^\s*(?:domain status|status)\s*:\s*(\S+)", re.I | re.M)


@dataclass(frozen=True)
class Info:
    """Parsed fields extracted from a WHOIS response."""

    domain: Optional[str] = None
    registrar: Optional[str] = None
    registrant: Optional[str] = None
    created: Optional[str] = None
    expires: Optional[str] = None
    updated: Optional[str] = None
    nameservers: Tuple[str, ...] = ()
    statuses: Tuple[str, ...] = ()

    @classmethod
    def from_text(cls, text: str) -> "Info":
        def grab(key: str) -> Optional[str]:
            match = _FIELD_PATTERNS[key].search(text)
            return match.group(1).strip() if match else None

        nameservers = tuple(
            dict.fromkeys(m.group(1).rstrip(".").lower() for m in _NS_PATTERN.finditer(text))
        )
        statuses = tuple(dict.fromkeys(m.group(1) for m in _STATUS_PATTERN.finditer(text)))
        return cls(
            domain=grab("domain"),
            registrar=grab("registrar"),
            registrant=grab("registrant"),
            created=grab("created"),
            expires=grab("expires"),
            updated=grab("updated"),
            nameservers=nameservers,
            statuses=statuses,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "domain": self.domain,
            "registrar": self.registrar,
            "registrant": self.registrant,
            "created": self.created,
            "expires": self.expires,
            "updated": self.updated,
            "nameservers": list(self.nameservers),
            "statuses": list(self.statuses),
        }


@dataclass(frozen=True)
class Result:
    """The outcome of checking one domain."""

    domain: str
    status: Status
    raw: str = ""
    info: Info = field(default_factory=Info)
    attempts: int = 0
    latency: float = 0.0
    error: Optional[str] = None
    dns_confirms_taken: Optional[bool] = None

    @property
    def available(self) -> bool:
        return self.status is Status.AVAILABLE

    @property
    def taken(self) -> bool:
        return self.status is Status.TAKEN

    def __bool__(self) -> bool:
        return self.available

    def __str__(self) -> str:
        return f"{self.domain} [{self.status}]"

    def to_dict(self, include_raw: bool = False) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "domain": self.domain,
            "status": str(self.status),
            "available": self.available,
            "latency": round(self.latency, 3),
            "attempts": self.attempts,
            "error": self.error,
            "registrar": self.info.registrar,
            "registrant": self.info.registrant,
            "created": self.info.created,
            "expires": self.info.expires,
            "nameservers": list(self.info.nameservers),
        }
        if include_raw:
            payload["raw"] = self.raw
        return payload
