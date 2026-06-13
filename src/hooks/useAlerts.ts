import { useCallback, useState } from 'react';
import type { AlertDirection, AlertHistoryEntry, PriceAlert } from '../types';

const STORAGE_KEY = 'cryptosentinel_alerts';
const HISTORY_KEY = 'cryptosentinel_alert_history';

function loadAlerts(): PriceAlert[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as PriceAlert[] : [];
  } catch {
    return [];
  }
}

function saveAlerts(alerts: PriceAlert[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
  } catch {
    // Keep runtime state when browser storage is unavailable.
  }
}

function loadHistory(): AlertHistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) as AlertHistoryEntry[] : [];
  } catch {
    return [];
  }
}

export function useAlerts() {
  const [alerts, setAlerts] = useState<PriceAlert[]>(loadAlerts);
  const [history, setHistory] = useState<AlertHistoryEntry[]>(loadHistory);

  const addAlert = useCallback((alertData: Omit<PriceAlert, 'id' | 'triggered' | 'createdAt'>) => {
    const newAlert: PriceAlert = {
      ...alertData,
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
      const next = prev.filter((alert) => alert.id !== id);
      saveAlerts(next);
      return next;
    });
  }, []);

  const resetAlert = useCallback((id: string) => {
    setAlerts((prev) => {
      const next = prev.map((alert) =>
        alert.id === id ? { ...alert, triggered: false, triggeredAt: undefined } : alert
      );
      saveAlerts(next);
      return next;
    });
  }, []);

  const editAlert = useCallback((
    id: string,
    threshold: number,
    direction: AlertDirection,
    percentChange?: number,
    note?: string,
  ) => {
    setAlerts((prev) => {
      const next = prev.map((alert) =>
        alert.id === id
          ? {
              ...alert,
              threshold,
              direction,
              percentChange,
              note: note !== undefined ? note : alert.note,
              triggered: false,
              triggeredAt: undefined,
            }
          : alert
      );
      saveAlerts(next);
      return next;
    });
  }, []);

  const toggleAlert = useCallback((id: string) => {
    setAlerts((prev) => {
      const next = prev.map((alert) =>
        alert.id === id ? { ...alert, active: !(alert.active ?? true) } : alert
      );
      saveAlerts(next);
      return next;
    });
  }, []);

  const clearAlerts = useCallback(() => {
    setAlerts([]);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
    localStorage.removeItem(HISTORY_KEY);
  }, []);

  return {
    alerts,
    addAlert,
    removeAlert,
    resetAlert,
    editAlert,
    toggleAlert,
    clearAlerts,
    history,
    clearHistory,
  };
}
