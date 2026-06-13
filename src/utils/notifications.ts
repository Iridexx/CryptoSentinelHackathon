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
let pushRegistrationStarted = false;

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
