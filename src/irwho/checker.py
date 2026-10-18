"""High level API: check one domain, many domains, or generated candidates."""

from __future__ import annotations

import asyncio
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Union,
)

from .cache import Cache
from .models import Result, Status
from .whois import WhoisClient

PathLike = Union[str, Path]
Progress = Callable[[int, int], None]
OnResult = Callable[[Result, int, int], None]


def _resolves(domain: str) -> bool:
    """Cheap second opinion: does DNS already know this name?"""
    try:
        socket.getaddrinfo(domain, None)
        return True
    except (socket.gaierror, OSError):
        return False


class Checker:
    """Coordinates WHOIS lookups: retries, caching, DNS cross-check, threads."""

    def __init__(
        self,
        tld: str = "ir",
        server: str = "whois.nic.ir",
        *,
        delay: float = 0.5,
        retries: int = 2,
        timeout: float = 8.0,
        workers: int = 4,
        verify_dns: bool = True,
        cache: Optional[Union[PathLike, Cache]] = None,
    ) -> None:
        self.client = WhoisClient(
            server=server, timeout=timeout, retries=retries, delay=delay
        )
        self.tld = tld.lstrip(".")
        self.workers = max(1, workers)
        self.verify_dns = verify_dns
        if isinstance(cache, Cache):
            self.cache: Optional[Cache] = cache
        elif cache:
            self.cache = Cache(cache)
        else:
            self.cache = None

    # -- single ----------------------------------------------------
    def domain_for(self, name: str) -> str:
        name = str(name).strip().lower()
        return name if "." in name else f"{name}.{self.tld}"

    def check(self, name: str) -> Result:
        """Check a single name or domain. Never raises for network problems."""
        domain = self.domain_for(name)

        if self.cache is not None:
            hit = self.cache.get(domain)
            if hit is not None:
                return Result(domain=domain, status=hit)

        result = self.client.lookup(domain)

        # Second signal: if DNS resolves it, it is registered, whatever
        # the WHOIS text said.
        if self.verify_dns and result.status is Status.AVAILABLE and _resolves(domain):
            result = replace(result, status=Status.TAKEN, dns_confirms_taken=True)

        if self.cache is not None:
            self.cache.put(domain, result.status)
        return result

    # -- many ------------------------------------------------------
    def check_many(
        self,
        domains: Iterable[str],
        *,
        limit: Optional[int] = None,
        on_result: Optional[OnResult] = None,
        progress: Optional[Progress] = None,
    ) -> List[Result]:
        """Check many names, keeping the input order.

        ``on_result(result, done, total)`` fires as each lookup finishes
        (out of order) - handy for printing available domains live.
        ``progress(done, total)`` is the same idea with just the counters.
        """
        items = [str(d).strip().lower() for d in domains if str(d).strip()]
        if limit:
            items = items[:limit]
        if not items:
            return []

        results: List[Optional[Result]] = [None] * len(items)
        done = 0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            future_map = {pool.submit(self.check, d): i for i, d in enumerate(items)}
            for future in as_completed(future_map):
                index = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:  # pragma: no cover - defensive
                    result = Result(
                        domain=items[index],
                        status=Status.ERROR,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                results[index] = result
                done += 1
                if on_result is not None:
                    on_result(result, done, len(items))
                if progress is not None:
                    progress(done, len(items))

        return [r for r in results if r is not None]

    async def check_many_async(
        self,
        domains: Iterable[str],
        *,
        limit: Optional[int] = None,
        workers: Optional[int] = None,
    ) -> List[Result]:
        """Async flavour of :meth:`check_many` (order preserved)."""
        items = [str(d).strip().lower() for d in domains if str(d).strip()]
        if limit:
            items = items[:limit]
        if not items:
            return []

        loop = asyncio.get_running_loop()
        semaphore = asyncio.Semaphore(workers or self.workers)

        async def run(domain: str) -> Result:
            async with semaphore:
                return await loop.run_in_executor(None, self.check, domain)

        return list(await asyncio.gather(*(run(d) for d in items)))

    # -- generate + check -----------------------------------------
    def check_names(
        self,
        seeds: Iterable[str],
        *,
        limit: Optional[int] = None,
        generate_options: Optional[Dict[str, Any]] = None,
        on_result: Optional[OnResult] = None,
        progress: Optional[Progress] = None,
    ) -> List[Result]:
        """Generate candidates from ``seeds`` and check the best ``limit``."""
        from .namer import generate

        candidates = generate(seeds, **(generate_options or {}))
        return self.check_many(candidates, limit=limit, on_result=on_result, progress=progress)


# -- module level shortcuts ---------------------------------------
def check(name: str, **options: Any) -> Result:
    """``irwho.check("webo")`` -> :class:`Result`."""
    return Checker(**options).check(name)


def check_many(domains: Iterable[str], **options: Any) -> List[Result]:
    """``irwho.check_many(["a.ir", "b.ir"])`` -> list of :class:`Result`."""
    return Checker(**options).check_many(domains)


def check_names(
    seeds: Iterable[str],
    *,
    tld: str = "ir",
    limit: Optional[int] = None,
    generate_options: Optional[Dict[str, Any]] = None,
    **options: Any,
) -> List[Result]:
    """Generate from ``seeds`` then check. One call, one list of results."""
    return Checker(tld=tld, **options).check_names(
        seeds, limit=limit, generate_options=generate_options
    )
