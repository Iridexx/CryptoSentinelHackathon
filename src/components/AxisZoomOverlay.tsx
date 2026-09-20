import { type FC, type PointerEvent, useRef, useState } from 'react';

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
  /** Trascinare sul grafico in orizzontale sposta la finestra (solo dove non c'e' scrubbing). */
  pan?: boolean;
  /** Lato dell'asse prezzo (default: destra). */
  yAxis?: 'left' | 'right';
}

const SENS = 0.008; // ~ x2 di zoom ogni 87px di trascinamento
const TAP_MS = 350;
const TAP_MOVE_PX = 6;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const pct = (v: number) => `${(v * 100).toFixed(3)}%`;

type Drag =
  | { kind: 'y'; sx: number; sy: number; lo: number; hi: number; anchor: number; frac: number }
  | { kind: 'x'; sx: number; sy: number; a: number; b: number; anchor: number; frac: number }
  | { kind: 'pan'; sx: number; sy: number; a: number; b: number };

/**
 * Strisce trasparenti sopra gli assi di un grafico SVG (il contenitore deve essere `relative`
 * e avere la stessa proporzione del viewBox).
 * - Asse prezzo: trascina in alto = zoom, in basso = riduzione (ancorato al punto toccato).
 * - Asse tempo: trascina a destra o in alto = zoom, a sinistra o in basso = riduzione.
 * - Doppio tap sull'asse: ripristina la scala automatica.
 */
const AxisZoomOverlay: FC<Props> = ({ geom, yDom, yFull, onY, xWin, xFull, xMinSpan, onX, pan = false, yAxis = 'right' }) => {
  const { W, H, plotL, plotR, plotT, plotB } = geom;
  const drag = useRef<Drag | null>(null);
  const lastTap = useRef<{ kind: string; t: number }>({ kind: '', t: 0 });
  const [active, setActive] = useState<'y' | 'x' | 'pan' | null>(null);

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
      drag.current = { kind, sx, sy, a: xWin[0], b: xWin[1] };
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
      const rect = e.currentTarget.getBoundingClientRect();
      const span = d.b - d.a;
      const a = clamp(d.a - (dx / rect.width) * span, xFull[0], xFull[1] - span);
      onX([a, a + span]);
    }
  };

  const end = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    drag.current = null;
    setActive(null);
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
      style={{
        position: 'absolute',
        left: pct(left / W),
        top: pct(top / H),
        width: pct(width / W),
        height: pct(height / H),
        touchAction,
        cursor,
        pointerEvents: 'auto',
        background: active === kind ? 'rgba(255,255,255,0.06)' : 'transparent',
      }}
      onPointerDown={start(kind)}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
    />
  );

  return (
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
      {pan && strip('pan', plotL, plotT, plotR - plotL, plotB - plotT, 'pan-y', 'grab')}
      {yAxis === 'left'
        ? strip('y', 0, plotT, plotL, plotB - plotT, 'none', 'ns-resize')
        : strip('y', plotR, plotT, W - plotR, plotB - plotT, 'none', 'ns-resize')}
      {strip('x', plotL, plotB, plotR - plotL, H - plotB, 'none', 'ew-resize')}
    </div>
  );
};

export default AxisZoomOverlay;
