import { useState, useCallback, useEffect, useRef } from 'react';
import type { Coin, PriceAlert } from '../types';
import { sendAlertNotification } from '../utils/notifications';
import { playAlertBeep } from '../utils/audio';
import { syncAlertsToNative } from '../utils/update';

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
  syncAlertsToNative(alerts);
}

export function useAlerts(coins: Coin[]) {
  const [alerts, setAlerts] = useState<PriceAlert[]>(loadAlerts);
  const lastTriggeredRef = useRef<Set<string>>(new Set());
  // Ref per accedere sempre agli alert più recenti senza dipendenze stale
  const alertsRef = useRef<PriceAlert[]>(alerts);
  alertsRef.current = alerts;

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

  useEffect(() => {
    if (coins.length === 0) return;

    // Calcola toFire PRIMA di setAlerts usando il ref (non la closure stale)
    // Il problema precedente: toFire era popolato dentro l'updater di setAlerts
    // che React esegue in modo asincrono — quando il controllo avveniva, toFire era vuoto
    type FireItem = { coinName: string; direction: 'above' | 'below'; threshold: number; currentPrice: number };
    const toFire: FireItem[] = [];
    const toTriggerIds = new Set<string>();

    for (const alert of alertsRef.current) {
      const coin = coins.find((c) => c.id === alert.coinId);
      if (!coin || alert.triggered || lastTriggeredRef.current.has(alert.id)) continue;

      const price = coin.current_price;
      const fires =
        (alert.direction === 'above' && price >= alert.threshold) ||
        (alert.direction === 'below' && price <= alert.threshold);

      if (fires) {
        lastTriggeredRef.current.add(alert.id);
        toTriggerIds.add(alert.id);
        toFire.push({ coinName: alert.coinName, direction: alert.direction, threshold: alert.threshold, currentPrice: price });
      }
    }

    if (toFire.length === 0) return;

    setAlerts((prev) => {
      const next = prev.map((a) => toTriggerIds.has(a.id) ? { ...a, triggered: true } : a);
      saveAlerts(next);
      return next;
    });

    playAlertBeep();
    toFire.forEach((params) => sendAlertNotification(params));
  }, [coins]);

  const clearAlerts = useCallback(() => {
    setAlerts([]);
    localStorage.removeItem(STORAGE_KEY);
    lastTriggeredRef.current.clear();
  }, []);

  return { alerts, addAlert, removeAlert, resetAlert, clearAlerts };
}
