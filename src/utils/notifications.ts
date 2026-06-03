import { Capacitor, registerPlugin } from '@capacitor/core';
import { LocalNotifications } from '@capacitor/local-notifications';

interface AppSettingsPlugin {
  openNotifications(): Promise<void>;
  openWithChooser(options: { url: string; title?: string }): Promise<void>;
  syncFavAlerts(options: { coinsJson: string; upPct: number; downPct: number; refPricesJson: string; currency: string }): Promise<void>;
  getAndClearPendingFavAlerts(): Promise<{ json: string }>;
}

const AppSettings = registerPlugin<AppSettingsPlugin>('AppSettings');

export async function initNotifications(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  await LocalNotifications.createChannel({
    id: 'price_alerts',
    name: 'Allarmi Prezzi',
    description: 'Notifiche per gli allarmi di prezzo crypto',
    importance: 5,
    vibration: true,
    sound: 'default',
    visibility: 1,
  });
}

export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!Capacitor.isNativePlatform()) {
    if (!('Notification' in window)) return 'denied';
    if (Notification.permission !== 'default') return Notification.permission;
    return await Notification.requestPermission();
  }
  const result = await LocalNotifications.requestPermissions();
  return result.display === 'granted' ? 'granted' : 'denied';
}

export async function getNotificationPermission(): Promise<NotificationPermission> {
  if (!Capacitor.isNativePlatform()) {
    if (!('Notification' in window)) return 'denied';
    return Notification.permission;
  }
  const status = await LocalNotifications.checkPermissions();
  return status.display === 'granted' ? 'granted' : 'denied';
}

function notifId(seed: string): number {
  let h = 5381;
  for (let i = 0; i < seed.length; i++) {
    h = (Math.imul(h, 33) ^ seed.charCodeAt(i)) >>> 0;
  }
  return (h % 1_900_000) + 1;
}

export async function sendAlertNotification(params: {
  coinName: string;
  direction: 'above' | 'below';
  threshold: number;
  currentPrice: number;
  note?: string;
}): Promise<void> {
  if (Capacitor.isNativePlatform()) {
    try {
      const perm = await LocalNotifications.checkPermissions();
      if (perm.display !== 'granted') return;
      const arrow = params.direction === 'above' ? '▲' : '▼';
      const label = params.direction === 'above' ? 'superato al rialzo' : 'superato al ribasso';
      const fmt = (v: number) => v >= 1000 ? v.toLocaleString('it-IT', { maximumFractionDigits: 0 }) : v >= 1 ? v.toFixed(2) : v.toFixed(6);
      const body = params.note
        ? `Soglia: $${fmt(params.threshold)}  ·  Prezzo attuale: $${fmt(params.currentPrice)}\n📝 ${params.note}`
        : `Soglia: $${fmt(params.threshold)}  ·  Prezzo attuale: $${fmt(params.currentPrice)}`;
      await LocalNotifications.schedule({
        notifications: [{
          id: notifId(params.coinName + params.direction + params.threshold),
          channelId: 'price_alerts',
          title: `${arrow} ${params.coinName} — soglia ${label}`,
          body,
          sound: 'default',
          smallIcon: 'ic_notification',
          autoCancel: true,
        }],
      });
    } catch {
      // notifica fallita silenziosamente
    }
    return;
  }
}

export async function sendRangeNotification(params: {
  coinName: string;
  minPrice: number;
  maxPrice: number;
  currentPrice: number;
  entered: boolean;
  note?: string;
}): Promise<void> {
  if (Capacitor.isNativePlatform()) {
    try {
      const perm = await LocalNotifications.checkPermissions();
      if (perm.display !== 'granted') return;
      const fmt = (v: number) => v >= 1000 ? v.toLocaleString('it-IT', { maximumFractionDigits: 0 }) : v >= 1 ? v.toFixed(2) : v.toFixed(6);
      const status = params.entered ? '↔ Entrato nel range' : '↗ Uscito dal range';
      const title = `${status} — ${params.coinName}`;
      const bodyBase = `Range: $${fmt(params.minPrice)} – $${fmt(params.maxPrice)}  ·  Ora: $${fmt(params.currentPrice)}`;
      const body = params.note ? `${bodyBase}\n📝 ${params.note}` : bodyBase;
      await LocalNotifications.schedule({
        notifications: [{
          id: notifId(params.coinName + params.minPrice + params.maxPrice),
          channelId: 'price_alerts',
          title,
          body,
          sound: 'default',
          smallIcon: 'ic_notification',
          autoCancel: true,
        }],
      });
    } catch {
      // notifica fallita silenziosamente
    }
    return;
  }
}

export async function sendFavoriteMoveNotification(params: {
  coinName: string;
  coinSymbol: string;
  direction: 'up' | 'down';
  pct: number;
  currentPrice: number;
}): Promise<void> {
  if (Capacitor.isNativePlatform()) {
    try {
      const perm = await LocalNotifications.checkPermissions();
      if (perm.display !== 'granted') return;
      const fmt = (v: number) => v >= 1000 ? v.toLocaleString('it-IT', { maximumFractionDigits: 0 }) : v >= 1 ? v.toFixed(2) : v.toFixed(6);
      const arrow = params.direction === 'up' ? '▲' : '▼';
      const label = params.direction === 'up' ? 'rialzo' : 'ribasso';
      const title = `${arrow} ${params.coinName} (${params.coinSymbol.toUpperCase()}) — ${label} del ${params.pct.toFixed(1)}%`;
      const body = `Il prezzo si è mosso verso il ${label} del ${params.pct.toFixed(1)}%  ·  Ora: $${fmt(params.currentPrice)}`;
      await LocalNotifications.schedule({
        notifications: [{
          id: notifId(params.coinName + params.direction),
          channelId: 'price_alerts',
          title,
          body,
          sound: 'default',
          smallIcon: 'ic_notification',
          autoCancel: true,
        }],
      });
    } catch {
      // notifica fallita silenziosamente
    }
    return;
  }
}

export function openExternalUrl(url: string): void {
  if (Capacitor.isNativePlatform()) {
    AppSettings.openWithChooser({ url, title: 'Apri con' }).catch(() => {
      window.open(url, '_blank');
    });
  } else {
    window.open(url, '_blank');
  }
}

export function openNotificationSettings(): void {
  if (Capacitor.isNativePlatform()) {
    AppSettings.openNotifications().catch(() => {
      window.open('app-settings:', '_system');
    });
  }
}

export async function syncFavAlertsNative(
  coinsJson: string,
  upPct: number,
  downPct: number,
  refPricesJson = '{}',
  currency = 'usd',
): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  try {
    await AppSettings.syncFavAlerts({ coinsJson, upPct, downPct, refPricesJson, currency });
  } catch { /* ignore */ }
}

export async function getAndClearPendingFavAlerts(): Promise<string> {
  if (!Capacitor.isNativePlatform()) return '[]';
  try {
    const result = await AppSettings.getAndClearPendingFavAlerts();
    return result.json ?? '[]';
  } catch {
    return '[]';
  }
}
