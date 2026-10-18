from __future__ import annotations

from irwho.models import Info, Status
from irwho.whois import WhoisClient

IRNIC_TAKEN = """
% IRNIC Whois Server
domain:		websaz.ir
nserver:	ns1.example.com
nserver:	ns2.example.com
registrant:	Example Company
admin:		admin@example.com
created:	2005-10-16
expire:		2026-10-16
source:		IRNIC
"""

IRNIC_FREE = """
% Info: No entries found for the selected source(s).
"""

GENERIC_TAKEN = """
Domain Name: example.com
Registry Domain ID: 123
Registrar: Example Registrar, LLC
Creation Date: 2000-01-01T00:00:00Z
Registry Expiry Date: 2030-01-01T00:00:00Z
Name Server: NS1.EXAMPLE.COM
Domain Status: clientTransferProhibited
"""


def test_classify_taken_irnic():
    assert WhoisClient.classify(IRNIC_TAKEN) is Status.TAKEN


def test_classify_taken_generic():
    assert WhoisClient.classify(GENERIC_TAKEN) is Status.TAKEN


def test_classify_available():
    assert WhoisClient.classify(IRNIC_FREE) is Status.AVAILABLE


def test_classify_empty_is_error():
    assert WhoisClient.classify("") is Status.ERROR
    assert WhoisClient.classify("   ") is Status.ERROR


def test_classify_throttled_is_error():
    assert WhoisClient.classify("Too many queries, try again later") is Status.ERROR


def test_classify_unknown():
    assert WhoisClient.classify("something unexpected") is Status.UNKNOWN


def test_taken_wins_over_availability_wording():
    text = "not found elsewhere\nregistrant: Someone"
    assert WhoisClient.classify(text) is Status.TAKEN


def test_info_parses_irnic_record():
    info = Info.from_text(IRNIC_TAKEN)
    assert info.domain == "websaz.ir"
    assert info.registrant == "Example Company"
    assert info.created == "2005-10-16"
    assert info.expires == "2026-10-16"
    assert info.nameservers == ("ns1.example.com", "ns2.example.com")


def test_info_parses_generic_record():
    info = Info.from_text(GENERIC_TAKEN)
    assert info.registrar == "Example Registrar, LLC"
    assert info.expires == "2030-01-01T00:00:00Z"
    assert info.statuses == ("clientTransferProhibited",)
    assert info.nameservers == ("ns1.example.com",)


def test_info_parses_empty_text():
    info = Info.from_text("")
    assert info.domain is None
    assert info.nameservers == ()


def test_encode_query_ascii():
    assert WhoisClient._encode_query("webo.ir") == b"webo.ir\r\n"


def test_encode_query_punycode():
    assert WhoisClient._encode_query("café.ir") == b"xn--caf-dma.ir\r\n"


def _client(**kwargs):
    kwargs.setdefault("retries", 2)
    kwargs.setdefault("backoff", 0)
    kwargs.setdefault("delay", 0)
    return WhoisClient(**kwargs)


def test_query_retries_until_success(monkeypatch):
    client = _client()
    calls = []

    def flaky(domain):
        calls.append(domain)
        if len(calls) < 3:
            raise OSError("connection reset")
        return "no entries found"

    monkeypatch.setattr(client, "_query_once", flaky)
    text, attempts, error = client.query("a.ir")
    assert text == "no entries found"
    assert attempts == 3
    assert error is None


def test_query_gives_up_with_error(monkeypatch):
    client = _client(retries=1)

    def down(domain):
        raise OSError("server down")

    monkeypatch.setattr(client, "_query_once", down)
    text, attempts, error = client.query("a.ir")
    assert text == ""
    assert attempts == 2
    assert "OSError" in error


def test_throttled_response_is_retried(monkeypatch):
    client = _client(retries=1)
    calls = []

    def fake(domain):
        calls.append(domain)
        return "Too many queries, try again later" if len(calls) == 1 else "no entries found"

    monkeypatch.setattr(client, "_query_once", fake)
    text, attempts, error = client.query("a.ir")
    assert text == "no entries found"
    assert attempts == 2
    assert error is None


def test_lookup_never_raises(monkeypatch):
    client = _client()

    def boom(domain):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(client, "query", boom)
    result = client.lookup("a.ir")
    assert result.status is Status.ERROR
    assert "RuntimeError" in result.error
