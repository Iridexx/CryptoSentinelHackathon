import { Capacitor } from '@capacitor/core';
import { LocalNotifications } from '@capacitor/local-notifications';

let notifIdCounter = 1;

export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (Capacitor.isNativePlatform()) {
    const result = await LocalNotifications.requestPermissions();
    return result.display === 'granted' ? 'granted' : 'denied';
  }
  if (!('Notification' in window)) return 'denied';
  if (Notification.permission === 'granted') return 'granted';
  if (Notification.permission === 'denied') return 'denied';
  return await Notification.requestPermission();
}

export async function getNotificationPermissionAsync(): Promise<NotificationPermission> {
  if (Capacitor.isNativePlatform()) {
    const result = await LocalNotifications.checkPermissions();
    return result.display === 'granted' ? 'granted' : 'denied';
  }
  if (!('Notification' in window)) return 'denied';
  return Notification.permission;
}

export function getNotificationPermission(): NotificationPermission {
  if (Capacitor.isNativePlatform()) return 'granted'; // inizialmente ottimistico, aggiornato async
  if (!('Notification' in window)) return 'denied';
  return Notification.permission;
}

export async function sendAlertNotification(params: {
  coinName: string;
  direction: 'above' | 'below';
  threshold: number;
  currentPrice: number;
}): Promise<void> {
  const { coinName, direction, threshold, currentPrice } = params;
  const symbol = direction === 'above' ? '▲' : '▼';
  const dirLabel = direction === 'above' ? 'superato' : 'sceso sotto';
  const title = `${symbol} Allarme ${coinName}`;
  const body = `${coinName} ha ${dirLabel} $${threshold.toLocaleString('it-IT')} — Attuale: $${currentPrice.toLocaleString('it-IT')}`;

  if (Capacitor.isNativePlatform()) {
    try {
      await LocalNotifications.schedule({
        notifications: [
          {
            id: notifIdCounter++,
            title,
            body,
            sound: 'beep.wav',
            smallIcon: 'ic_stat_icon_config_sample',
            iconColor: '#F59E0B',
            extra: { coinName, direction, threshold },
          },
        ],
      });
    } catch {
      // permessi non concessi
    }
    return;
  }

  // Fallback web: Service Worker
  if (!('serviceWorker' in navigator)) return;
  try {
    const reg = await navigator.serviceWorker.ready;
    reg.active?.postMessage({ type: 'PRICE_ALERT', ...params });
  } catch { /* SW non disponibile */ }
}
