import { type FC, type PointerEvent, useEffect, useRef, useState } from 'react';

export interface AxisGeom {
  W: number;
  H: number;
  plotL: number;
  plotR: number;
  plotT: number;
  plotB: number;
}

export type Range = [number, number];

interface Props {
  geom: AxisGeom;
  /** Dominio Y attualmente mostrato e dominio "auto" (tutto il dato). */
  yDom: Range;
  yFull: Range;
  onY: (r: Range | null) => void;
  /** Finestra X attualmente mostrata ed estensione completa (in unita' di indice). */
  xWin: Range;
  xFull: Range;
  /** Ampiezza minima della finestra X (es. 5 candele). */
  xMinSpan: number;
  onX: (r: Range | null) => void;
  /**
   * Pan del grafico. Mouse: trascinando. Touch: a grafico zoomato trascinando in qualsiasi direzione;
   * a grafico intero in orizzontale, oppure tenendo premuto un istante e poi trascinando in qualsiasi
   * direzione (cosi' lo scroll verticale della pagina resta libero finche' non serve il pan).
   */
  pan?: boolean;
  /** Puntatore (mouse) che si muove sul grafico senza premere: serve a chi mostra un crosshair. */
  onHover?: (clientX: number | null) => void;
  /** Lato dell'asse prezzo (default: destra). */
  yAxis?: 'left' | 'right';
}

const SENS = 0.008; // ~ x2 di zoom ogni 87px di trascinamento
const TAP_MS = 350;
const TAP_MOVE_PX = 6;
const HOLD_MS = 200;
const HOLD_JITTER_PX = 10;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const pct = (v: number) => `${(v * 100).toFixed(3)}%`;

type Drag =
  | { kind: 'y'; sx: number; sy: number; lo: number; hi: number; anchor: number; frac: number }
  | { kind: 'x'; sx: number; sy: number; a: number; b: number; anchor: number; frac: number }
  | { kind: 'pan'; sx: number; sy: number; a: number; b: number; lo: number; hi: number; touch: boolean };

/**
 * Strisce trasparenti sopra gli assi di un grafico SVG (il contenitore deve essere `relative`
 * e avere la stessa proporzione del viewBox).
 * - Asse prezzo: trascina in alto = zoom, in basso = riduzione (ancorato al punto toccato).
 * - Asse tempo: trascina a destra o in alto = zoom, a sinistra o in basso = riduzione.
 * - Doppio tap sull'asse: ripristina la scala automatica.
 */
