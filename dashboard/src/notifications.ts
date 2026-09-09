import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { DashboardSession } from './api';
import { fetchFeed, markFeedRead, normalizeBackendBaseUrl } from './api';
import type { FeedEventItem, FeedResponse, ToastPreferences } from './types';

const POLL_INTERVAL_MS = 10_000;

export type NotificationState = {
  items: FeedEventItem[];
  unreadCount: number;
  newItems: FeedEventItem[];
  loading: boolean;
  error: string | null;
};

export type UseNotificationsReturn = NotificationState & {
  markRead: (ids: string[]) => Promise<void>;
  markAllRead: () => Promise<void>;
  loadMore: () => Promise<void>;
  hasMore: boolean;
};

export function useNotifications(
  session: DashboardSession | null,
  toastPrefs: ToastPreferences | null,
  dnd: boolean,
): UseNotificationsReturn {
  const [items, setItems] = useState<FeedEventItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [newItems, setNewItems] = useState<FeedEventItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);

  const cursorRef = useRef<string | null>(null);
  const initialLoadDone = useRef(false);
  const dndRef = useRef(dnd);
  dndRef.current = dnd;
  const toastPrefsRef = useRef(toastPrefs);
  toastPrefsRef.current = toastPrefs;

  const applyFresh = useCallback((fresh: FeedEventItem[], unread: number) => {
    if (fresh.length === 0) {
      setUnreadCount(unread);
      return;
    }
    setItems(prev => {
      const existingIds = new Set(prev.map(i => i.event_id));
      const deduped = fresh.filter(i => !existingIds.has(i.event_id));
      return [...deduped.reverse(), ...prev];
    });
    cursorRef.current = fresh[fresh.length - 1].event_id;
    setUnreadCount(unread);

    if (!dndRef.current && toastPrefsRef.current) {
      const prefs = toastPrefsRef.current;
      const toastable = fresh.filter(item => {
        const key = `toast_${item.category}` as keyof ToastPreferences;
        return prefs[key] ?? false;
      });
      if (toastable.length > 0) {
        setNewItems(toastable);
      }
    }
  }, []);

  const doInitialLoad = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    try {
      const res = await fetchFeed(session, { limit: 50 });
      setItems(res.items);
      setUnreadCount(res.unread_count);
      setHasMore(res.items.length >= 50);
      if (res.items.length > 0) {
        cursorRef.current = res.items[0].event_id;
      }
      setError(null);
      initialLoadDone.current = true;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    doInitialLoad();
  }, [doInitialLoad]);

  // SSE with polling fallback
  useEffect(() => {
    if (!session || !initialLoadDone.current) return;

    let aborted = false;
    const ctrl = new AbortController();

    const startSSE = () => {
      const base = normalizeBackendBaseUrl(session.baseUrl);
      const since = cursorRef.current ? `?since=${encodeURIComponent(cursorRef.current)}` : '';
      const url = `${base}/api/v1/notifications/feed/stream${since}`;

      fetchEventSource(url, {
        signal: ctrl.signal,
        headers: {
          Authorization: `Bearer ${session.readToken}`,
          Accept: 'text/event-stream',
        },
        onmessage(ev) {
          if (aborted) return;
          try {
            const data: FeedResponse = JSON.parse(ev.data);
            applyFresh(data.items, data.unread_count);
          } catch { /* malformed event */ }
        },
        onerror() {
          // Fall back to polling on SSE failure
          return 5000;
        },
        openWhenHidden: false,
      }).catch(() => {});
    };

    // Try SSE first
    startSSE();

    // Polling fallback: runs alongside SSE but only fires when SSE isn't delivering
    const doPoll = async () => {
      if (aborted || !initialLoadDone.current) return;
      try {
        const since = cursorRef.current ?? undefined;
        const res = await fetchFeed(session, { since, limit: 200 });
        applyFresh(res.items, res.unread_count);
        setError(null);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
      }
    };

    const timer = setInterval(() => {
      if (!document.hidden) doPoll();
    }, POLL_INTERVAL_MS);

    const onVisibility = () => {
      if (!document.hidden) doPoll();
    };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      aborted = true;
      ctrl.abort();
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [session, applyFresh]);

  useEffect(() => {
    if (newItems.length > 0) {
      const t = setTimeout(() => setNewItems([]), 100);
      return () => clearTimeout(t);
    }
  }, [newItems]);

  const markRead = useCallback(async (ids: string[]) => {
    if (!session || ids.length === 0) return;
    try {
      const res = await markFeedRead(session, { ids });
      setUnreadCount(res.unread_count);
      setItems(prev => prev.map(i =>
        ids.includes(i.event_id) ? { ...i, read_at: new Date().toISOString() } : i,
      ));
    } catch { /* silent */ }
  }, [session]);

  const markAllRead = useCallback(async () => {
    if (!session) return;
    try {
      const res = await markFeedRead(session, { all: true });
      setUnreadCount(res.unread_count);
      setItems(prev => prev.map(i =>
        i.read_at ? i : { ...i, read_at: new Date().toISOString() },
      ));
    } catch { /* silent */ }
  }, [session]);

  const loadMore = useCallback(async () => {
    if (!session || !hasMore || loading) return;
    const oldest = items[items.length - 1];
    if (!oldest) return;
    setLoading(true);
    try {
      const res = await fetchFeed(session, { before: oldest.event_id, limit: 50 });
      if (res.items.length > 0) {
        setItems(prev => [...prev, ...res.items]);
      }
      setHasMore(res.items.length >= 50);
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  }, [session, hasMore, loading, items]);

  return {
    items,
    unreadCount,
    newItems,
    loading,
    error,
    markRead,
    markAllRead,
    loadMore,
    hasMore,
  };
}
