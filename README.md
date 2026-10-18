<p align="center">
  <img src="https://raw.githubusercontent.com/mrhamidrezam/irwho/main/assets/banner.svg" alt="irwho — WHOIS toolkit for .ir domains" width="100%">
</p>

<p align="center">
  <strong>Check <code>.ir</code> domain availability, scan hundreds in bulk, and invent brandable names from a few seed words.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/irwho/"><img alt="PyPI" src="https://img.shields.io/pypi/v/irwho.svg?color=3fe0c8"></a>
  <a href="https://pypi.org/project/irwho/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/irwho.svg"></a>
  <a href="https://github.com/mrhamidrezam/irwho/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/mrhamidrezam/irwho/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg"></a>
  <img alt="Dependencies" src="https://img.shields.io/badge/dependencies-zero-blue.svg">
</p>

---

## Why irwho?

Most `.ir` availability tools are either a one-off script or a slow single-domain
lookup. **irwho** is a proper library: you bring a few words, it explores the rest.

- 🧠 **Names from seeds** — give it `["web", "saz"]` and it generates suffixes,
  prefixes, combos and plausible misspellings, then *ranks* them by brandability.
- ⚡ **Bulk + threaded** — scans run on a thread pool with input order preserved.
- 🔄 **Resumable** — interrupted scans pick up exactly where they left off (JSON cache).
- 🕸 **Polite** — one shared rate limiter across all threads, retries with backoff,
  and automatic detection of throttled WHOIS servers.
- ✅ **Cross-checked** — a WHOIS "available" verdict that still resolves in DNS
  is flipped to *taken*, so you don't buy a name that isn't free.
- 🔌 **Zero dependencies** — pure standard library. Python 3.9+.
- ⏳ **Async ready** — `await checker.check_many_async(...)` when you need it.

> WHOIS is never a guarantee. Before paying, always confirm on [nic.ir](https://www.nic.ir/).

## Install

```bash
pip install irwho
```

## 60-second tour

### Check one domain

```python
import irwho

r = irwho.check("websaz")            # ".ir" is appended for you
if r:
    print("probably free:", r.domain)
elif r.taken:
    print("registered since:", r.info.created)
```

### Give it a few names — it explores the rest

```python
import irwho

results = irwho.check_names(
    ["web", "site", "saz", "besaz", "vitrin"],
    limit=100,        # check only the 100 *best* candidates
    delay=0.5,        # stay polite
    workers=4,
)

print("\n".join(r.domain for r in results if r.available))
```

### Invent names without touching the network

```python
import irwho

names = irwho.generate(["web", "saz", "kar"], limit=10)
print(names)                    # best-looking first
irwho.to_domains(names)         # -> ['karweb.ir', 'sazweb.ir', ...]
```

### Resumable bulk scan

```python
import irwho

checker = irwho.Checker(cache=".irwho-cache.json")   # already-checked names are skipped
results = checker.check_many(candidates)

for r in results:
    print(f"{r.domain:<20} {r.status}")
```

### Async

```python
import asyncio, irwho

async def free_domains():
    checker = irwho.Checker(workers=6)
    results = await checker.check_many_async(["a.ir", "b.ir", "c.ir"])
    return [r.domain for r in results if r.available]

print(asyncio.run(free_domains()))
```

## CLI

```bash
irwho web,site,saz,besaz --limit 100        # generate + check the best 100
irwho web,saz --list-only                   # just show candidates, no network
irwho --check webo.ir besazoo.ir            # check exact domains
irwho --words seeds.txt --available-only -o free.csv --format csv
```

```console
$ irwho besazinoo,hamkar --limit 4 --delay 0.7
hamkari.ir      taken       0.20s
hamkaro.ir      taken       0.92s
hamkarha.ir     taken       1.43s
hamkarka.ir     available   1.33s

4 checked - 1 probably free
```

| Flag | Meaning |
| --- | --- |
| `--limit N` | how many candidates to check (default 100) |
| `--delay S` | minimum seconds between WHOIS queries (default 0.5) |
| `--workers N` | parallel threads (default 4) |
| `--retries N` | retries per domain, with backoff (default 2) |
| `--tld ir` | TLD appended to bare names |
| `--server HOST` | any WHOIS server |
| `--no-dns` | skip the DNS cross-check |
| `--no-cache` | ignore the resume cache |
| `--available-only` | print only probably-free domains |
| `--format table\|csv\|json` | output format |
| `-o FILE` | write to a file (UTF-8 with BOM, opens cleanly in Excel) |

## API reference

| Object | Purpose |
| --- | --- |
| `irwho.check(name, **opts)` | check one name → `Result` |
| `irwho.check_many(domains, **opts)` | check many → `list[Result]` (order preserved) |
| `irwho.check_names(seeds, ...)` | generate + check in one call |
| `irwho.generate(seeds, ...)` | ranked candidates from seed words |
| `irwho.to_domains(names, tld)` | attach a TLD |
| `irwho.Checker(...)` | reusable checker: cache, thread pool, DNS check |
| `irwho.WhoisClient(...)` | raw WHOIS transport with retries/backoff |
| `irwho.Cache` | thread-safe JSON cache for resuming scans |
| `irwho.Status` | `AVAILABLE` / `TAKEN` / `UNKNOWN` / `ERROR` |
| `irwho.Result` | `domain`, `status`, `info`, `latency`, `attempts`, `error` |

`Result.info` (`irwho.Info`) exposes `registrar`, `registrant`, `created`,
`expires`, `updated`, `nameservers` and `statuses`.

`Result` is truthy when the domain is available:

```python
if irwho.check("webo"):
    ...
```

## How a verdict is made

1. The WHOIS response is fetched with retries, backoff and a rate limiter.
2. Strong "registered" evidence always wins — `domain name:`, `registrant:`,
   `nserver:`, `registrar:`, `creation date:` …
3. Otherwise availability wording (`no entries found`, `no match`, …) → **probably available**.
4. If WHOIS says free but DNS still resolves the name → **taken**
   (`result.dns_confirms_taken is True`).
5. Everything else stays **unknown**; network failures are **error** — and errors
   are *never* cached, so a re-run always retries them.

## Publishing a new version

```bash
git tag v0.2.0
git push origin v0.2.0
```

That's it — the GitHub Action builds and publishes to PyPI via
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/). No tokens, no passwords.

## Development

```bash
git clone https://github.com/mrhamidrezam/irwho.git
cd irwho
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](https://github.com/mrhamidrezam/irwho/blob/main/LICENSE).