const AxisZoomOverlay: FC<Props> = ({ geom, yDom, yFull, onY, xWin, xFull, xMinSpan, onX, pan = false, onHover, yAxis = 'right' }) => {
  const { W, H, plotL, plotR, plotT, plotB } = geom;
  // A grafico zoomato il pan touch e' libero da subito: il grafico si prende il gesto (touch-action: none).
  const zoomedNow = xWin[0] !== xFull[0] || xWin[1] !== xFull[1] || yDom[0] !== yFull[0] || yDom[1] !== yFull[1];
  const drag = useRef<Drag | null>(null);
  const lastTap = useRef<{ kind: string; t: number }>({ kind: '', t: 0 });
  const [active, setActive] = useState<'y' | 'x' | 'pan' | null>(null);
  // "Pressione lunga" raggiunta: da ora il pan touch vale anche in verticale.
  const holdRef = useRef(false);
  const holdTimer = useRef<number | undefined>(undefined);
  const [held, setHeld] = useState(false);
  const panEl = useRef<HTMLDivElement | null>(null);

  // Dopo la pressione lunga il touchmove non deve far partire lo scroll della pagina.
  useEffect(() => {
    const el = panEl.current;
    if (!el) return;
    const block = (e: TouchEvent) => { if (holdRef.current && e.cancelable) e.preventDefault(); };
    el.addEventListener('touchmove', block, { passive: false });
    return () => el.removeEventListener('touchmove', block);
  }, [pan]);

  const stopHold = () => {
    window.clearTimeout(holdTimer.current);
    holdRef.current = false;
    setHeld(false);
  };

  const start = (kind: 'y' | 'x' | 'pan') => (e: PointerEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const sx = e.clientX;
    const sy = e.clientY;
    if (kind === 'y') {
      const frac = (e.clientY - rect.top) / rect.height;
      drag.current = { kind, sx, sy, lo: yDom[0], hi: yDom[1], frac, anchor: yDom[1] - frac * (yDom[1] - yDom[0]) };
    } else if (kind === 'x') {
      const frac = (e.clientX - rect.left) / rect.width;
      drag.current = { kind, sx, sy, a: xWin[0], b: xWin[1], frac, anchor: xWin[0] + frac * (xWin[1] - xWin[0]) };
    } else {
      const touch = e.pointerType === 'touch';
      drag.current = { kind, sx, sy, a: xWin[0], b: xWin[1], lo: yDom[0], hi: yDom[1], touch };
      window.clearTimeout(holdTimer.current);
      holdRef.current = !touch || zoomedNow;
      if (touch && !zoomedNow) {
        holdTimer.current = window.setTimeout(() => {
          holdRef.current = true;
          setHeld(true);
          navigator.vibrate?.(8);
        }, HOLD_MS);
      }
    }
    setActive(kind);
  };

  const move = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.sx;
    const dy = e.clientY - d.sy;
    if (d.kind === 'y') {
      const span0 = d.hi - d.lo;
      const fullSpan = yFull[1] - yFull[0];
      const span = clamp(span0 * Math.exp(dy * SENS), fullSpan * 0.02, fullSpan * 20);
      const hi = d.anchor + d.frac * span;
      onY([hi - span, hi]);
    } else if (d.kind === 'x') {
      const fullSpan = xFull[1] - xFull[0];
      const span = clamp((d.b - d.a) * Math.exp(-(dx - dy) * SENS), Math.min(xMinSpan, fullSpan), fullSpan);
      const a = clamp(d.anchor - d.frac * span, xFull[0], xFull[1] - span);
      onX([a, a + span]);
    } else {
      // Un movimento prima della pressione lunga e' uno swipe: niente hold, lo scroll verticale resta alla pagina.
      if (d.touch && !holdRef.current && Math.hypot(dx, dy) > HOLD_JITTER_PX) window.clearTimeout(holdTimer.current);
      const rect = e.currentTarget.getBoundingClientRect();
      const span = d.b - d.a;
      const a = clamp(d.a - (dx / rect.width) * span, xFull[0], xFull[1] - span);
      if (a !== d.a) onX([a, a + span]);
      if (holdRef.current && dy !== 0) {
        const ySpan = d.hi - d.lo;
        const lo = clamp(d.lo + (dy / rect.height) * ySpan, yFull[0] - ySpan, yFull[1]);
        onY([lo, lo + ySpan]);
      }
    }
  };

  const end = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    drag.current = null;
    setActive(null);
    stopHold();
    if (!d || e.type === 'pointercancel') return;
    const moved = Math.hypot(e.clientX - d.sx, e.clientY - d.sy);
    if (moved > TAP_MOVE_PX || d.kind === 'pan') return;
    const now = e.timeStamp;
    if (lastTap.current.kind === d.kind && now - lastTap.current.t < TAP_MS) {
      (d.kind === 'y' ? onY : onX)(null);
      lastTap.current = { kind: '', t: 0 };
    } else {
      lastTap.current = { kind: d.kind, t: now };
    }
  };

  const strip = (
    kind: 'y' | 'x' | 'pan',
    left: number,
    top: number,
    width: number,
    height: number,
    touchAction: string,
    cursor: string,
  ) => (
    <div
      ref={kind === 'pan' ? panEl : undefined}
      style={{
        position: 'absolute',
        left: pct(left / W),
        top: pct(top / H),
        width: pct(width / W),
        height: pct(height / H),
        touchAction,
        cursor,
        pointerEvents: 'auto',
        background: kind === 'pan' && held ? 'rgba(255,255,255,0.05)' : active === kind && kind !== 'pan' ? 'rgba(255,255,255,0.06)' : 'transparent',
      }}
      onPointerDown={start(kind)}
      onPointerMove={(e) => {
        if (kind === 'pan' && !drag.current && e.pointerType === 'mouse') onHover?.(e.clientX);
        move(e);
      }}
      onPointerLeave={kind === 'pan' ? () => onHover?.(null) : undefined}
      onPointerUp={end}
      onPointerCancel={end}
    />
  );

  return (
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
      {pan && strip('pan', plotL, plotT, plotR - plotL, plotB - plotT, zoomedNow ? 'none' : 'pan-y', 'grab')}
      {yAxis === 'left'
        ? strip('y', 0, plotT, plotL, plotB - plotT, 'none', 'ns-resize')
        : strip('y', plotR, plotT, W - plotR, plotB - plotT, 'none', 'ns-resize')}
      {strip('x', plotL, plotB, plotR - plotL, H - plotB, 'none', 'ew-resize')}
    </div>
  );
};

export default AxisZoomOverlay;
