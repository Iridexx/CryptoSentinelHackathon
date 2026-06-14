import { useState, useEffect, useRef } from 'react';
import type { Coin } from '../types';
import { searchMarkets } from '../services/marketData';

export function useSearch(query: string, currency = 'usd') {
  const [results, setResults] = useState<Coin[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    abortRef.current?.abort();

    if (!query.trim()) {
      setResults([]);
      setSearching(false);
      setError(null);
      return;
    }

    setSearching(true);

    timerRef.current = setTimeout(async () => {
      abortRef.current = new AbortController();
      const { signal } = abortRef.current;

      try {
        setResults(await searchMarkets(query.trim(), currency, signal));
        setError(null);
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setResults([]);
          setError((err as Error).message || 'Market data search failed');
        }
      } finally {
        setSearching(false);
      }
    }, 400);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      abortRef.current?.abort();
    };
  }, [query, currency]);

  return { results, searching, error };
}
