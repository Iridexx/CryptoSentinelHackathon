import { useCallback, useEffect, useRef, useState, type FC } from 'react';
import type { Coin } from '../types';
import type { Currency } from '../hooks/useCurrency';
import type { FavAlertData } from '../hooks/useFavoritePriceAlerts';
import { hapticMedium, hapticLight } from '../utils/haptics';

const SYMBOL: Record<Currency, string> = { usd: '$', eur: '€', btc: '₿' };

function formatPrice(price: number | null | undefined, currency: Currency): string {
  if (price == null || !isFinite(price)) return '—';
  if (currency === 'btc') {
    if (price >= 0.001) return price.toLocaleString('it-IT', { minimumFractionDigits: 4, maximumFractionDigits: 6 });
    return price.toFixed(8);
  }
  if (price >= 1000) return price.toLocaleString('it-IT', { maximumFractionDigits: 0 });
  if (price >= 1) return price.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return price.toLocaleString('it-IT', { minimumFractionDigits: 4, maximumFractionDigits: 6 });
}

function formatMarketCap(val: number | null | undefined, currency: Currency): string {
  if (val == null || !isFinite(val)) return '—';
  const sym = SYMBOL[currency];
  if (currency === 'btc') {
    if (val >= 1e6) return `${sym}${(val / 1e6).toFixed(2)}M`;
    if (val >= 1000) return `${sym}${(val / 1000).toFixed(1)}K`;
    return `${sym}${val.toFixed(2)}`;
  }
  if (val >= 1e12) return `${sym}${(val / 1e12).toFixed(2)}T`;
  if (val >= 1e9) return `${sym}${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `${sym}${(val / 1e6).toFixed(2)}M`;
  return `${sym}${val.toLocaleString('it-IT')}`;
}

type TimeFrame = '1h' | '24h' | '7d';

interface Props {
  coin: Coin;
  isFavorite: boolean;
  onToggleFavorite: (id: string) => void;
  onAddAlert: (coin: Coin) => void;
  onChartTap: (coin: Coin) => void;
  currency: Currency;
  showVolume?: boolean;
  timeFrame?: TimeFrame;
  alertPending?: FavAlertData;
  onAlertTap?: () => void;
  rankDelta?: number;
}

const CoinCard: FC<Props> = ({ coin, isFavorite, onToggleFavorite, onAddAlert, onChartTap, currency, showVolume, timeFrame = '24h', alertPending, onAlertTap, rankDelta }) => {
  const displayChange =
    timeFrame === '1h' ? (coin.price_change_percentage_1h_in_currency ?? coin.price_change_percentage_24h ?? 0) :
    timeFrame === '7d' ? (coin.price_change_percentage_7d_in_currency ?? coin.price_change_percentage_24h ?? 0) :
    (coin.price_change_percentage_24h ?? 0);
  const isPositive = displayChange >= 0;
  const sym = SYMBOL[currency];

  const prevPriceRef = useRef(coin.current_price);
  const [flash, setFlash] = useState<'up' | 'down' | null>(null);

  useEffect(() => {
    const prev = prevPriceRef.current;
    if (prev === coin.current_price) return;
    prevPriceRef.current = coin.current_price;
    setFlash(coin.current_price > prev ? 'up' : 'down');
    const t = setTimeout(() => setFlash(null), 800);
    return () => clearTimeout(t);
  }, [coin.current_price]);

  // Rank change animation
  const cardRef = useRef<HTMLDivElement>(null);
  const isVisibleRef = useRef(false);
  const pendingRankDeltaRef = useRef<number | null>(null);
  const rankFlashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevRankDeltaRef = useRef<number | undefined>(undefined);
  const [rankFlash, setRankFlash] = useState<number | null>(null);

  const fireRankFlash = useCallback((delta: number) => {
    if (rankFlashTimerRef.current) clearTimeout(rankFlashTimerRef.current);
    setRankFlash(delta);
    rankFlashTimerRef.current = setTimeout(() => setRankFlash(null), 3500);
  }, []);

  useEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        isVisibleRef.current = entry.isIntersecting;
        if (entry.isIntersecting && pendingRankDeltaRef.current !== null) {
          const delta = pendingRankDeltaRef.current;
          pendingRankDeltaRef.current = null;
          fireRankFlash(delta);
        }
      },
      { threshold: 0.3 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [fireRankFlash]);

  useEffect(() => {
    if (rankDelta === undefined) {
      prevRankDeltaRef.current = undefined;
      return;
    }
    if (rankDelta === 0 || rankDelta === prevRankDeltaRef.current) return;
    prevRankDeltaRef.current = rankDelta;
    if (isVisibleRef.current) {
      fireRankFlash(rankDelta);
    } else {
      pendingRankDeltaRef.current = rankDelta;
    }
  }, [rankDelta, fireRankFlash]);

  const cardBg = rankFlash !== null
    ? rankFlash > 0
      ? 'bg-[#0c1f0c] ring-2 ring-green-500/60'
      : 'bg-[#1f0c0c] ring-2 ring-red-500/60'
    : alertPending
      ? 'bg-[#1c1208] ring-2 ring-orange-500/60 hover:bg-[#221508]'
      : 'bg-dark-800 hover:bg-dark-700';

  return (
    <div ref={cardRef} className={`flex items-center gap-3 rounded-xl p-3 transition-colors relative ${cardBg}`}>
      {alertPending && (
        <span className="absolute top-1.5 right-10 w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
      )}
      {rankFlash !== null && (
        <span className={`absolute top-1 left-1 flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full animate-pulse z-10 ${
          rankFlash > 0 ? 'bg-green-500/30 text-green-400' : 'bg-red-500/30 text-red-400'
        }`}>
          {rankFlash > 0 ? `▲ +${rankFlash}` : `▼ ${rankFlash}`}
        </span>
      )}

      {/* Tappable area (separata dai bottoni) */}
      <div
        className={`flex items-center gap-3 flex-1 min-w-0 ${alertPending ? 'cursor-pointer' : ''}`}
        onClick={alertPending && onAlertTap ? onAlertTap : undefined}
      >
        <span className="text-xs text-white font-mono w-6 text-right flex-shrink-0 tabular-nums">
          {coin.market_cap_rank ?? '—'}
        </span>
        <img src={coin.image} alt={coin.name} className="w-9 h-9 rounded-full flex-shrink-0" loading="lazy" />

        <div
          className="flex-1 min-w-0 cursor-pointer active:opacity-70"
          onClick={(e) => { e.stopPropagation(); hapticLight(); onChartTap(coin); }}
        >
          <div className="flex items-center gap-1 min-w-0">
            <span className="font-semibold text-sm text-white truncate">{coin.name}</span>
            <span className="text-xs text-gray-400 uppercase flex-shrink-0">{coin.symbol}</span>
          </div>
          <div className="text-xs text-gray-400 mt-0.5">
            {showVolume
              ? `Vol: ${formatMarketCap(coin.total_volume, currency)}`
              : `Cap: ${formatMarketCap(coin.market_cap, currency)}`}
          </div>
        </div>

        <div className="text-right flex-shrink-0">
          <div className={`font-bold text-sm transition-colors duration-300 ${
            flash === 'up' ? 'text-accent-green' :
            flash === 'down' ? 'text-accent-red' :
            'text-white'
          }`}>
            {sym}{formatPrice(coin.current_price, currency)}
          </div>
          <div className={`text-xs font-medium mt-0.5 ${isPositive ? 'text-accent-green' : 'text-accent-red'}`}>
            {isPositive ? '▲' : '▼'} {Math.abs(displayChange).toFixed(2)}%
            {timeFrame !== '24h' && <span className="text-gray-600 ml-0.5">{timeFrame === '1h' ? '1h' : '7g'}</span>}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-1 flex-shrink-0 ml-1">
        <button
          onClick={() => { hapticMedium(); onToggleFavorite(coin.id); }}
          className={`text-lg leading-none transition-transform active:scale-75 ${isFavorite ? 'text-accent-yellow' : 'text-gray-600 hover:text-gray-400'}`}
          aria-label={isFavorite ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'}
        >
          ★
        </button>
        <button
          onClick={() => { hapticLight(); onAddAlert(coin); }}
          className="text-lg leading-none text-gray-600 hover:text-accent-blue transition-colors active:scale-75"
          aria-label="Imposta allarme"
        >
          🔔
        </button>
      </div>
    </div>
  );
};

export default CoinCard;
