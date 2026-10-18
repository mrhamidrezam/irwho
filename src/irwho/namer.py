"""Turn a handful of seed words into hundreds of brandable domain candidates."""

from __future__ import annotations

import itertools
import re
from typing import Iterable, List, Optional, Sequence, Set

VOWELS = "aeiou"

#: Persian/English friendly endings: ``web`` -> ``webo``, ``webino``, ...
SUFFIXES: Sequence[str] = (
    "o", "oo", "i", "y", "in", "ino", "inoo", "ak", "eh", "an", "na",
    "ya", "chi", "kar", "sho", "ha", "ka", "va", "li", "er", "ify",
    "io", "ia", "us", "or", "z", "s", "ez", "an",
)

#: Prefixes that read naturally before Persian-ish roots.
PREFIXES: Sequence[str] = (
    "my", "be", "na", "ra", "go", "ham", "dig", "av", "tik", "no",
    "pro", "top", "best", "new", "next", "max", "one", "up", "hey", "ino",
)

_JOINERS = ("a", "e", "i", "o")
_NAME_RE = re.compile(r"^[a-z]{3,15}$")
_TRIPLE_LETTER = re.compile(r"(.)\1\1")
_DOUBLE_VOWEL = re.compile(r"[aeiou]{2}")
_LONG_CONSONANTS = re.compile(r"[bcdfghjklmnpqrstvwxyz]{3,}")


def normalize(name: str) -> Optional[str]:
    """Return a clean lowercase ASCII name, or ``None`` if unusable."""
    cleaned = re.sub(r"[^a-z0-9-]", "", str(name).strip().lower())
    return cleaned if _NAME_RE.fullmatch(cleaned) else None


def score(name: str) -> float:
    """Rough "how brandable is this" score. Higher is better."""
    n = len(name)
    if n == 0:
        return 0.0

    value = 0.0
    # sweet spot: 5-9 characters
    value += max(0.0, 14 - abs(n - 7) * 1.5)

    vowel_ratio = sum(c in VOWELS for c in name) / n
    value += 12 * (1 - min(1.0, abs(vowel_ratio - 0.42) / 0.5))

    value -= 8 * len(_LONG_CONSONANTS.findall(name))     # webzshop style clusters
    value -= 6 * len(re.findall(r"([a-z])\1", name))     # doubled letters
    value -= 10 * len(_DOUBLE_VOWEL.findall(name))       # aa/ee/oo... rarely nice
    value -= 8 * (len(set(name)) / n < 0.5)              # too repetitive

    if name[-1] in VOWELS:
        value += 3
    if name[0] in VOWELS:
        value -= 2
    if _TRIPLE_LETTER.search(name):
        value -= 20

    return round(value, 2)


def _valid(name: str, min_len: int, max_len: int) -> bool:
    return (
        bool(_NAME_RE.fullmatch(name))
        and min_len <= len(name) <= max_len
        and not _TRIPLE_LETTER.search(name)
        and not _DOUBLE_VOWEL.search(name)
    )


def _mutate(name: str) -> Set[str]:
    """Small orthographic variations of an already generated name."""
    out: Set[str] = set()
    if len(name) >= 4 and not name.endswith(("s", "z")):
        out.add(name + "s")
        out.add(name + "z")
    if len(name) >= 5 and name[-1] not in VOWELS:
        out.add(name + name[-1])          # web -> webb
    if len(name) >= 6 and name[-1] in VOWELS:
        out.add(name[:-1])                # webo -> web
    if "oo" in name:
        out.add(name.replace("oo", "o"))
    if "ee" in name:
        out.add(name.replace("ee", "e"))
    return out


def generate(
    seeds: Iterable[str],
    *,
    suffixes: Sequence[str] = SUFFIXES,
    prefixes: Sequence[str] = PREFIXES,
    combine: bool = True,
    mutate: bool = True,
    min_len: int = 3,
    max_len: int = 13,
    limit: Optional[int] = None,
) -> List[str]:
    """Build domain candidates from a few seed words.

    ``seeds`` may be as small as ``["web", "saz"]``; irwho then explores
    suffixes, prefixes, combinations and simple misspellings, filters out
    the ugly ones and ranks the rest by :func:`score`.

    The best (highest scoring) names come first, so ``limit`` keeps the
    most promising ones.
    """
    cleaned = [normalize(seed) for seed in seeds]
    unique = list(dict.fromkeys(seed for seed in cleaned if seed))
    if not unique:
        raise ValueError("no usable seed names (use 3-15 latin letters)")

    names: Set[str] = set(unique)

    for seed in unique:
        for suffix in suffixes:
            names.add(seed + suffix)
        for prefix in prefixes:
            names.add(prefix + seed)

    if combine:
        for a, b in itertools.permutations(unique, 2):
            names.add(a + b)
            for joiner in _JOINERS:
                names.add(a + joiner + b)

    if mutate:
        extra: Set[str] = set()
        for name in names:
            extra |= _mutate(name)
        names |= extra

    candidates = [name for name in names if _valid(name, min_len, max_len)]
    candidates.sort(key=lambda n: (-score(n), len(n), n))
    return candidates[:limit] if limit else candidates


def to_domains(names: Iterable[str], tld: str = "ir") -> List[str]:
    """Attach a TLD to bare names (already qualified names pass through)."""
    tld = tld.lstrip(".")
    domains: List[str] = []
    for name in names:
        name = str(name).strip().lower()
        if not name:
            continue
        domains.append(name if "." in name else f"{name}.{tld}")
    return domains
