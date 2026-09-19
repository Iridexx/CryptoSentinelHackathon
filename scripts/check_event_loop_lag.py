"""Misura quanto l'event loop del backend resta bloccato.

Interroga /health/live (che non fa nulla) ogni 0,2 s: se il loop e' libero risponde in pochi
millisecondi, se qualcosa lo blocca le risposte arrivano in secondi. Serve a distinguere un
backend "lento" per le query da uno con il loop bloccato (vedi backend/app/core/tls.py).

Uso:  python scripts/check_event_loop_lag.py [secondi] [url]
"""

from __future__ import annotations

import sys
import time
import urllib.request


def main() -> None:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    url = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8001/health/live"
    latencies: list[float] = []
    end = time.time() + seconds
    while time.time() < end:
        started = time.time()
        try:
            urllib.request.urlopen(url, timeout=60).read()
        except Exception as exc:  # noqa: BLE001 - diagnostica: un errore conta come risposta lenta
            print(f"errore: {exc}")
        latencies.append(time.time() - started)
        time.sleep(0.2)
    ordered = sorted(latencies)
    print(
        f"richieste {len(ordered)} | mediana {ordered[len(ordered) // 2] * 1000:.0f} ms | "
        f"p95 {ordered[int(len(ordered) * 0.95) - 1] * 1000:.0f} ms | max {ordered[-1]:.2f} s | "
        f"sopra 0,5 s: {sum(1 for v in ordered if v > 0.5)} | sopra 2 s: {sum(1 for v in ordered if v > 2)}"
    )


if __name__ == "__main__":
    main()
