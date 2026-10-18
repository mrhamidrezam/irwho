"""Command line interface: ``irwho web,site,saz --limit 100``."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from . import __version__
from .checker import Checker
from .models import Result, Status
from .namer import generate, to_domains

_COLORS = {
    Status.AVAILABLE: "\033[32m",
    Status.TAKEN: "\033[2m",
    Status.UNKNOWN: "\033[33m",
    Status.ERROR: "\033[31m",
}
_RESET = "\033[0m"
_BOLD = "\033[1m"


def _supports_color() -> bool:
    return (
        sys.stdout.isatty()
        and not os.environ.get("NO_COLOR")
        and os.environ.get("TERM") != "dumb"
    )


def _paint(text: str, status: Status, *, color: bool) -> str:
    if not color:
        return text
    return f"{_COLORS.get(status, '')}{text}{_RESET}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="irwho",
        description="WHOIS toolkit for .ir domains: check availability, "
        "scan in bulk and invent brandable names from a few seed words.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  irwho web,saz,besaz --limit 100\n"
            "  irwho --check webo.ir besazoo.ir\n"
            "  irwho --words seeds.txt --available-only --format csv -o free.csv\n"
            "  irwho web,saz --list-only\n"
        ),
    )
    parser.add_argument(
        "names",
        nargs="*",
        help="seed words (comma or space separated) or, with --check, domains",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="treat the given arguments as domains and skip name generation",
    )
    parser.add_argument(
        "--words",
        metavar="FILE",
        action="append",
        default=[],
        help="read extra seed words from a file, one per line (repeatable)",
    )

    gen = parser.add_argument_group("name generation")
    gen.add_argument("--tld", default="ir", help="TLD to append (default: ir)")
    gen.add_argument("--limit", type=int, default=100, help="max candidates to check")
    gen.add_argument("--min-len", type=int, default=4)
    gen.add_argument("--max-len", type=int, default=13)
    gen.add_argument("--no-combine", action="store_true", help="do not glue seeds together")
    gen.add_argument("--no-mutate", action="store_true", help="skip spelling variations")
    gen.add_argument(
        "--list-only", action="store_true", help="only print candidates, do no network I/O"
    )

    net = parser.add_argument_group("network")
    net.add_argument("--server", default="whois.nic.ir", help="WHOIS server")
    net.add_argument("--delay", type=float, default=0.5, help="min seconds between queries")
    net.add_argument("--retries", type=int, default=2)
    net.add_argument("--timeout", type=float, default=8.0)
    net.add_argument("--workers", type=int, default=4)
    net.add_argument("--no-dns", action="store_true", help="skip the DNS cross-check")

    out = parser.add_argument_group("output")
    out.add_argument("--format", choices=("table", "csv", "json"), default="table")
    out.add_argument("-o", "--out", metavar="FILE", help="write results to a file")
    out.add_argument("--available-only", action="store_true")
    out.add_argument("--cache", metavar="FILE", default=".irwho-cache.json")
    out.add_argument("--no-cache", action="store_true", help="do not resume from the cache")
    out.add_argument("-v", "--verbose", action="store_true", help="include raw WHOIS text")
    parser.add_argument("--version", action="version", version=f"irwho {__version__}")
    return parser


def _collect_seeds(args: argparse.Namespace) -> List[str]:
    seeds: List[str] = []
    for chunk in list(args.names) + [
        Path(path).read_text(encoding="utf-8") for path in args.words
    ]:
        seeds.extend(str(chunk).replace(",", " ").split())
    return seeds


def _print_table(results: Sequence[Result], color: bool) -> None:
    if not results:
        print("no results")
        return
    width = max(len(r.domain) for r in results)
    if color:
        print(_BOLD + f"{'DOMAIN'.ljust(width)}  {'STATUS':<10}  TIME" + _RESET)
    else:
        print(f"{'DOMAIN'.ljust(width)}  {'STATUS':<10}  TIME")
    for result in results:
        line = (
            f"{result.domain.ljust(width)}  "
            f"{str(result.status):<10}  "
            f"{result.latency:.2f}s"
        )
        print(_paint(line, result.status, color=color))
    available = sum(1 for r in results if r.available)
    print(f"\n{len(results)} checked - {available} probably free")


def _write_csv(results: Sequence[Result], handle) -> None:
    writer = csv.DictWriter(
        handle, fieldnames=["domain", "status", "latency", "attempts", "expires", "error"]
    )
    writer.writeheader()
    for result in results:
        writer.writerow(
            {
                "domain": result.domain,
                "status": str(result.status),
                "latency": round(result.latency, 3),
                "attempts": result.attempts,
                "expires": result.info.expires or "",
                "error": result.error or "",
            }
        )


def _emit(results: Sequence[Result], args: argparse.Namespace, color: bool) -> None:
    if args.available_only:
        results = [r for r in results if r.available]

    handle = open(args.out, "w", encoding="utf-8-sig", newline="") if args.out else sys.stdout
    try:
        if args.format == "table":
            _print_table(results, color)
        elif args.format == "csv":
            _write_csv(results, handle)
        else:
            payload = [r.to_dict(include_raw=args.verbose) for r in results]
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    finally:
        if args.out:
            handle.close()
            print(f"saved {len(results)} rows to {args.out}")


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles
    except (AttributeError, OSError):
        pass

    color = _supports_color()

    if args.check:
        domains = to_domains(_collect_seeds(args), tld=args.tld)
        if not domains:
            print("nothing to check", file=sys.stderr)
            return 2
        checker = Checker(
            tld=args.tld,
            server=args.server,
            delay=args.delay,
            retries=args.retries,
            timeout=args.timeout,
            workers=args.workers,
            verify_dns=not args.no_dns,
            cache=None if args.no_cache else args.cache,
        )
        print(f"checking {len(domains)} domain(s)...", file=sys.stderr)
        _emit(
            checker.check_many(
                domains,
                on_result=lambda r, done, total: print(
                    f"[{done}/{total}] {r.domain} {r.status}", file=sys.stderr
                )
                if r.available or r.status is Status.ERROR
                else None,
            ),
            args,
            color,
        )
        return 0

    seeds = _collect_seeds(args)
    try:
        candidates = generate(
            seeds,
            min_len=args.min_len,
            max_len=args.max_len,
            combine=not args.no_combine,
            mutate=not args.no_mutate,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.list_only:
        for name in candidates[: args.limit]:
            print(name)
        print(f"\n{len(candidates)} candidates, showing {min(args.limit, len(candidates))}")
        return 0

    checker = Checker(
        tld=args.tld,
        server=args.server,
        delay=args.delay,
        retries=args.retries,
        timeout=args.timeout,
        workers=args.workers,
        verify_dns=not args.no_dns,
        cache=None if args.no_cache else args.cache,
    )
    print(
        f"checking the best {min(args.limit, len(candidates))} of "
        f"{len(candidates)} candidates...",
        file=sys.stderr,
    )
    results = checker.check_many(
        candidates,
        limit=args.limit,
        on_result=lambda r, done, total: print(
            f"[{done}/{total}] {r.domain} {r.status}", file=sys.stderr
        )
        if r.available or r.status is Status.ERROR
        else None,
    )
    _emit(results, args, color)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
