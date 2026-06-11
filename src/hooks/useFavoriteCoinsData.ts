import { useState, useEffect, useRef } from 'react';
import type { Coin } from '../types';

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
        const url = `https://api.coingecko.com/api/v3/coins/markets?vs_currency=${currency}&ids=${missingIds.join(',')}&order=market_cap_desc&per_page=${missingIds.length}&page=1&sparkline=false&price_change_percentage=1h,24h,7d`;
        const res = await fetch(url, { signal: abortRef.current.signal });
        if (!res.ok) return;
        const data: Coin[] = await res.json();
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
