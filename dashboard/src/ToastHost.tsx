import { useCallback, useEffect, useRef, useState } from 'react';
import type { FeedEventItem } from './types';

const TOAST_DURATION_MS = 6000;
const MAX_VISIBLE = 5;

type ToastEntry = FeedEventItem & { _id: number; _progress: number; _paused: boolean };

const SEVERITY_CLASS: Record<string, string> = {
  critical: 'toast--critical',
  normal: 'toast--normal',
  info: 'toast--info',
};

const CATEGORY_ICON: Record<string, string> = {
  spot_trade: '\u{1F4B9}',
  perp_trade: '\u{1F4C8}',
  risk: '\u{26A0}\u{FE0F}',
  system: '\u{1F6A8}',
  reserve: '\u{1F3E6}',
  summary: '\u{1F4CA}',
};

let _nextId = 1;

export default function ToastHost({
  newItems,
  onDismiss,
  soundEnabled,
}: {
  newItems: FeedEventItem[];
  onDismiss?: (eventId: string) => void;
  soundEnabled: boolean;
}) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (newItems.length === 0) return;
    const entries: ToastEntry[] = newItems.map((item) => ({
      ...item,
      _id: _nextId++,
      _progress: 100,
      _paused: false,
    }));
    setToasts((prev) => [...entries, ...prev].slice(0, MAX_VISIBLE));

    if (soundEnabled) {
      const hasCritical = newItems.some((i) => i.severity === 'critical');
      if (hasCritical) playSound(audioRef);
    }
  }, [newItems, soundEnabled]);

  useEffect(() => {
    if (toasts.length === 0) return;
    const TICK = 50;
    const decrement = (TICK / TOAST_DURATION_MS) * 100;
    const timer = setInterval(() => {
      setToasts((prev) => {
        const next = prev
          .map((t) =>
            t._paused ? t : { ...t, _progress: t._progress - decrement },
          )
          .filter((t) => t._progress > 0);
        return next;
      });
    }, TICK);
    return () => clearInterval(timer);
  }, [toasts.length > 0]);

  const dismiss = useCallback(
    (id: number, eventId: string) => {
      setToasts((prev) => prev.filter((t) => t._id !== id));
      onDismiss?.(eventId);
    },
    [onDismiss],
  );

  const pause = useCallback((id: number) => {
    setToasts((prev) =>
      prev.map((t) => (t._id === id ? { ...t, _paused: true } : t)),
    );
  }, []);

  const resume = useCallback((id: number) => {
    setToasts((prev) =>
      prev.map((t) => (t._id === id ? { ...t, _paused: false } : t)),
    );
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="toast-host" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t._id}
          className={`toast ${SEVERITY_CLASS[t.severity] || 'toast--info'}`}
          onMouseEnter={() => pause(t._id)}
          onMouseLeave={() => resume(t._id)}
        >
          <div className="toast__head">
            <span className="toast__icon">
              {CATEGORY_ICON[t.category] || '\u{1F514}'}
            </span>
            <span className="toast__title">{t.title}</span>
            <button
              className="toast__close"
              onClick={() => dismiss(t._id, t.event_id)}
              aria-label="Chiudi"
            >
              ×
            </button>
          </div>
          <div className="toast__body">{t.body}</div>
          <div className="toast__bar-track">
            <div
              className="toast__bar"
              style={{ width: `${Math.max(0, t._progress)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function playSound(audioRef: React.MutableRefObject<HTMLAudioElement | null>) {
  try {
    if (!audioRef.current) {
      audioRef.current = new Audio(
        'data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1iZWNhW1RYWl5iZ2t0fIONl6CnrrO2uLm5ubi1sK2oo56Yko2Ih4WHioyPk5aZnJ6goKCgnpuZlpOQjo2Mi4uMjI2Oj5CSk5WXmJqbnJ2dnZyamJaUkpCPjo6Ojo+PkJGSk5SVlpeYmJmZmZiYl5aVlJOSkZGQkJCRkZKSk5OUlJWVlpaWl5eXl5aWlpWUlJOTk5OTk5OUlJSVlZWWlpaWlpeXl5eXl5eXlpaWlZWVlZWVlZWVlpaWlpaWlpaWlpaWlpaWlpaWlpaVlZWVlZWVlZWVlpaWlpaWlpaW',
      );
      audioRef.current.volume = 0.3;
    }
    audioRef.current.currentTime = 0;
    audioRef.current.play().catch(() => {});
  } catch { /* silent */ }
}
