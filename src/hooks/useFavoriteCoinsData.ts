import { useState, useEffect, useRef } from 'react';
import type { Coin } from '../types';
import { fetchMarkets } from '../services/marketData';

function unresolvedFavorite(id: string): Coin {
  return {
    id,
    symbol: id,
    name: id
      .split('-')
      .map(part => part ? part[0].toUpperCase() + part.slice(1) : part)
      .join(' '),
    image: '/crypto-icon.svg',
    current_price: 0,
    price_change_percentage_24h: 0,
    market_cap: 0,
    market_cap_rank: null,
    total_volume: 0,
    high_24h: 0,
    low_24h: 0,
  };
}

export function useFavoriteCoinsData(
  favorites: Set<string>,
  mainCoins: Coin[],
  intervalMs: number,
  currency: string
): Coin[] {
  const [extraCoins, setExtraCoins] = useState<Coin[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const mainIds = new Set(mainCoins.map(c => c.id));
  const missingIds = [...favorites].filter(id => !mainIds.has(id));
  const missingKey = [...missingIds].sort().join(',');

  useEffect(() => {
    if (missingIds.length === 0) {
      setExtraCoins([]);
      return;
    }

    const doFetch = async () => {
      if (retryRef.current !== null) {
        clearTimeout(retryRef.current);
        retryRef.current = null;
      }
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
        if ((err as Error).name !== 'AbortError') {
          retryRef.current = setTimeout(doFetch, 5_000);
        }
      }
    };

    doFetch();
    const timer = setInterval(doFetch, intervalMs);
    return () => {
      clearInterval(timer);
      if (retryRef.current !== null) clearTimeout(retryRef.current);
      retryRef.current = null;
      abortRef.current?.abort();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missingKey, currency, intervalMs]);

  const mainFavorites = mainCoins.filter(c => favorites.has(c.id));
  const resolved = new Map(
    [...mainFavorites, ...extraCoins].map(coin => [coin.id, coin]),
  );
  return [...favorites].map(id => resolved.get(id) ?? unresolvedFavorite(id));
}
