import { useRef, type FC } from 'react';
import type { FavAlertData } from '../hooks/useFavoritePriceAlerts';
import type { Currency } from '../hooks/useCurrency';

interface Props {
  alert: FavAlertData;
  currency: Currency;
  onClose: () => void;
  onDismiss: () => void;
}

const SYMBOL: Record<Currency, string> = { usd: '$', eur: '€', btc: '₿' };

function fmt(v: number, currency: Currency): string {
  if (currency === 'btc') return v.toFixed(8);
  if (v >= 1000) return v.toLocaleString('it-IT', { maximumFractionDigits: 0 });
  if (v >= 1) return v.toFixed(2);
  return v.toFixed(6);
}

const FavMovePopup: FC<Props> = ({ alert, currency, onClose, onDismiss }) => {
  const touchStartY = useRef(0);
  const sym = SYMBOL[currency];
  const isUp = alert.direction === 'up';

  return (
    <div
      className="fixed inset-0 bg-black/70 z-50 flex flex-col justify-end"
      onClick={onClose}
    >
      <div
        className="bg-dark-800 rounded-t-3xl border-t border-dark-600 max-h-[92vh] flex flex-col"
        onClick={e => e.stopPropagation()}
        onTouchStart={e => { touchStartY.current = e.touches[0].clientY; }}
        onTouchEnd={e => {
          const deltaY = e.changedTouches[0].clientY - touchStartY.current;
          if (deltaY > 80) onClose();
        }}
      >
        {/* Handle */}
        <div className="flex justify-center pt-3 pb-1 flex-shrink-0">
          <div className="w-9 h-1 bg-dark-600 rounded-full" />
        </div>

        {/* Contenuto */}
        <div className="overflow-y-auto flex-1 px-5 pb-8">

          <div className="flex items-center justify-between py-4">
            <div className="flex items-center gap-2">
              <span className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${
                isUp ? 'bg-accent-green/20' : 'bg-red-500/20'
              }`}>
                <svg className={`w-5 h-5 ${isUp ? 'text-accent-green' : 'text-red-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {isUp
                    ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                    : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                  }
                </svg>
              </span>
              <h2 className="text-white font-bold text-lg">Movimento rilevato</h2>
            </div>
            <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-2xl leading-none w-8 h-8 flex items-center justify-center">×</button>
          </div>

          <div className="bg-dark-700 rounded-xl px-4 py-4 mb-4">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs text-gray-500">{alert.coinSymbol.toUpperCase()}</p>
              <span className={`flex-shrink-0 text-xs font-semibold px-2.5 py-1 rounded-full ${
                isUp ? 'text-accent-green bg-accent-green/10' : 'text-red-400 bg-red-500/10'
              }`}>
                {isUp ? 'Rialzo' : 'Ribasso'}
              </span>
            </div>
            <p className="text-white font-bold text-xl leading-snug mt-1">{alert.coinName}</p>
            <p className={`text-sm mt-1.5 font-semibold ${isUp ? 'text-accent-green' : 'text-red-400'}`}>
              {isUp ? '+' : ''}{alert.pct.toFixed(2)}% dal riferimento
            </p>
          </div>

          <div className="flex gap-3 mb-6">
            <div className="flex-1 bg-dark-700 rounded-xl px-4 py-3">
              <p className="text-xs text-gray-500 mb-1">Prezzo attuale</p>
              <p className="text-sm font-semibold text-white">{sym}{fmt(alert.currentPrice, currency)}</p>
            </div>
            <div className="flex-1 bg-dark-700 rounded-xl px-4 py-3">
              <p className="text-xs text-gray-500 mb-1">Riferimento</p>
              <p className="text-sm font-semibold text-gray-300">{sym}{fmt(alert.refPrice, currency)}</p>
            </div>
          </div>

          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="flex-1 py-3 rounded-xl text-sm text-gray-400 font-medium transition-colors bg-dark-700"
            >
              Chiudi
            </button>
            <button
              onClick={onDismiss}
              className={`flex-1 py-3 text-white text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity ${
                isUp ? 'bg-accent-green' : 'bg-red-500'
              }`}
            >
              Ho capito
            </button>
          </div>

        </div>
      </div>
    </div>
  );
};

export default FavMovePopup;
