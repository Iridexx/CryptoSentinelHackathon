import { useState, useCallback, useEffect, useRef } from 'react';
import type { Coin, PriceAlert } from '../types';
import { sendAlertNotification } from '../utils/notifications';
import { playAlertBeep } from '../utils/audio';

const STORAGE_KEY = 'cryptowatch_alerts';

function loadAlerts(): PriceAlert[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as PriceAlert[];
  } catch {
    return [];
  }
}

function saveAlerts(alerts: PriceAlert[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
  } catch { /* quota */ }
}

export function useAlerts(coins: Coin[]) {
  const [alerts, setAlerts] = useState<PriceAlert[]>(loadAlerts);
  const lastTriggeredRef = useRef<Set<string>>(new Set());

  const addAlert = useCallback((alert: Omit<PriceAlert, 'id' | 'triggered' | 'createdAt'>) => {
    const newAlert: PriceAlert = {
      ...alert,
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      triggered: false,
      createdAt: Date.now(),
    };
    setAlerts((prev) => {
      const next = [...prev, newAlert];
      saveAlerts(next);
      return next;
    });
  }, []);

  const removeAlert = useCallback((id: string) => {
    setAlerts((prev) => {
      const next = prev.filter((a) => a.id !== id);
      saveAlerts(next);
      lastTriggeredRef.current.delete(id);
      return next;
    });
  }, []);

  const resetAlert = useCallback((id: string) => {
    setAlerts((prev) => {
      const next = prev.map((a) => (a.id === id ? { ...a, triggered: false } : a));
      saveAlerts(next);
      lastTriggeredRef.current.delete(id);
      return next;
    });
  }, []);

  // Controlla gli allarmi ogni volta che i prezzi si aggiornano
  useEffect(() => {
    if (coins.length === 0) return;

    // Raccogli gli allarmi da scattare senza side-effect nell'updater
    const toFire: { coinName: string; direction: 'above' | 'below'; threshold: number; currentPrice: number }[] = [];

    setAlerts((prev) => {
      let changed = false;
      const next = prev.map((alert) => {
        const coin = coins.find((c) => c.id === alert.coinId);
        if (!coin || alert.triggered || lastTriggeredRef.current.has(alert.id)) return alert;

        const price = coin.current_price;
        const shouldTrigger =
          (alert.direction === 'above' && price >= alert.threshold) ||
          (alert.direction === 'below' && price <= alert.threshold);

        if (shouldTrigger) {
          lastTriggeredRef.current.add(alert.id);
          changed = true;
          toFire.push({
            coinName: alert.coinName,
            direction: alert.direction,
            threshold: alert.threshold,
            currentPrice: price,
          });
          return { ...alert, triggered: true };
        }
        return alert;
      });

      if (changed) {
        saveAlerts(next);
        return next;
      }
      return prev;
    });

    // Effetti collaterali fuori dall'updater
    if (toFire.length > 0) {
      playAlertBeep();
      toFire.forEach((params) => sendAlertNotification(params));
    }
  }, [coins]);

  const clearAlerts = useCallback(() => {
    setAlerts([]);
    localStorage.removeItem(STORAGE_KEY);
    lastTriggeredRef.current.clear();
  }, []);

  return { alerts, addAlert, removeAlert, resetAlert, clearAlerts };
}
