import { useState, useEffect, useRef } from 'react';
import type { Coin } from '../types';
import { searchMarkets } from '../services/marketData';

interface SearchState {
  /** Chiave (query + valuta) dell'ultima ricerca conclusa. */
  key: string | null;
  results: Coin[];
  error: string | null;
}

export function useSearch(query: string, currency = 'usd') {
  const trimmed = query.trim();
  const searchKey = `${trimmed}|${currency}`;
  const [state, setState] = useState<SearchState>({ key: null, results: [], error: null });
  // Query svuotata: i risultati precedenti non devono riapparire alla ricerca successiva
  // (aggiornamento durante il render, non in un effect).
  if (!trimmed && (state.key !== null || state.results.length > 0 || state.error !== null)) {
    setState({ key: null, results: [], error: null });
  }
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestVersionRef = useRef(0);

  useEffect(() => {
    const requestVersion = ++requestVersionRef.current;
    if (timerRef.current) clearTimeout(timerRef.current);
    abortRef.current?.abort();

    if (!trimmed) return;

    timerRef.current = setTimeout(async () => {
      abortRef.current = new AbortController();
      const { signal } = abortRef.current;

      try {
        const nextResults = await searchMarkets(trimmed, currency, signal);
        if (requestVersion !== requestVersionRef.current) return;
        setState({ key: searchKey, results: nextResults, error: null });
      } catch (err) {
        if (requestVersion !== requestVersionRef.current) return;
        if ((err as Error).name !== 'AbortError') {
          setState({ key: searchKey, results: [], error: (err as Error).message || 'Market data search failed' });
        } else {
          setState((previous) => ({ ...previous, key: searchKey }));
        }
      }
    }, 400);

    return () => {
      requestVersionRef.current += 1;
      if (timerRef.current) clearTimeout(timerRef.current);
      abortRef.current?.abort();
    };
  }, [trimmed, currency, searchKey]);

  // Stato derivato: 'searching' dal momento in cui la query cambia fino alla risposta;
  // con la query vuota non c'e' nulla da mostrare.
  const active = trimmed !== '';
  return {
    results: active ? state.results : [],
    searching: active && state.key !== searchKey,
    error: active ? state.error : null,
  };
}
