import { Capacitor, registerPlugin } from '@capacitor/core';

interface AppSettingsPlugin {
  openNotifications(): Promise<void>;
  openWithChooser(options: { url: string; title?: string }): Promise<void>;
}

const AppSettings = registerPlugin<AppSettingsPlugin>('AppSettings');

export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!('Notification' in window)) return 'denied';
  if (Notification.permission === 'granted') return 'granted';
  if (Notification.permission === 'denied') return 'denied';
  return await Notification.requestPermission();
}

export function getNotificationPermission(): NotificationPermission {
  if (!('Notification' in window)) return 'denied';
  return Notification.permission;
}

export function openNotificationSettings(): void {
  if (Capacitor.isNativePlatform()) {
    AppSettings.openNotifications().catch(() => {
      window.open('app-settings:', '_system');
    });
  }
}

export async function sendAlertNotification(params: {
  coinName: string;
  direction: 'above' | 'below';
  threshold: number;
  currentPrice: number;
}): Promise<void> {
  if (!('serviceWorker' in navigator)) return;

  const reg = await navigator.serviceWorker.ready;
  if (!reg.active) return;

  // Invia al SW il messaggio per mostrare la notifica
  reg.active.postMessage({
    type: 'PRICE_ALERT',
    ...params,
  });
}
