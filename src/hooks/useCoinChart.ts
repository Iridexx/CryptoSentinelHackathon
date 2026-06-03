import { useState, useEffect } from 'react';
import { type UTCTimestamp } from 'lightweight-charts';

export interface LinePoint { time: UTCTimestamp; value: number }
export interface CandlePoint { time: UTCTimestamp; open: number; high: number; low: number; close: number }

const BASE = 'https://api.coingecko.com/api/v3/coins';

function ohlcDays(days: number): number {
  if (days <= 1) return 1;
  if (days <= 7) return 7;
  if (days <= 30) return 30;
  return 365;
}

export function useCoinChart(
  coinId: string,
  currency: string,
  days: number,
  mode: 'line' | 'candle',
) {
  const [lineData, setLineData] = useState<LinePoint[]>([]);
  const [candleData, setCandleData] = useState<CandlePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!coinId) return;
    let ctrl: AbortController;

    // Debounce 450ms: evita richieste multiple su cambio rapido di timeframe/modalità
    const debounce = setTimeout(() => {
      ctrl = new AbortController();
      setLoading(true);
      setError(false);

      (async () => {
        try {
          if (mode === 'line') {
            const res = await fetch(
              `${BASE}/${coinId}/market_chart?vs_currency=${currency}&days=${days}`,
              { signal: ctrl.signal },
            );
            if (!res.ok) throw new Error();
            const json = await res.json() as { prices: [number, number][] };
            setLineData(json.prices.map(([ts, v]) => ({ time: Math.floor(ts / 1000) as UTCTimestamp, value: v })));
          } else {
            const res = await fetch(
              `${BASE}/${coinId}/ohlc?vs_currency=${currency}&days=${ohlcDays(days)}`,
              { signal: ctrl.signal },
            );
            if (!res.ok) throw new Error();
            const json = await res.json() as [number, number, number, number, number][];
            const seen = new Set<number>();
            const pts: CandlePoint[] = [];
            for (const [ts, o, h, l, c] of json) {
              const t = Math.floor(ts / 1000);
              if (seen.has(t)) continue;
              seen.add(t);
              pts.push({ time: t as UTCTimestamp, open: o, high: h, low: l, close: c });
            }
            setCandleData(pts);
          }
        } catch (e) {
          if ((e as Error).name !== 'AbortError') setError(true);
        } finally {
          if (!ctrl.signal.aborted) setLoading(false);
        }
      })();
    }, 450);

    return () => {
      clearTimeout(debounce);
      ctrl?.abort();
    };
  }, [coinId, currency, days, mode]);

  return { lineData, candleData, loading, error };
}
