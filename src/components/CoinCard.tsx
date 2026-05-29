import type { FC } from 'react';
import type { Coin } from '../types';

interface Props {
  coin: Coin;
  isFavorite: boolean;
  onToggleFavorite: (id: string) => void;
  onAddAlert: (coin: Coin) => void;
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString('it-IT', { maximumFractionDigits: 0 });
  if (price >= 1) return price.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return price.toLocaleString('it-IT', { minimumFractionDigits: 4, maximumFractionDigits: 6 });
}

function formatMarketCap(val: number): string {
  if (val >= 1e12) return `$${(val / 1e12).toFixed(2)}T`;
  if (val >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
  return `$${val.toLocaleString('it-IT')}`;
}

const CoinCard: FC<Props> = ({ coin, isFavorite, onToggleFavorite, onAddAlert }) => {
  const isPositive = coin.price_change_percentage_24h >= 0;

  return (
    <div className="flex items-center gap-3 bg-dark-800 rounded-xl p-3 hover:bg-dark-700 transition-colors">
      <img src={coin.image} alt={coin.name} className="w-9 h-9 rounded-full flex-shrink-0" loading="lazy" />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1">
          <span className="font-semibold text-sm text-white truncate">{coin.name}</span>
          <span className="text-xs text-gray-500 uppercase flex-shrink-0">{coin.symbol}</span>
        </div>
        <div className="text-xs text-gray-500 mt-0.5">
          Cap: {formatMarketCap(coin.market_cap)}
        </div>
      </div>

      <div className="text-right flex-shrink-0">
        <div className="font-bold text-sm text-white">${formatPrice(coin.current_price)}</div>
        <div className={`text-xs font-medium mt-0.5 ${isPositive ? 'text-accent-green' : 'text-accent-red'}`}>
          {isPositive ? '▲' : '▼'} {Math.abs(coin.price_change_percentage_24h).toFixed(2)}%
        </div>
      </div>

      <div className="flex flex-col gap-1 flex-shrink-0 ml-1">
        <button
          onClick={() => onToggleFavorite(coin.id)}
          className={`text-lg leading-none transition-transform active:scale-75 ${isFavorite ? 'text-accent-yellow' : 'text-gray-600 hover:text-gray-400'}`}
          aria-label={isFavorite ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'}
        >
          ★
        </button>
        <button
          onClick={() => onAddAlert(coin)}
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
