import { useCallback, useEffect, useRef } from 'react';
import type { Coin } from '../types';
import { sendFavoriteMoveNotification } from '../utils/notifications';
import { playAlertBeep } from '../utils/audio';

export interface FavAlertData {
  coinId: string;
  coinName: string;
  coinSymbol: string;
  direction: 'up' | 'down';
  pct: number;
  currentPrice: number;
  refPrice: number;
}

const REF_KEY = 'cs_fav_ref_prices';
const FAV_COOLDOWN_MS = 5 * 60 * 1000;

function loadRefPrices(): Map<string, number> {
  try {
    const raw = localStorage.getItem(REF_KEY);
    if (!raw) return new Map();
    return new Map(Object.entries(JSON.parse(raw) as Record<string, number>));
  } catch { return new Map(); }
}

function saveRefPrices(map: Map<string, number>) {
  try {
    localStorage.setItem(REF_KEY, JSON.stringify(Object.fromEntries(map)));
  } catch { /* quota */ }
}

export function useFavoritePriceAlerts(
  favoriteCoins: Coin[],
  upPct: number,
  downPct: number,
  onAlert?: (alert: FavAlertData) => void,
): { bumpRefPrice: (coinId: string, price: number) => void } {
  const refPrices = useRef<Map<string, number>>(loadRefPrices());
  const lastFiredRef = useRef<Map<string, number>>(new Map());
  const upPctRef = useRef(upPct);
  const downPctRef = useRef(downPct);
  const onAlertRef = useRef(onAlert);
  upPctRef.current = upPct;
  downPctRef.current = downPct;
  onAlertRef.current = onAlert;

  useEffect(() => {
    if (favoriteCoins.length === 0) return;

    const up = upPctRef.current;
    const down = downPctRef.current;
    const now = Date.now();
    const toNotify: FavAlertData[] = [];

    for (const coin of favoriteCoins) {
      const ref = refPrices.current.get(coin.id);
      if (ref === undefined) {
        refPrices.current.set(coin.id, coin.current_price);
        continue;
      }

      const pctChange = (coin.current_price - ref) / ref * 100;
      const cooldownOk = now - (lastFiredRef.current.get(coin.id) ?? 0) >= FAV_COOLDOWN_MS;

      if (up > 0 && pctChange >= up) {
        refPrices.current.set(coin.id, coin.current_price);
        if (cooldownOk) {
          lastFiredRef.current.set(coin.id, now);
          toNotify.push({ coinId: coin.id, coinName: coin.name, coinSymbol: coin.symbol, direction: 'up', pct: pctChange, currentPrice: coin.current_price, refPrice: ref });
        }
      } else if (down > 0 && pctChange <= -down) {
        refPrices.current.set(coin.id, coin.current_price);
        if (cooldownOk) {
          lastFiredRef.current.set(coin.id, now);
          toNotify.push({ coinId: coin.id, coinName: coin.name, coinSymbol: coin.symbol, direction: 'down', pct: Math.abs(pctChange), currentPrice: coin.current_price, refPrice: ref });
        }
      }
    }

    // Remove entries for coins no longer in favorites
    const favoriteIds = new Set(favoriteCoins.map(c => c.id));
    for (const id of refPrices.current.keys()) {
      if (!favoriteIds.has(id)) refPrices.current.delete(id);
    }

    saveRefPrices(refPrices.current);

    if (toNotify.length === 0) return;
    playAlertBeep();
    toNotify.forEach(p => {
      sendFavoriteMoveNotification(p);
      onAlertRef.current?.(p);
    });
  }, [favoriteCoins]);

  const bumpRefPrice = useCallback((coinId: string, price: number) => {
    refPrices.current.set(coinId, price);
    saveRefPrices(refPrices.current);
  }, []);

  return { bumpRefPrice };
}
