import { useState, useCallback, useEffect, useRef } from 'react';
import type { Coin, PriceAlert, AlertDirection, AlertHistoryEntry } from '../types';
import { sendAlertNotification } from '../utils/notifications';
import { playAlertBeep } from '../utils/audio';
import { syncAlertsToNative, getAlertsFromNative } from '../utils/update';

const STORAGE_KEY = 'cryptosentinel_alerts';
const HISTORY_KEY = 'cryptosentinel_alert_history';
const MAX_HISTORY = 50;

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

function loadHistory(): AlertHistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as AlertHistoryEntry[];
  } catch {
    return [];
  }
}

function saveHistory(history: AlertHistoryEntry[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  } catch { /* quota */ }
}

export function useAlerts(coins: Coin[]) {
  const [alerts, setAlerts] = useState<PriceAlert[]>(loadAlerts);
  const [history, setHistory] = useState<AlertHistoryEntry[]>(loadHistory);
  const lastTriggeredRef = useRef<Set<string>>(new Set());
  const prevPricesRef = useRef<Map<string, number>>(new Map());
  const alertsRef = useRef<PriceAlert[]>(alerts);
  const coinsRef = useRef<Coin[]>(coins);
  alertsRef.current = alerts;
  coinsRef.current = coins;

  const addAlert = useCallback((alertData: Omit<PriceAlert, 'id' | 'triggered' | 'createdAt'>) => {
    const newAlert: PriceAlert = {
      ...alertData,
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      triggered: false,
      createdAt: Date.now(),
    };

    // Verifica immediata: se il prezzo è già oltre la soglia, scatta subito senza aspettare il prossimo refresh
    const coin = coinsRef.current.find(c => c.id === alertData.coinId);
    if (coin) {
      const price = coin.current_price;
      const alreadyMet =
        (alertData.direction === 'above' && price >= alertData.threshold) ||
        (alertData.direction === 'below' && price <= alertData.threshold);
      if (alreadyMet) {
        newAlert.triggered = true;
        lastTriggeredRef.current.add(newAlert.id);
        const now = Date.now();
        const entry: AlertHistoryEntry = {
          id: `${now}-${newAlert.id}`,
          coinId: alertData.coinId,
          coinName: alertData.coinName,
          coinSymbol: alertData.coinSymbol,
          coinImage: alertData.coinImage,
          direction: alertData.direction,
          threshold: alertData.threshold,
          triggeredPrice: price,
          triggeredAt: now,
        };
        setHistory(prev => {
          const next = [entry, ...prev].slice(0, MAX_HISTORY);
          saveHistory(next);
          return next;
        });
        playAlertBeep();
        sendAlertNotification({ coinName: alertData.coinName, direction: alertData.direction, threshold: alertData.threshold, currentPrice: price, note: alertData.note });
      }
    }

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

  // Al resume: resetta i prezzi precedenti così il primo fetch post-pausa
  // funge da baseline e non scatta alert in blocco per movimenti avvenuti in background
  useEffect(() => {
    const onResume = () => {
      if (document.visibilityState === 'visible') prevPricesRef.current.clear();
    };
    document.addEventListener('visibilitychange', onResume);
    return () => document.removeEventListener('visibilitychange', onResume);
  }, []);

  // Al mount: legge lo stato triggered dal worker nativo e aggiorna React
  useEffect(() => {
    getAlertsFromNative().then(nativeJson => {
      if (!nativeJson) return;
      try {
        const nativeAlerts = JSON.parse(nativeJson) as Array<{ id: string; triggered?: boolean }>;
        const triggeredIds = new Set(nativeAlerts.filter(a => a.triggered).map(a => a.id));
        if (triggeredIds.size === 0) return;
        setAlerts(prev => {
          const needsUpdate = prev.some(a => triggeredIds.has(a.id) && !a.triggered);
          if (!needsUpdate) return prev;
          const next = prev.map(a => triggeredIds.has(a.id) ? { ...a, triggered: true } : a);
          try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch {}
          return next;
        });
      } catch {}
    });
  }, []);

  useEffect(() => {
    if (coins.length === 0) return;

    const prevPrices = prevPricesRef.current;

    // Prima lettura: popola i prezzi senza sparare (evita notifiche all'apertura app)
    if (prevPrices.size === 0) {
      coins.forEach(c => prevPrices.set(c.id, c.current_price));
      return;
    }

    type FireItem = { alert: PriceAlert; coinName: string; direction: 'above' | 'below'; threshold: number; currentPrice: number; note?: string };
    const toFire: FireItem[] = [];
    const toTriggerIds = new Set<string>();

    for (const alert of alertsRef.current) {
      const coin = coins.find((c) => c.id === alert.coinId);
      if (!coin || alert.triggered || !(alert.active ?? true) || lastTriggeredRef.current.has(alert.id)) continue;

      const price = coin.current_price;
      const prevPrice = prevPrices.get(coin.id);

      const conditionMet =
        (alert.direction === 'above' && price >= alert.threshold) ||
        (alert.direction === 'below' && price <= alert.threshold);
      const crossed =
        (alert.direction === 'above' && prevPrice !== undefined && prevPrice < alert.threshold && price >= alert.threshold) ||
        (alert.direction === 'below' && prevPrice !== undefined && prevPrice > alert.threshold && price <= alert.threshold);
      // Fallback: scatta se l'alert è recente e la condizione è già soddisfatta (editAlert senza cambio prezzo)
      const isNew = Date.now() - alert.createdAt < 10 * 60 * 1000;
      const fires = crossed || (isNew && conditionMet);

      if (fires) {
        lastTriggeredRef.current.add(alert.id);
        toTriggerIds.add(alert.id);
        toFire.push({ alert, coinName: alert.coinName, direction: alert.direction, threshold: alert.threshold, currentPrice: price, note: alert.note });
      }
    }

    // Aggiorna i prezzi precedenti
    coins.forEach(c => prevPrices.set(c.id, c.current_price));

    if (toFire.length === 0) return;

    // Controlla se il worker nativo ha già sparato per questi alert (evita doppioni)
    let alive = true;
    const fire = async () => {
      const nativeJson = await getAlertsFromNative();
      if (!alive) return;

      const nativeTriggered = new Set<string>();
      if (nativeJson) {
        try {
          (JSON.parse(nativeJson) as Array<{ id: string; triggered?: boolean }>)
            .filter(a => a.triggered)
            .forEach(a => nativeTriggered.add(a.id));
        } catch {}
      }

      // Segna tutti come triggered in React (anche quelli gestiti dal worker)
      setAlerts((prev) => {
        const next = prev.map((a) => toTriggerIds.has(a.id) ? { ...a, triggered: true } : a);
        saveAlerts(next);
        return next;
      });

      // Storico per tutti i crossing rilevati dal JS
      const now = Date.now();
      const newEntries: AlertHistoryEntry[] = toFire.map(({ alert, currentPrice }) => ({
        id: `${now}-${alert.id}`,
        coinId: alert.coinId,
        coinName: alert.coinName,
        coinSymbol: alert.coinSymbol,
        coinImage: alert.coinImage,
        direction: alert.direction,
        threshold: alert.threshold,
        triggeredPrice: currentPrice,
        triggeredAt: now,
      }));
      setHistory((prev) => {
        const next = [...newEntries, ...prev].slice(0, MAX_HISTORY);
        saveHistory(next);
        return next;
      });

      // Notifica solo per alert che il worker NON ha già gestito
      const filtered = toFire.filter(({ alert }) => !nativeTriggered.has(alert.id));
      if (filtered.length === 0) return;

      playAlertBeep();
      filtered.forEach(({ coinName, direction, threshold, currentPrice, note }) =>
        sendAlertNotification({ coinName, direction, threshold, currentPrice, note })
      );
    };

    fire();
    return () => { alive = false; };
  }, [coins]);

  const editAlert = useCallback((id: string, threshold: number, direction: AlertDirection, percentChange?: number, note?: string) => {
    const existing = alertsRef.current.find(a => a.id === id);
    let firedNow = false;

    if (existing) {
      const coin = coinsRef.current.find(c => c.id === existing.coinId);
      if (coin) {
        const price = coin.current_price;
        const alreadyMet =
          (direction === 'above' && price >= threshold) ||
          (direction === 'below' && price <= threshold);
        if (alreadyMet) {
          firedNow = true;
          lastTriggeredRef.current.add(id);
          const now = Date.now();
          const entry: AlertHistoryEntry = {
            id: `${now}-${id}`,
            coinId: existing.coinId,
            coinName: existing.coinName,
            coinSymbol: existing.coinSymbol,
            coinImage: existing.coinImage,
            direction,
            threshold,
            triggeredPrice: price,
            triggeredAt: now,
          };
          setHistory(prev => {
            const next = [entry, ...prev].slice(0, MAX_HISTORY);
            saveHistory(next);
            return next;
          });
          playAlertBeep();
          sendAlertNotification({ coinName: existing.coinName, direction, threshold, currentPrice: price, note: note !== undefined ? note : existing.note });
        }
      }
    }

    setAlerts((prev) => {
      const next = prev.map((a) => a.id === id ? { ...a, threshold, direction, percentChange, note: note !== undefined ? note : a.note, triggered: firedNow } : a);
      saveAlerts(next);
      return next;
    });
    if (!firedNow) lastTriggeredRef.current.delete(id);
  }, []);

  const toggleAlert = useCallback((id: string) => {
    setAlerts((prev) => {
      const next = prev.map((a) => a.id === id ? { ...a, active: !(a.active ?? true) } : a);
      saveAlerts(next);
      return next;
    });
  }, []);

  const clearAlerts = useCallback(() => {
    setAlerts([]);
    localStorage.removeItem(STORAGE_KEY);
    syncAlertsToNative([]);
    lastTriggeredRef.current.clear();
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
    localStorage.removeItem(HISTORY_KEY);
  }, []);

  return { alerts, addAlert, removeAlert, resetAlert, editAlert, toggleAlert, clearAlerts, history, clearHistory };
}
