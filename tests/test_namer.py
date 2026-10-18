from __future__ import annotations

import pytest

from irwho.namer import SUFFIXES, generate, normalize, score, to_domains


def test_generate_includes_seed_and_suffixes():
    names = generate(["web"], combine=False, mutate=False)
    assert "web" in names
    assert "webo" in names
    assert "webino" in names


def test_generate_builds_combos_from_two_seeds():
    names = generate(["web", "saz"], mutate=False)
    assert "websaz" in names
    assert "sazaweb" in names  # joiner variant


def test_generate_filters_bad_names():
    names = generate(["web", "site"], max_len=13)
    for name in names:
        assert 3 <= len(name) <= 13
        assert name.isalpha() and name.islower()
        assert "aa" not in name and "ee" not in name and "oo" not in name


def test_generate_is_sorted_by_score():
    names = generate(["web", "saz"], limit=30)
    scores = [score(name) for name in names]
    assert scores == sorted(scores, reverse=True)


def test_generate_limit():
    assert len(generate(["web", "saz"], limit=5)) == 5


def test_generate_rejects_unusable_seeds():
    with pytest.raises(ValueError):
        generate(["", "12", "??"])


def test_generate_deduplicates_and_is_deterministic():
    first = generate(["web", "web", "saz"])
    second = generate(["web", "saz"])
    assert first == second
    assert len(first) == len(set(first))


def test_normalize():
    assert normalize("  WebO ") == "webo"
    assert normalize("a-b") is None  # hyphen is not allowed by the strict name rule
    assert normalize("!!") is None
    assert normalize("python") == "python"


def test_to_domains():
    assert to_domains(["webo", "besaz.ir"]) == ["webo.ir", "besaz.ir"]
    assert to_domains(["webo"], tld=".ir") == ["webo.ir"]


def test_score_prefers_reasonable_names():
    assert score("webo") > score("wzzqk")
