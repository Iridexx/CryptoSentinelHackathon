"""Contesto TLS condiviso per i client HTTP.

Creare un `httpx.AsyncClient()` costruisce un contesto SSL nuovo e carica da zero il bundle
dei certificati: su questa macchina (OpenSSL 3.0, Windows) sono ~2 secondi, tutti sul thread
dell'event loop. Con un client per richiesta (kline, RPC, prezzi, fee, Claude...) il backend
restava bloccato quasi di continuo e anche `/health/live` rispondeva in secondi.

Un contesto SSL puo' essere condiviso tra client e thread: si costruisce una volta sola e si
passa come `verify=` a ogni `httpx.AsyncClient`. Stessa configurazione del default di httpx
(bundle certifi), quindi nessun cambio di sicurezza.
"""

from __future__ import annotations

import ssl
from functools import lru_cache

import certifi


@lru_cache(maxsize=1)
def shared_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())
