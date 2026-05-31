import { useRef, useState, useCallback, useEffect } from 'react';

const TRIGGER_THRESHOLD = 60;
const MAX_PULL = 88;
const DAMPING = 0.5;

export function usePullToRefresh(onRefresh: () => Promise<void> | void) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [pullY, setPullY] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const startYRef = useRef<number | null>(null);
  const pullYRef = useRef(0);
  const isRefreshingRef = useRef(false);

  const handleTouchStart = useCallback((e: TouchEvent) => {
    const el = containerRef.current;
    if (!el || el.scrollTop > 0 || isRefreshingRef.current) return;
    startYRef.current = e.touches[0].clientY;
  }, []);

  const handleTouchMove = useCallback((e: TouchEvent) => {
    const el = containerRef.current;
    if (!el || startYRef.current === null) return;
    if (el.scrollTop > 0) { startYRef.current = null; pullYRef.current = 0; setPullY(0); return; }
    const dy = e.touches[0].clientY - startYRef.current;
    if (dy <= 0) return;
    e.preventDefault();
    const clamped = Math.min(dy * DAMPING, MAX_PULL);
    pullYRef.current = clamped;
    setPullY(clamped);
  }, []);

  const handleTouchEnd = useCallback(async () => {
    if (startYRef.current === null && pullYRef.current === 0) return;
    const dist = pullYRef.current;
    startYRef.current = null;
    pullYRef.current = 0;
    setPullY(0);
    if (dist >= TRIGGER_THRESHOLD && !isRefreshingRef.current) {
      isRefreshingRef.current = true;
      setIsRefreshing(true);
      try { await onRefresh(); } finally {
        isRefreshingRef.current = false;
        setIsRefreshing(false);
      }
    }
  }, [onRefresh]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener('touchstart', handleTouchStart, { passive: true });
    el.addEventListener('touchmove', handleTouchMove, { passive: false });
    el.addEventListener('touchend', handleTouchEnd);
    return () => {
      el.removeEventListener('touchstart', handleTouchStart);
      el.removeEventListener('touchmove', handleTouchMove);
      el.removeEventListener('touchend', handleTouchEnd);
    };
  }, [handleTouchStart, handleTouchMove, handleTouchEnd]);

  return { containerRef, pullY, isRefreshing };
}
