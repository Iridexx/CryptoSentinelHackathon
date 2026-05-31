import { useState, useEffect, useCallback, useRef } from 'react';
import type { Coin } from '../types';

const CACHE_KEY = 'cryptosentinel_coins_cache';

function buildUrl(perPage: 50 | 100, page: number, currency: string): string {
  return `https://api.coingecko.com/api/v3/coins/markets?vs_currency=${currency}&order=market_cap_desc&per_page=${perPage}&page=${page}&sparkline=false&price_change_percentage=1h,24h,7d`;
}

function loadCachedCoins(): Coin[] {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as Coin[];
  } catch {
    return [];
  }
}

export function useCryptoData(intervalMs = 30_000, perPage: 50 | 100 = 50, page = 1, currency = 'usd') {
  const [coins, setCoins] = useState<Coin[]>(() => page === 1 ? loadCachedCoins() : []);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchCoins = useCallback(async () => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      const res = await fetch(buildUrl(perPage, page, currency), { signal: abortRef.current.signal });
      if (!res.ok) throw new Error(`Errore API: ${res.status}`);
      const data: Coin[] = await res.json();
      setCoins(data);
      setError(null);
      setLastUpdated(new Date());
      if (page === 1) {
        try { localStorage.setItem(CACHE_KEY, JSON.stringify(data)); } catch { /* quota */ }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      setError('Impossibile caricare i prezzi. Dati dalla cache.');
    } finally {
      setLoading(false);
    }
  }, [perPage, page, currency]);

  // Manual refresh: reset the auto-refresh timer first to prevent it from
  // aborting the in-flight fetch immediately after this call.
  const refresh = useCallback(async () => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = setInterval(fetchCoins, intervalMs);
    }
    await fetchCoins();
  }, [fetchCoins, intervalMs]);

  useEffect(() => {
    setLoading(true);
    fetchCoins();
    timerRef.current = setInterval(fetchCoins, intervalMs);
    return () => {
      if (timerRef.current !== null) clearInterval(timerRef.current);
      timerRef.current = null;
      abortRef.current?.abort();
    };
  }, [fetchCoins, intervalMs]);

  return { coins, loading, error, lastUpdated, refresh };
}
