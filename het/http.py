"""Polite HTTP fetching with an on-disk cache.

Detail pages are ~60 KB each and rarely change, so caching keeps re-runs
instant and keeps us off the source's servers. Every request is throttled and
identifies itself honestly in the User-Agent.
"""

from __future__ import annotations

import hashlib
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = (
    "HigherEducationTracker/0.1 (personal study-planning tool; "
    "contact: local user)"
)

# Deployed installs keep code and state apart, so both are overridable.
CACHE_DIR = Path(os.environ.get("HET_CACHE_DIR")
                 or Path(__file__).resolve().parent.parent / "data" / "cache")
MIN_INTERVAL = 0.7  # seconds between requests to the same host

_last_request: dict[str, float] = {}

# Point at a PEM bundle when the platform trust store is missing a root.
CA_BUNDLE = os.environ.get("HET_CA_BUNDLE")


class CertificateTrustError(Exception):
    """The server's certificate chain could not be verified locally.

    Raised instead of the bare SSL error because the cause is almost never the
    source being untrustworthy — it is the local trust store lacking a root.
    Study in NL, for instance, chains to HARICA (a Greek academic CA) which
    Linux distributions ship but Windows only fetches on demand, so the same
    ingest succeeds on the server and fails on a Windows laptop.
    """

    def __init__(self, url: str):
        host = urllib.parse.urlparse(url).netloc
        super().__init__(
            f"{host} sertifikası doğrulanamadı — bu makinenin kök sertifika "
            f"deposunda ilgili kök yok (kaynakta bir sorun olduğu anlamına "
            f"gelmez).\n"
            f"  • Sunucuda (Linux) çalıştırırsan sorun çıkmaz.\n"
            f"  • Ya da bir PEM paketi göstererek: HET_CA_BUNDLE=/yol/ca.pem\n"
            f"Doğrulama kapatılmıyor; kapatılması da gerekmez."
        )


def _ssl_context() -> ssl.SSLContext:
    if CA_BUNDLE:
        return ssl.create_default_context(cafile=CA_BUNDLE)
    return ssl.create_default_context()


def _throttle(url: str) -> None:
    host = urllib.parse.urlparse(url).netloc
    elapsed = time.monotonic() - _last_request.get(host, 0.0)
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_request[host] = time.monotonic()


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return CACHE_DIR / digest[:2] / f"{digest}.cache"


def fetch(url: str, *, max_age: float | None = 7 * 24 * 3600,
          timeout: int = 30) -> str:
    """GET `url` as text, using the disk cache when the entry is fresh enough.

    `max_age=None` disables cache reads (but still writes), which is what a
    forced refresh uses.
    """
    path = _cache_path(url)
    if max_age is not None and path.exists():
        if time.time() - path.stat().st_mtime < max_age:
            return path.read_text(encoding="utf-8")

    _throttle(url)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Language": "en",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=_ssl_context()) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise CertificateTrustError(url) from exc
        raise

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return body


def build_url(base: str, params: dict) -> str:
    return base + "?" + urllib.parse.urlencode(params, doseq=True)
