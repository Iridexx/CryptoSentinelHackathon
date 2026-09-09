import { useMemo, useState } from 'react';
import type { FeedEventItem } from './types';
import type { UseNotificationsReturn } from './notifications';

type CategoryFilter = 'all' | 'spot_trade' | 'perp_trade' | 'risk' | 'reserve' | 'system' | 'summary';
type SeverityFilter = 'all' | 'info' | 'normal' | 'critical';

const CATEGORY_LABELS: Record<string, string> = {
  all: 'Tutte',
  spot_trade: 'Spot',
  perp_trade: 'Perp',
  risk: 'Rischio',
  reserve: 'Riserva',
  system: 'Sistema',
  summary: 'Riepilogo',
};

const SEVERITY_LABELS: Record<string, string> = {
  all: 'Tutte',
  info: 'Info',
  normal: 'Normale',
  critical: 'Critico',
};

const CATEGORY_ICON: Record<string, string> = {
  spot_trade: '\u{1F4B9}',
  perp_trade: '\u{1F4C8}',
  risk: '\u{26A0}\u{FE0F}',
  system: '\u{1F6A8}',
  reserve: '\u{1F3E6}',
  summary: '\u{1F4CA}',
};

function groupByDay(items: FeedEventItem[]): [string, FeedEventItem[]][] {
  const groups = new Map<string, FeedEventItem[]>();
  for (const item of items) {
    const day = item.created_at.slice(0, 10);
    const list = groups.get(day);
    if (list) list.push(item);
    else groups.set(day, [item]);
  }
  return Array.from(groups.entries());
}

function formatDay(iso: string): string {
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  if (iso === today) return 'Oggi';
  if (iso === yesterday) return 'Ieri';
  return new Date(iso + 'T00:00:00').toLocaleDateString('it-IT', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

export default function NotificationsPanel({
  notifications,
}: {
  notifications: UseNotificationsReturn;
}) {
  const { items, unreadCount, loading, markRead, markAllRead, loadMore, hasMore } = notifications;

  const [category, setCategory] = useState<CategoryFilter>('all');
  const [severity, setSeverity] = useState<SeverityFilter>('all');
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    let result = items;
    if (category !== 'all') result = result.filter((i) => i.category === category);
    if (severity !== 'all') result = result.filter((i) => i.severity === severity);
    if (unreadOnly) result = result.filter((i) => !i.read_at);
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (i) => i.title.toLowerCase().includes(q) || i.body.toLowerCase().includes(q),
      );
    }
    return result;
  }, [items, category, severity, unreadOnly, search]);

  const groups = useMemo(() => groupByDay(filtered), [filtered]);

  return (
    <div className="notif-panel">
      <div className="notif-toolbar">
        <div className="notif-filters">
          <select value={category} onChange={(e) => setCategory(e.target.value as CategoryFilter)}>
            {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <select value={severity} onChange={(e) => setSeverity(e.target.value as SeverityFilter)}>
            {Object.entries(SEVERITY_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <label className="notif-unread-toggle">
            <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
            Solo non lette
          </label>
          <input
            type="text"
            placeholder="Cerca..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="notif-search"
          />
        </div>
        <div className="notif-actions">
          {unreadCount > 0 && (
            <button onClick={() => void markAllRead()}>
              Segna tutte lette ({unreadCount})
            </button>
          )}
        </div>
      </div>

      {items.length === 0 && !loading && (
        <p className="notif-empty">Nessuna notifica.</p>
      )}

      {groups.map(([day, dayItems]) => (
        <div key={day} className="notif-day-group">
          <div className="notif-day-header">{formatDay(day)}</div>
          {dayItems.map((item) => (
            <div
              key={item.event_id}
              className={`notif-item ${!item.read_at ? 'notif-item--unread' : ''} notif-item--${item.severity}`}
              onClick={() => { if (!item.read_at) void markRead([item.event_id]); }}
            >
              <span className="notif-item__icon">{CATEGORY_ICON[item.category] || '\u{1F514}'}</span>
              <div className="notif-item__content">
                <div className="notif-item__title">
                  {item.title}
                  <span className="notif-item__time">{formatTime(item.created_at)}</span>
                </div>
                <div className="notif-item__body">{item.body}</div>
              </div>
              {!item.read_at && <span className="notif-item__dot" />}
            </div>
          ))}
        </div>
      ))}

      {hasMore && (
        <button className="notif-load-more" onClick={() => void loadMore()} disabled={loading}>
          {loading ? 'Caricamento...' : 'Carica precedenti'}
        </button>
      )}
    </div>
  );
}
