import { useState, useEffect, useCallback, useRef } from 'react';
import type { Coin } from '../types';

export type PerPage = 50 | 100 | 200 | 400 | 600;

const CACHE_KEY = 'cryptosentinel_coins_cache';
const API_CHUNK = 200;

function buildUrl(perPage: number, page: number, currency: string): string {
  return `https://api.coingecko.com/api/v3/coins/markets?vs_currency=${currency}&order=market_cap_desc&per_page=${perPage}&page=${page}&sparkline=false&price_change_percentage=1h,24h,7d`;
}

async function fetchCoinsAll(perPage: PerPage, page: number, currency: string, signal: AbortSignal): Promise<Coin[]> {
  if (perPage <= API_CHUNK) {
    const res = await fetch(buildUrl(perPage, page, currency), { signal });
    if (!res.ok) throw new Error(`Errore API: ${res.status}`);
    return res.json();
  }

  // Split into parallel chunks of API_CHUNK
  const numChunks = Math.ceil(perPage / API_CHUNK);
  const baseApiPage = (page - 1) * numChunks;
  const chunks: Array<{ size: number; apiPage: number }> = [];
  let remaining = perPage;
  for (let i = 0; i < numChunks; i++) {
    chunks.push({ size: Math.min(remaining, API_CHUNK), apiPage: baseApiPage + i + 1 });
    remaining -= API_CHUNK;
  }

  const results = await Promise.all(
    chunks.map(({ size, apiPage }) =>
      fetch(buildUrl(size, apiPage, currency), { signal }).then(r => {
        if (!r.ok) throw new Error(`Errore API: ${r.status}`);
        return r.json() as Promise<Coin[]>;
      })
    )
  );

  return results.flat();
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

export function useCryptoData(intervalMs = 30_000, perPage: PerPage = 50, page = 1, currency = 'usd') {
  const [coins, setCoins] = useState<Coin[]>(() => page === 1 ? loadCachedCoins() : []);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchRef = useRef<() => Promise<void>>(async () => {});
  const coinsRef = useRef<Coin[]>(page === 1 ? loadCachedCoins() : []);

  const fetchCoins = useCallback(async () => {
    if (retryRef.current) { clearTimeout(retryRef.current); retryRef.current = null; }
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      const data = await fetchCoinsAll(perPage, page, currency, abortRef.current.signal);
      coinsRef.current = data;
      setCoins(data);
      setError(null);
      setLastUpdated(new Date());
      if (page === 1) {
        try { localStorage.setItem(CACHE_KEY, JSON.stringify(data)); } catch { /* quota */ }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      const msg = (err as Error).message ?? '';
      const isRateLimit = msg.includes('429');
      // Retry silently if rate-limited or if we already have data to display
      if (isRateLimit || coinsRef.current.length > 0) {
        retryRef.current = setTimeout(() => fetchRef.current(), isRateLimit ? 15_000 : 10_000);
        return;
      }
      setError('Impossibile caricare i prezzi. Dati dalla cache.');
    } finally {
      setLoading(false);
    }
  }, [perPage, page, currency]);

  fetchRef.current = fetchCoins;

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
      if (retryRef.current !== null) clearTimeout(retryRef.current);
      retryRef.current = null;
      abortRef.current?.abort();
    };
  }, [fetchCoins, intervalMs]);

  return { coins, loading, error, lastUpdated, refresh };
}
