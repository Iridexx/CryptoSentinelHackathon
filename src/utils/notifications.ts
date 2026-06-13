import { Capacitor, CapacitorHttp, registerPlugin } from '@capacitor/core';
import { LocalNotifications } from '@capacitor/local-notifications';
import { PushNotifications } from '@capacitor/push-notifications';

interface AppSettingsPlugin {
  openNotifications(): Promise<void>;
  openWithChooser(options: { url: string; title?: string }): Promise<void>;
  syncFavAlerts(options: { coinsJson: string; upPct: number; downPct: number; refPricesJson: string; currency: string }): Promise<void>;
  getAndClearPendingFavAlerts(): Promise<{ json: string }>;
}

const AppSettings = registerPlugin<AppSettingsPlugin>('AppSettings');
const BACKEND_API_BASE_URL = import.meta.env.VITE_BACKEND_API_BASE_URL as string | undefined;
const API_DEVICE_TOKEN = import.meta.env.VITE_API_DEVICE_TOKEN as string | undefined;
const API_ALERTS_TOKEN = import.meta.env.VITE_API_ALERTS_TOKEN as string | undefined;
const PENDING_FAV_ALERTS_KEY = 'cs_pending_fcm_fav_alerts';
let pushRegistrationStarted = false;

export interface FavAlertData {
  coinId: string;
  coinName: string;
  coinSymbol: string;
  direction: 'up' | 'down';
  pct: number;
  currentPrice: number;
  refPrice: number;
}

interface FavPushEvent {
  alert: FavAlertData;
  openFavorites: boolean;
}

const favPushSubscribers = new Set<(event: FavPushEvent) => void>();

function loadPendingFavAlerts(): Record<string, FavAlertData> {
  try {
    return JSON.parse(localStorage.getItem(PENDING_FAV_ALERTS_KEY) ?? '{}') as Record<string, FavAlertData>;
  } catch {
    return {};
  }
}

function savePendingFavAlert(alert: FavAlertData): void {
  const pending = loadPendingFavAlerts();
  pending[alert.coinId] = alert;
  localStorage.setItem(PENDING_FAV_ALERTS_KEY, JSON.stringify(pending));
}

function parseFavAlert(data: Record<string, unknown> | undefined): FavAlertData | null {
  if (!data || data.type !== 'fav_alert' || typeof data.coin_id !== 'string') return null;
  return {
    coinId: data.coin_id,
    coinName: typeof data.coin_name === 'string' ? data.coin_name : data.coin_id,
    coinSymbol: typeof data.coin_symbol === 'string' ? data.coin_symbol : '',
    direction: data.direction === 'down' ? 'down' : 'up',
    pct: Number(data.pct ?? 0),
    currentPrice: Number(data.current_price ?? 0),
    refPrice: Number(data.ref_price ?? 0),
  };
}

function emitFavPush(data: Record<string, unknown> | undefined, openFavorites: boolean): void {
  const alert = parseFavAlert(data);
  if (!alert) return;
  savePendingFavAlert(alert);
  favPushSubscribers.forEach((subscriber) => subscriber({ alert, openFavorites }));
}

export function subscribeFavoritePushAlerts(
  subscriber: (event: FavPushEvent) => void,
): () => void {
  favPushSubscribers.add(subscriber);
  Object.values(loadPendingFavAlerts()).forEach((alert) => {
    subscriber({ alert, openFavorites: false });
  });
  return () => favPushSubscribers.delete(subscriber);
}

export function dismissFavoritePushAlert(coinId: string): void {
  const pending = loadPendingFavAlerts();
  delete pending[coinId];
  localStorage.setItem(PENDING_FAV_ALERTS_KEY, JSON.stringify(pending));
  dismissFavoritePushAlertOnBackend(coinId);
}

export async function refreshPendingFavoritePushAlerts(): Promise<void> {
  const baseUrl = BACKEND_API_BASE_URL?.replace(/\/+$/, '');
  if (!baseUrl || !API_ALERTS_TOKEN) return;
  try {
    const response = await CapacitorHttp.request({
      method: 'GET',
      url: `${baseUrl}/api/v1/alerts/pending-favorites`,
      headers: { Authorization: `Bearer ${API_ALERTS_TOKEN}` },
      connectTimeout: 6000,
      readTimeout: 6000,
    });
    if (response.status < 200 || response.status >= 300) return;
    const items = (response.data as { items?: Record<string, unknown>[] })?.items ?? [];
    for (const item of items) emitFavPush({ ...item, type: 'fav_alert' }, false);
  } catch {
    // The local persisted badge remains available while the backend is unreachable.
  }
}

async function dismissFavoritePushAlertOnBackend(coinId: string): Promise<void> {
  const baseUrl = BACKEND_API_BASE_URL?.replace(/\/+$/, '');
  if (!baseUrl || !API_ALERTS_TOKEN) return;
  try {
    await CapacitorHttp.request({
      method: 'DELETE',
      url: `${baseUrl}/api/v1/alerts/pending-favorites/${encodeURIComponent(coinId)}`,
      headers: { Authorization: `Bearer ${API_ALERTS_TOKEN}` },
      connectTimeout: 6000,
      readTimeout: 6000,
    });
  } catch {
    // Best effort: a later backend refresh may restore the badge until acknowledgement succeeds.
  }
}

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
  await registerRemotePushToken();
}

async function registerRemotePushToken(): Promise<void> {
  if (pushRegistrationStarted || !BACKEND_API_BASE_URL || !API_DEVICE_TOKEN) return;
  pushRegistrationStarted = true;

  try {
    await PushNotifications.addListener('registration', async (token) => {
      await sendPushTokenToBackend(token.value);
    });

    await PushNotifications.addListener('registrationError', () => {
      // Keep local notifications working even if FCM registration is unavailable.
    });

    // FCM in foreground: show as local notification (Android doesn't auto-display these)
    await PushNotifications.addListener('pushNotificationReceived', async (notification) => {
      emitFavPush(notification.data, false);
      await LocalNotifications.schedule({
        notifications: [{
          id: Math.floor(Math.random() * 1_900_000) + 1,
          channelId: 'price_alerts',
          title: notification.title ?? 'CryptoSentinel',
          body: notification.body ?? '',
          sound: 'default',
          smallIcon: 'ic_notification',
          autoCancel: true,
        }],
      });
    });

    await PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
      emitFavPush(action.notification.data, true);
    });

    const permission = await PushNotifications.requestPermissions();
    if (permission.receive !== 'granted') return;
    await PushNotifications.register();
  } catch {
    // Keep local notifications working even if remote push bootstrap fails.
  }
}

async function sendPushTokenToBackend(token: string): Promise<void> {
  try {
    const baseUrl = BACKEND_API_BASE_URL?.replace(/\/+$/, '');
    if (!baseUrl || !API_DEVICE_TOKEN) return;
    await CapacitorHttp.request({
      method: 'POST',
      url: `${baseUrl}/api/v1/notifications/devices`,
      headers: {
        Authorization: `Bearer ${API_DEVICE_TOKEN}`,
        'Content-Type': 'application/json',
      },
      data: {
        token,
        platform: 'android',
        app_version: __APP_VERSION__,
        locale: navigator.language,
      },
    });
  } catch {
    // Registration is retried on next app start; do not block local alerts.
  }
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
