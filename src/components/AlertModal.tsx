import { useState, type FC } from 'react';
import type { Coin, AlertDirection } from '../types';

interface Props {
  coin: Coin;
  onConfirm: (direction: AlertDirection, threshold: number) => void;
  onClose: () => void;
}

function formatPrice(price: number): string {
  if (price >= 1) return price.toFixed(2);
  return price.toFixed(6);
}

const AlertModal: FC<Props> = ({ coin, onConfirm, onClose }) => {
  const [direction, setDirection] = useState<AlertDirection>('above');
  const [value, setValue] = useState(formatPrice(coin.current_price));
  const [error, setError] = useState('');

  const handleSubmit = () => {
    const num = parseFloat(value.trim().replace(',', '.'));
    if (isNaN(num) || num <= 0) {
      setError('Inserisci un prezzo valido maggiore di zero');
      return;
    }
    onConfirm(direction, num);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-end sm:items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-dark-800 rounded-2xl w-full max-w-sm p-5 shadow-2xl border border-dark-600"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 mb-4">
          <img src={coin.image} alt={coin.name} className="w-10 h-10 rounded-full" />
          <div>
            <h2 className="text-white font-bold text-lg leading-tight">Imposta Allarme</h2>
            <p className="text-gray-400 text-sm">{coin.name} · Prezzo attuale: <span className="text-white">${formatPrice(coin.current_price)}</span></p>
          </div>
        </div>

        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setDirection('above')}
            className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-colors ${
              direction === 'above' ? 'bg-accent-green text-white' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}
          >
            ▲ Sopra
          </button>
          <button
            onClick={() => setDirection('below')}
            className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-colors ${
              direction === 'below' ? 'bg-accent-red text-white' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}
          >
            ▼ Sotto
          </button>
        </div>

        <div className="mb-2">
          <label className="text-gray-400 text-xs mb-1 block">Prezzo soglia (USD)</label>
          <div className="flex items-center bg-dark-700 rounded-lg px-3 border border-dark-600 focus-within:border-accent-blue">
            <span className="text-gray-500 mr-1">$</span>
            <input
              type="number"
              value={value}
              onChange={(e) => { setValue(e.target.value); setError(''); }}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              className="flex-1 bg-transparent text-white py-2.5 outline-none text-sm"
              placeholder="0.00"
              step="any"
              min="0"
              autoFocus
            />
          </div>
          {error && <p className="text-accent-red text-xs mt-1">{error}</p>}
        </div>

        <p className="text-gray-500 text-xs mb-4">
          Riceverai una notifica quando {coin.name} andrà{' '}
          <span className={direction === 'above' ? 'text-accent-green' : 'text-accent-red'}>
            {direction === 'above' ? 'sopra' : 'sotto'}
          </span>{' '}
          ${value || '…'}
        </p>

        <div className="flex gap-2">
          <button onClick={onClose} className="flex-1 py-2.5 rounded-lg bg-dark-700 text-gray-300 hover:bg-dark-600 text-sm font-medium transition-colors">
            Annulla
          </button>
          <button onClick={handleSubmit} className="flex-1 py-2.5 rounded-lg bg-accent-blue text-white hover:opacity-90 text-sm font-semibold transition-opacity">
            Crea Allarme
          </button>
        </div>
      </div>
    </div>
  );
};

export default AlertModal;
