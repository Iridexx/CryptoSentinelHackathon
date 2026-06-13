import { useState, useEffect, useRef } from 'react';
import type { Coin } from '../types';
import { fetchMarkets } from '../services/marketData';

export function useFavoriteCoinsData(
  favorites: Set<string>,
  mainCoins: Coin[],
  intervalMs: number,
  currency: string
): Coin[] {
  const [extraCoins, setExtraCoins] = useState<Coin[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const mainIds = new Set(mainCoins.map(c => c.id));
  const missingIds = [...favorites].filter(id => !mainIds.has(id));
  const missingKey = [...missingIds].sort().join(',');

  useEffect(() => {
    if (missingIds.length === 0) {
      setExtraCoins([]);
      return;
    }

    const doFetch = async () => {
      abortRef.current?.abort();
      abortRef.current = new AbortController();
      try {
        const data = await fetchMarkets(
          missingIds.length,
          1,
          currency,
          abortRef.current.signal,
          missingIds,
        );
        setExtraCoins(data);
      } catch (err) {
        if ((err as Error).name !== 'AbortError') { /* silent */ }
      }
    };

    doFetch();
    const timer = setInterval(doFetch, intervalMs);
    return () => {
      clearInterval(timer);
      abortRef.current?.abort();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missingKey, currency, intervalMs]);

  const mainFavorites = mainCoins.filter(c => favorites.has(c.id));
  return [...mainFavorites, ...extraCoins];
}
