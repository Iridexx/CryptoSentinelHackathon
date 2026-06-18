import { useState, useEffect, useCallback, useRef } from 'react';
import type { Coin } from '../types';
import { fetchMarkets } from '../services/marketData';

export type PerPage = 50 | 100 | 200 | 400 | 600;

const CACHE_KEY = 'cryptosentinel_coins_cache';
async function fetchCoinsAll(perPage: PerPage, page: number, currency: string, signal: AbortSignal): Promise<Coin[]> {
  return fetchMarkets(perPage, page, currency, signal);
}

function cacheKey(perPage: PerPage, page: number, currency: string): string {
  return `${CACHE_KEY}:${currency}:${perPage}:${page}`;
}

function loadCachedCoins(perPage: PerPage, page: number, currency: string): Coin[] {
  try {
    const raw = localStorage.getItem(cacheKey(perPage, page, currency));
    if (!raw) return [];
    return JSON.parse(raw) as Coin[];
  } catch {
    return [];
  }
}

function loadAnyCachedCoins(currency: string): Coin[] {
  const preferred: PerPage[] = [600, 400, 200, 100, 50];
  for (const cachedPerPage of preferred) {
    const data = loadCachedCoins(cachedPerPage, 1, currency);
    if (data.length > 0) return data;
  }
  try {
    const legacy = localStorage.getItem(CACHE_KEY);
    if (!legacy) return [];
    return JSON.parse(legacy) as Coin[];
  } catch {
    return [];
  }
}

export function useCryptoData(intervalMs = 30_000, perPage: PerPage = 50, page = 1, currency = 'usd') {
  const [coins, setCoins] = useState<Coin[]>(() => loadCachedCoins(perPage, page, currency));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchRef = useRef<() => Promise<void>>(async () => {});
  const coinsRef = useRef<Coin[]>(loadCachedCoins(perPage, page, currency));
  const requestVersionRef = useRef(0);

  const fetchCoins = useCallback(async () => {
    const requestVersion = ++requestVersionRef.current;
    if (retryRef.current) { clearTimeout(retryRef.current); retryRef.current = null; }
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      const data = await fetchCoinsAll(perPage, page, currency, abortRef.current.signal);
      if (requestVersion !== requestVersionRef.current) return;
      coinsRef.current = data;
      setCoins(data);
      setError(null);
      setLastUpdated(new Date());
      try { localStorage.setItem(cacheKey(perPage, page, currency), JSON.stringify(data)); } catch { /* quota */ }
    } catch (err) {
      if (requestVersion !== requestVersionRef.current) return;
      if ((err as Error).name === 'AbortError') return;
      const msg = (err as Error).message ?? '';
      const isConfigurationError = msg.includes('not configured');
      const isRateLimit = msg.includes('429');
      if (isConfigurationError) {
        setError(msg);
        return;
      }
      // Retry silently if rate-limited or if we already have data to display.
      if (isRateLimit || coinsRef.current.length > 0) {
        setError(null);
        retryRef.current = setTimeout(() => fetchRef.current(), isRateLimit ? 15_000 : 10_000);
        return;
      }
      const fallback = loadAnyCachedCoins(currency);
      if (fallback.length > 0) {
        coinsRef.current = fallback;
        setCoins(fallback);
        setError(null);
        retryRef.current = setTimeout(() => fetchRef.current(), 10_000);
        return;
      }
      setError('Unable to load prices. Retrying.');
    } finally {
      if (requestVersion === requestVersionRef.current) setLoading(false);
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
    const cached = loadCachedCoins(perPage, page, currency);
    if (cached.length > 0) {
      coinsRef.current = cached;
      setCoins(cached);
    }
    setLoading(true);
    fetchCoins();
    timerRef.current = setInterval(fetchCoins, intervalMs);
    return () => {
      requestVersionRef.current += 1;
      if (timerRef.current !== null) clearInterval(timerRef.current);
      timerRef.current = null;
      if (retryRef.current !== null) clearTimeout(retryRef.current);
      retryRef.current = null;
      abortRef.current?.abort();
    };
  }, [fetchCoins, intervalMs]);

  return { coins, loading, error, lastUpdated, refresh };
}
