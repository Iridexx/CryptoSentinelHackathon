import { useState, useEffect, useRef } from 'react';
import type { Coin } from '../types';

const SEARCH_URL = 'https://api.coingecko.com/api/v3/search';
const MARKETS_URL = 'https://api.coingecko.com/api/v3/coins/markets';

export function useSearch(query: string) {
  const [results, setResults] = useState<Coin[]>([]);
  const [searching, setSearching] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    abortRef.current?.abort();

    if (!query.trim()) {
      setResults([]);
      setSearching(false);
      return;
    }

    setSearching(true);

    timerRef.current = setTimeout(async () => {
      abortRef.current = new AbortController();
      const { signal } = abortRef.current;

      try {
        const searchRes = await fetch(`${SEARCH_URL}?query=${encodeURIComponent(query.trim())}`, { signal });
        if (!searchRes.ok) throw new Error();
        const { coins } = await searchRes.json() as { coins: { id: string }[] };

        if (coins.length === 0) { setResults([]); return; }

        const ids = coins.slice(0, 25).map((c) => c.id).join(',');
        const marketsRes = await fetch(
          `${MARKETS_URL}?vs_currency=usd&ids=${ids}&order=market_cap_desc&sparkline=false&price_change_percentage=24h`,
          { signal }
        );
        if (!marketsRes.ok) throw new Error();
        setResults(await marketsRes.json() as Coin[]);
      } catch (err) {
        if ((err as Error).name !== 'AbortError') setResults([]);
      } finally {
        setSearching(false);
      }
    }, 400);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      abortRef.current?.abort();
    };
  }, [query]);

  return { results, searching };
}
