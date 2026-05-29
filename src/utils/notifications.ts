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
