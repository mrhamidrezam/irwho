"""irwho - a fast, friendly WHOIS toolkit for .ir domains.

Quick start::

    import irwho

    result = irwho.check("webo")
    if result:
        print("probably free:", result.domain)

    candidates = irwho.generate(["web", "site", "saz"], limit=50)
    free = [r.domain for r in irwho.check_many(candidates) if r.available]
"""

from __future__ import annotations

from .cache import Cache
from .checker import Checker, check, check_many, check_names
from .models import Info, Result, Status
from .namer import generate, normalize, score, to_domains
from .whois import WhoisClient

__version__ = "0.1.1"

__all__ = [
    "Cache",
    "Checker",
    "Info",
    "Result",
    "Status",
    "WhoisClient",
    "__version__",
    "check",
    "check_many",
    "check_names",
    "generate",
    "normalize",
    "score",
    "to_domains",
]
