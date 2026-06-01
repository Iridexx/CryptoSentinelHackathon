import { useState, useCallback, useEffect, useRef } from 'react';
import type { Coin, RangeAlert } from '../types';
import { sendRangeNotification } from '../utils/notifications';
import { playAlertBeep } from '../utils/audio';
import { syncRangeAlertsToNative, getRangeAlertsFromNative } from '../utils/update';

const STORAGE_KEY = 'cryptosentinel_range_alerts';
const COOLDOWN_MS = 5 * 60 * 1000;

function loadRangeAlerts(): RangeAlert[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as RangeAlert[];
  } catch {
    return [];
  }
}

function saveRangeAlerts(alerts: RangeAlert[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
  } catch { /* quota */ }
  syncRangeAlertsToNative(alerts);
}

export function useRangeAlerts(coins: Coin[]) {
  const [rangeAlerts, setRangeAlerts] = useState<RangeAlert[]>(loadRangeAlerts);
  const rangeAlertsRef = useRef<RangeAlert[]>(rangeAlerts);
  rangeAlertsRef.current = rangeAlerts;

  const addRangeAlert = useCallback((alert: Omit<RangeAlert, 'id' | 'isInsideRange' | 'lastNotifiedAt' | 'createdAt'>) => {
    const newAlert: RangeAlert = {
      ...alert,
      id: `range-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      isInsideRange: null,
      lastNotifiedAt: null,
      createdAt: Date.now(),
    };
    setRangeAlerts((prev) => {
      const next = [...prev, newAlert];
      saveRangeAlerts(next);
      return next;
    });
  }, []);

  const removeRangeAlert = useCallback((id: string) => {
    setRangeAlerts((prev) => {
      const next = prev.filter((a) => a.id !== id);
      saveRangeAlerts(next);
      return next;
    });
  }, []);

  const editRangeAlert = useCallback((id: string, minPrice: number, maxPrice: number, note?: string) => {
    setRangeAlerts((prev) => {
      const next = prev.map((a) =>
        a.id === id
          ? { ...a, minPrice, maxPrice, note: note !== undefined ? note : a.note, isInsideRange: null, lastNotifiedAt: null }
          : a
      );
      saveRangeAlerts(next);
      return next;
    });
  }, []);

  const clearRangeAlerts = useCallback(() => {
    setRangeAlerts([]);
    localStorage.removeItem(STORAGE_KEY);
    syncRangeAlertsToNative([]);
  }, []);

  // At mount: sync isInsideRange state from native worker
  useEffect(() => {
    getRangeAlertsFromNative().then((nativeJson) => {
      if (!nativeJson) return;
      try {
        const nativeAlerts = JSON.parse(nativeJson) as Array<{ id: string; isInsideRange?: boolean | null; lastNotifiedAt?: number | null }>;
        if (nativeAlerts.length === 0) return;
        setRangeAlerts((prev) => {
          const nativeMap = new Map(nativeAlerts.map((a) => [a.id, a]));
          let changed = false;
          const next = prev.map((a) => {
            const native = nativeMap.get(a.id);
            if (!native) return a;
            const newIsInside = native.isInsideRange ?? null;
            const newLastNotified = native.lastNotifiedAt ?? null;
            if (newIsInside === a.isInsideRange && newLastNotified === a.lastNotifiedAt) return a;
            changed = true;
            return { ...a, isInsideRange: newIsInside, lastNotifiedAt: newLastNotified };
          });
          if (!changed) return prev;
          try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch {}
          return next;
        });
      } catch {}
    });
  }, []);

  useEffect(() => {
    if (coins.length === 0) return;

    const now = Date.now();
    type UpdateItem = { id: string; updates: Partial<RangeAlert> };
    const toUpdate: UpdateItem[] = [];
    const toNotify: Array<{ alert: RangeAlert; entered: boolean; price: number }> = [];

    for (const alert of rangeAlertsRef.current) {
      const coin = coins.find((c) => c.id === alert.coinId);
      if (!coin) continue;

      const price = coin.current_price;
      const isInside = price >= alert.minPrice && price <= alert.maxPrice;

      if (alert.isInsideRange === null) {
        toUpdate.push({ id: alert.id, updates: { isInsideRange: isInside } });
        continue;
      }

      if (isInside === alert.isInsideRange) continue;

      const cooldownOk = alert.lastNotifiedAt === null || now - alert.lastNotifiedAt >= COOLDOWN_MS;
      if (cooldownOk) {
        toUpdate.push({ id: alert.id, updates: { isInsideRange: isInside, lastNotifiedAt: now } });
        toNotify.push({ alert, entered: isInside, price });
      } else {
        toUpdate.push({ id: alert.id, updates: { isInsideRange: isInside } });
      }
    }

    if (toUpdate.length === 0) return;

    setRangeAlerts((prev) => {
      const updateMap = new Map(toUpdate.map((u) => [u.id, u.updates]));
      const next = prev.map((a) => {
        const updates = updateMap.get(a.id);
        return updates ? { ...a, ...updates } : a;
      });
      saveRangeAlerts(next);
      return next;
    });

    if (toNotify.length === 0) return;

    playAlertBeep();
    toNotify.forEach(({ alert, entered, price }) => {
      sendRangeNotification({
        coinName: alert.coinName,
        minPrice: alert.minPrice,
        maxPrice: alert.maxPrice,
        currentPrice: price,
        entered,
        note: alert.note,
      });
    });
  }, [coins]);

  return { rangeAlerts, addRangeAlert, removeRangeAlert, editRangeAlert, clearRangeAlerts };
}
