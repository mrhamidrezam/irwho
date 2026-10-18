"""Quick tour of irwho.

Run with:  python examples/quickstart.py
"""

import irwho

# 1. invent brandable names from a few words - no network needed
candidates = irwho.generate(["web", "site", "saz", "besaz"], limit=15)
print("candidates:", ", ".join(candidates))

# 2. check the best ones (be polite: small delay, few workers)
checker = irwho.Checker(tld="ir", delay=0.6, workers=3, cache=".irwho-cache.json")


def on_result(result, done, total):
    if result.available:
        print(f"[{done}/{total}] FREE? {result.domain}")


results = checker.check_many(candidates, on_result=on_result)

# 3. summarize
free = [r for r in results if r.available]
print(f"\nchecked {len(results)} domains, {len(free)} probably free")
for r in free:
    print("  ", r.domain)
