import { CapacitorHttp } from '@capacitor/core';
import type { PriceAlert, RangeAlert } from '../types';

const BACKEND_URL = (import.meta.env.VITE_BACKEND_API_BASE_URL as string | undefined)?.replace(/\/+$/, '');
const DEVICE_TOKEN = import.meta.env.VITE_API_DEVICE_TOKEN as string | undefined;

export interface FavSyncConfig {
  coins: { id: string; name: string; symbol: string }[];
  upPct: number;
  downPct: number;
  currency: string;
  refPrices: Record<string, number>;
}

export async function syncAlertsToBackend(
  priceAlerts: PriceAlert[],
  rangeAlerts: RangeAlert[],
  fav: FavSyncConfig,
): Promise<void> {
  if (!BACKEND_URL || !DEVICE_TOKEN) return;
  try {
    await CapacitorHttp.request({
      method: 'POST',
      url: `${BACKEND_URL}/api/v1/alerts/sync`,
      headers: {
        Authorization: `Bearer ${DEVICE_TOKEN}`,
        'Content-Type': 'application/json',
      },
      data: {
        price_alerts: priceAlerts
          .filter((a) => !a.triggered && a.active !== false)
          .map((a) => ({
            coin_id: a.coinId,
            coin_name: a.coinName,
            coin_symbol: a.coinSymbol,
            direction: a.direction,
            threshold: a.threshold,
            note: a.note ?? null,
          })),
        range_alerts: rangeAlerts
          .filter((a) => a.active !== false)
          .map((a) => ({
            coin_id: a.coinId,
            coin_name: a.coinName,
            coin_symbol: a.coinSymbol,
            min_price: a.minPrice,
            max_price: a.maxPrice,
            note: a.note ?? null,
          })),
        fav_coins: fav.coins.map((c) => ({ id: c.id, name: c.name, symbol: c.symbol })),
        fav_up_pct: fav.upPct,
        fav_down_pct: fav.downPct,
        fav_currency: fav.currency,
        fav_ref_prices: fav.refPrices,
      },
    });
  } catch {
    // Sync is best-effort — local alerts still work as fallback
  }
}
