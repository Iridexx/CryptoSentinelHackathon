import { Capacitor, registerPlugin } from '@capacitor/core';
import { LocalNotifications } from '@capacitor/local-notifications';

interface AppSettingsPlugin {
  openNotifications(): Promise<void>;
  openWithChooser(options: { url: string; title?: string }): Promise<void>;
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

export async function sendAlertNotification(params: {
  coinName: string;
  direction: 'above' | 'below';
  threshold: number;
  currentPrice: number;
}): Promise<void> {
  if (Capacitor.isNativePlatform()) {
    try {
      const perm = await LocalNotifications.checkPermissions();
      if (perm.display !== 'granted') return;
      await LocalNotifications.schedule({
        notifications: [{
          id: Math.floor(Math.random() * 2_000_000),
          channelId: 'price_alerts',
          title: `🚨 ${params.coinName}`,
          body: `Prezzo ${params.direction === 'above' ? 'sopra' : 'sotto'} $${params.threshold.toLocaleString()} · Attuale: $${params.currentPrice.toLocaleString()}`,
          sound: 'default',
          smallIcon: 'ic_launcher',
          autoCancel: true,
        }],
      });
    } catch {
      // notifica fallita silenziosamente
    }
    return;
  }
}

export function openNotificationSettings(): void {
  if (Capacitor.isNativePlatform()) {
    AppSettings.openNotifications().catch(() => {
      window.open('app-settings:', '_system');
    });
  }
}
