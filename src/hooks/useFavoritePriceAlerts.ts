import { useEffect, useRef } from 'react';
import type { Coin } from '../types';
import { sendFavoriteMoveNotification } from '../utils/notifications';
import { playAlertBeep } from '../utils/audio';

export function useFavoritePriceAlerts(favoriteCoins: Coin[], upPct: number, downPct: number) {
  const refPrices = useRef<Map<string, number>>(new Map());
  const upPctRef = useRef(upPct);
  const downPctRef = useRef(downPct);
  upPctRef.current = upPct;
  downPctRef.current = downPct;

  useEffect(() => {
    if (favoriteCoins.length === 0) return;

    const up = upPctRef.current;
    const down = downPctRef.current;
    const toNotify: Array<{ coinName: string; coinSymbol: string; direction: 'up' | 'down'; pct: number; currentPrice: number }> = [];

    for (const coin of favoriteCoins) {
      const ref = refPrices.current.get(coin.id);
      if (ref === undefined) {
        refPrices.current.set(coin.id, coin.current_price);
        continue;
      }

      const pctChange = (coin.current_price - ref) / ref * 100;

      if (up > 0 && pctChange >= up) {
        refPrices.current.set(coin.id, coin.current_price);
        toNotify.push({ coinName: coin.name, coinSymbol: coin.symbol, direction: 'up', pct: pctChange, currentPrice: coin.current_price });
      } else if (down > 0 && pctChange <= -down) {
        refPrices.current.set(coin.id, coin.current_price);
        toNotify.push({ coinName: coin.name, coinSymbol: coin.symbol, direction: 'down', pct: Math.abs(pctChange), currentPrice: coin.current_price });
      }
    }

    // Remove entries for coins no longer in favorites
    const favoriteIds = new Set(favoriteCoins.map(c => c.id));
    for (const id of refPrices.current.keys()) {
      if (!favoriteIds.has(id)) refPrices.current.delete(id);
    }

    if (toNotify.length === 0) return;
    playAlertBeep();
    toNotify.forEach(p => sendFavoriteMoveNotification(p));
  }, [favoriteCoins]);
}
