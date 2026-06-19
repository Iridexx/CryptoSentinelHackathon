import { useState, useEffect, useCallback, useRef } from 'react';
import type { Coin } from '../types';
import { fetchMarkets } from '../services/marketData';

export type PerPage = 50 | 100 | 200 | 400 | 600;

const CACHE_KEY_PREFIX = 'cryptosentinel_coins_cache';

function cacheKey(perPage: PerPage): string {
  return `${CACHE_KEY_PREFIX}_${perPage}`;
}

async function fetchCoinsAll(perPage: PerPage, page: number, currency: string, signal: AbortSignal): Promise<Coin[]> {
  return fetchMarkets(perPage, page, currency, signal);
}

function loadCachedCoins(perPage: PerPage): Coin[] {
  try {
    const raw = localStorage.getItem(cacheKey(perPage));
    if (!raw) return [];
    return JSON.parse(raw) as Coin[];
  } catch {
    return [];
  }
}

export function useCryptoData(intervalMs = 30_000, perPage: PerPage = 50, page = 1, currency = 'usd') {
  const [coins, setCoins] = useState<Coin[]>(() => page === 1 ? loadCachedCoins(perPage) : []);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchRef = useRef<() => Promise<void>>(async () => {});
  const coinsRef = useRef<Coin[]>(page === 1 ? loadCachedCoins(perPage) : []);
  const requestVersionRef = useRef(0);
  // Tracks which perPage was used for the last successful fetch, so we know
  // when the selector changes and coinsRef needs to be re-seeded from the
  // per-perPage cache instead of carrying over stale data from another limit.
  const fetchedPerPageRef = useRef<PerPage | null>(null);

  const fetchCoins = useCallback(async () => {
    const requestVersion = ++requestVersionRef.current;
    if (retryRef.current) { clearTimeout(retryRef.current); retryRef.current = null; }

    // When perPage changes, reset coinsRef to the per-perPage cache so that a
    // failed fetch for the new limit doesn't silently fall back to stale data
    // from a different limit (e.g. 50 masking a 100-coin request failure).
    if (fetchedPerPageRef.current !== null && fetchedPerPageRef.current !== perPage) {
      const nextCache = page === 1 ? loadCachedCoins(perPage) : [];
      coinsRef.current = nextCache;
      setCoins(nextCache);
    }

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      const data = await fetchCoinsAll(perPage, page, currency, abortRef.current.signal);
      if (requestVersion !== requestVersionRef.current) return;
      coinsRef.current = data;
      fetchedPerPageRef.current = perPage;
      setCoins(data);
      setError(null);
      setLastUpdated(new Date());
      if (page === 1) {
        try { localStorage.setItem(cacheKey(perPage), JSON.stringify(data)); } catch { /* quota */ }
      }
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
      // Retry silently if rate-limited or if we already have data to display
      if (isRateLimit || coinsRef.current.length > 0) {
        retryRef.current = setTimeout(() => fetchRef.current(), isRateLimit ? 15_000 : 10_000);
        return;
      }
      setError('Unable to load prices. Showing cached data.');
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
