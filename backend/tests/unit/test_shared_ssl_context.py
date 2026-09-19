"""Contesto TLS condiviso per i client httpx.

Un `httpx.AsyncClient()` senza `verify=` costruisce un contesto SSL nuovo: ~2 secondi di
lavoro sul thread dell'event loop (sull'hardware di produzione, OpenSSL 3.0 su Windows), a
ogni richiesta. Il backend restava bloccato quasi di continuo e `/health/live` rispondeva in
secondi. Qui si congela la regola: ogni client passa lo stesso contesto.
"""

from __future__ import annotations

import re
import ssl
from pathlib import Path

import httpx

from backend.app.core.tls import shared_ssl_context

APP_DIR = Path(__file__).resolve().parents[2] / "app"


def test_shared_ssl_context_is_built_once_and_reused() -> None:
    first = shared_ssl_context()
    assert isinstance(first, ssl.SSLContext)
    assert shared_ssl_context() is first


def test_shared_ssl_context_verifies_certificates() -> None:
    ctx = shared_ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_client_with_shared_context_is_cheap_to_create() -> None:
    shared_ssl_context()  # la prima costruzione e' costosa, poi il costo per client e' irrisorio
    import time

    started = time.perf_counter()
    for _ in range(20):
        httpx.AsyncClient(timeout=5, verify=shared_ssl_context())
    assert time.perf_counter() - started < 1.0


def test_every_async_client_in_app_uses_the_shared_context() -> None:
    offenders: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        if path.name == "tls.py":  # la docstring del modulo cita httpx.AsyncClient() come esempio
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"httpx\.AsyncClient\(", text):
            # la chiamata puo' andare a capo: si guarda fino alla parentesi che la chiude
            depth, end = 0, match.end() - 1
            for index in range(match.end() - 1, len(text)):
                if text[index] == "(":
                    depth += 1
                elif text[index] == ")":
                    depth -= 1
                    if depth == 0:
                        end = index
                        break
            if "verify=" not in text[match.start() : end + 1]:
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(APP_DIR)}:{line}")
    assert not offenders, (
        "httpx.AsyncClient senza verify=shared_ssl_context() (blocca l'event loop ~2 s a chiamata): "
        + ", ".join(offenders)
    )
