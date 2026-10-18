from __future__ import annotations

from dataclasses import replace

from irwho import __version__
from irwho.cache import Cache
from irwho.checker import Checker
from irwho.models import Result, Status


def test_version_is_semver():
    parts = __version__.split(".")
    assert len(parts) == 3 and all(part.isdigit() for part in parts)


def test_result_truthiness():
    free = Result(domain="a.ir", status=Status.AVAILABLE)
    taken = Result(domain="b.ir", status=Status.TAKEN)
    assert bool(free) is True
    assert bool(taken) is False
    assert free.available and taken.taken
    assert str(free) == "a.ir [available]"


def test_result_to_dict_roundtrip_fields():
    payload = Result(domain="a.ir", status=Status.AVAILABLE, latency=0.123).to_dict()
    assert payload["domain"] == "a.ir"
    assert payload["status"] == "available"
    assert payload["available"] is True
    assert "raw" not in payload
    assert "raw" in Result(domain="a.ir", status=Status.ERROR).to_dict(include_raw=True)


def test_cache_put_get_and_persistence(tmp_path):
    path = tmp_path / "cache.json"
    cache = Cache(path)
    cache.put("a.ir", Status.TAKEN)
    cache.put("b.ir", Status.AVAILABLE)

    reloaded = Cache(path)
    assert reloaded.get("a.ir") is Status.TAKEN
    assert reloaded.get("b.ir") is Status.AVAILABLE
    assert reloaded.get("c.ir") is None
    assert len(reloaded) == 2


def test_cache_never_stores_errors(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    cache.put("broken.ir", Status.ERROR)
    assert cache.get("broken.ir") is None


def test_cache_survives_corrupt_file(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{ not json", encoding="utf-8")
    assert len(Cache(path)) == 0


def test_cache_prune(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    cache.put("old.ir", Status.TAKEN)
    assert cache.prune(max_age=-1) == 1
    assert cache.get("old.ir") is None


def test_checker_domain_for():
    checker = Checker(tld="ir")
    assert checker.domain_for("webo") == "webo.ir"
    assert checker.domain_for("example.com") == "example.com"


def test_checker_uses_cache_and_skips_network(tmp_path, monkeypatch):
    cache = Cache(tmp_path / "cache.json")
    cache.put("webo.ir", Status.AVAILABLE)

    checker = Checker(cache=cache)

    def boom(domain):  # pragma: no cover - must never run
        raise AssertionError("network should not be touched")

    monkeypatch.setattr(checker.client, "lookup", boom)
    result = checker.check("webo")
    assert result.available
    assert result.attempts == 0


def test_checker_dns_cross_check_overrides_available(tmp_path, monkeypatch):
    checker = Checker(cache=tmp_path / "cache.json")
    monkeypatch.setattr(
        checker.client,
        "lookup",
        lambda domain: Result(domain=domain, status=Status.AVAILABLE, raw="free"),
    )
    monkeypatch.setattr("irwho.checker._resolves", lambda domain: True)
    result = checker.check("webo")
    assert result.status is Status.TAKEN
    assert result.dns_confirms_taken is True


def test_check_many_preserves_order(monkeypatch):
    checker = Checker(cache=None, workers=3)
    monkeypatch.setattr(
        checker.client,
        "lookup",
        lambda domain: Result(domain=domain, status=Status.TAKEN, raw="taken"),
    )
    results = checker.check_many(["c.ir", "a.ir", "b.ir"])
    assert [r.domain for r in results] == ["c.ir", "a.ir", "b.ir"]


def test_check_many_reports_progress(monkeypatch):
    checker = Checker(cache=None)
    monkeypatch.setattr(
        checker.client,
        "lookup",
        lambda domain: Result(domain=domain, status=Status.TAKEN, raw="taken"),
    )
    seen = []
    checker.check_many(["a.ir", "b.ir"], progress=lambda done, total: seen.append((done, total)))
    assert seen == [(1, 2), (2, 2)]


def test_check_many_empty_input():
    assert Checker().check_many([]) == []


def test_result_replace_keeps_frozen():
    result = Result(domain="a.ir", status=Status.AVAILABLE)
    updated = replace(result, status=Status.TAKEN)
    assert updated.status is Status.TAKEN
    assert result.status is Status.AVAILABLE
