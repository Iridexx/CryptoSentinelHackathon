import { useState, type FC } from 'react';
import type { PriceAlert, Coin, AlertDirection } from '../types';

interface Props {
  alerts: PriceAlert[];
  onRemove: (id: string) => void;
  onReset: (id: string) => void;
  coins: Coin[];
  onEdit: (id: string, threshold: number, direction: AlertDirection) => void;
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString('it-IT', { maximumFractionDigits: 0 });
  if (price >= 1) return price.toFixed(2);
  return price.toFixed(6);
}

const AlertsTab: FC<Props> = ({ alerts, onRemove, onReset, coins, onEdit }) => {
  if (alerts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center px-8">
        <div className="text-5xl mb-4">🔔</div>
        <h3 className="text-white font-semibold text-lg mb-2">Nessun allarme</h3>
        <p className="text-gray-500 text-sm">
          Premi il 🔔 accanto a una criptovaluta per impostare un allarme di prezzo.
        </p>
      </div>
    );
  }

  const active = alerts.filter((a) => !a.triggered);
  const triggered = alerts.filter((a) => a.triggered);

  return (
    <div className="space-y-2">
      {triggered.length > 0 && (
        <div>
          <h3 className="text-accent-yellow text-xs font-semibold uppercase tracking-wide px-1 mb-2">
            ✅ Scattati ({triggered.length})
          </h3>
          {triggered.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              onRemove={onRemove}
              onReset={onReset}
              onEdit={onEdit}
              coin={coins.find((c) => c.id === alert.coinId)}
            />
          ))}
        </div>
      )}

      {active.length > 0 && (
        <div>
          <h3 className="text-gray-400 text-xs font-semibold uppercase tracking-wide px-1 mb-2">
            Attivi ({active.length})
          </h3>
          {active.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              onRemove={onRemove}
              onReset={onReset}
              onEdit={onEdit}
              coin={coins.find((c) => c.id === alert.coinId)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

interface AlertRowProps {
  alert: PriceAlert;
  onRemove: (id: string) => void;
  onReset: (id: string) => void;
  onEdit: (id: string, threshold: number, direction: AlertDirection) => void;
  coin?: Coin;
}

const AlertRow: FC<AlertRowProps> = ({ alert, onRemove, onReset, onEdit, coin }) => {
  const [editing, setEditing] = useState(false);
  const [sliderValue, setSliderValue] = useState(50);
  const [draftThreshold, setDraftThreshold] = useState(alert.threshold);
  const [draftDirection, setDraftDirection] = useState<AlertDirection>(alert.direction);

  const isAbove = alert.direction === 'above';
  const sliderMin = alert.threshold * 0.5;
  const sliderMax = alert.threshold * 1.5;

  const handleOpenEdit = () => {
    setSliderValue(50);
    setDraftThreshold(alert.threshold);
    setDraftDirection(alert.direction);
    setEditing(true);
  };

  const handleSliderChange = (val: number) => {
    setSliderValue(val);
    const newThreshold = sliderMin + (val / 100) * (sliderMax - sliderMin);
    setDraftThreshold(newThreshold);
    if (coin) {
      setDraftDirection(newThreshold >= coin.current_price ? 'above' : 'below');
    }
  };

  const handleSave = () => {
    onEdit(alert.id, draftThreshold, draftDirection);
    setEditing(false);
  };

  const currentPricePercent = coin
    ? Math.max(0, Math.min(100, ((coin.current_price - sliderMin) / (sliderMax - sliderMin)) * 100))
    : null;

  const deviation = sliderValue - 50;
  const thumbColor = deviation === 0 ? '#6b7280' : deviation > 0 ? '#22c55e' : '#ef4444';

  return (
    <div className={`rounded-xl mb-2 border overflow-hidden transition-all ${
      alert.triggered ? 'bg-dark-700 border-accent-yellow/30' : 'bg-dark-800 border-dark-600'
    }`}>
      <div
        className="flex items-center gap-3 p-3 cursor-pointer select-none"
        onClick={() => !editing && handleOpenEdit()}
      >
        <img src={alert.coinImage} alt={alert.coinName} className="w-8 h-8 rounded-full flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1">
            <span className="text-white text-sm font-semibold">{alert.coinName}</span>
            {alert.triggered && (
              <span className="text-xs bg-accent-yellow/20 text-accent-yellow px-1.5 py-0.5 rounded-full">Scattato</span>
            )}
          </div>
          <div className={`text-xs mt-0.5 flex items-center gap-1.5 ${isAbove ? 'text-accent-green' : 'text-accent-red'}`}>
            {isAbove ? '▲ Sopra' : '▼ Sotto'} ${formatPrice(alert.threshold)}
            {alert.percentChange != null && (
              <span className={`px-1.5 py-0.5 rounded-full text-xs font-semibold ${isAbove ? 'bg-accent-green/10' : 'bg-accent-red/10'}`}>
                {isAbove ? '+' : '-'}{alert.percentChange.toFixed(1)}%
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
          {!editing && (
            <span className="text-gray-600 text-xs mr-1">✏️</span>
          )}
          {alert.triggered && (
            <button
              onClick={() => onReset(alert.id)}
              className="text-xs px-2 py-1 rounded-lg bg-dark-600 text-gray-300 hover:bg-dark-500 transition-colors"
              aria-label="Riattiva allarme"
            >
              ↺
            </button>
          )}
          <button
            onClick={() => onRemove(alert.id)}
            className="text-xs px-2 py-1 rounded-lg bg-accent-red/10 text-accent-red hover:bg-accent-red/20 transition-colors"
            aria-label="Elimina allarme"
          >
            ✕
          </button>
        </div>
      </div>

      {editing && (
        <div className="px-3 pb-3 border-t border-dark-600">
          <div className="flex items-center justify-between pt-2.5 pb-2">
            <div className="flex items-center gap-2">
              <span className={`text-sm font-bold tabular-nums ${draftDirection === 'above' ? 'text-accent-green' : 'text-accent-red'}`}>
                {draftDirection === 'above' ? '▲' : '▼'} ${formatPrice(draftThreshold)}
              </span>
              {coin && (() => {
                const pct = ((draftThreshold - coin.current_price) / coin.current_price) * 100;
                const sign = pct >= 0 ? '+' : '';
                return (
                  <span className={`text-xs font-semibold tabular-nums px-1.5 py-0.5 rounded-full ${pct >= 0 ? 'text-accent-green bg-accent-green/10' : 'text-accent-red bg-accent-red/10'}`}>
                    {sign}{pct.toFixed(2)}%
                  </span>
                );
              })()}
            </div>
            {coin && (
              <span className="text-xs text-gray-500">
                Ora: <span className="text-gray-300 font-medium">${formatPrice(coin.current_price)}</span>
              </span>
            )}
          </div>

          <div className="relative mb-1">
            <input
              type="range"
              min={0}
              max={100}
              step={0.1}
              value={sliderValue}
              onChange={(e) => handleSliderChange(parseFloat(e.target.value))}
              className="w-full h-1.5 rounded-full outline-none cursor-pointer appearance-none"
              style={{
                background: `linear-gradient(to right, ${thumbColor} 0%, ${thumbColor} ${sliderValue}%, #374151 ${sliderValue}%, #374151 100%)`,
                accentColor: thumbColor,
              }}
            />
            {currentPricePercent !== null && (
              <div
                className="absolute top-0 h-full w-px bg-accent-blue/70 rounded-full pointer-events-none"
                style={{ left: `${currentPricePercent}%`, transform: 'translateX(-50%)' }}
              />
            )}
          </div>

          <div className="flex justify-between text-xs text-gray-600 mb-3 mt-1">
            <span>${formatPrice(sliderMin)}</span>
            <span className="text-gray-700">−50% · +50%</span>
            <span>${formatPrice(sliderMax)}</span>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setEditing(false)}
              className="flex-1 py-2 bg-dark-700 text-gray-400 text-sm rounded-lg hover:bg-dark-600 transition-colors"
            >
              Annulla
            </button>
            <button
              onClick={handleSave}
              className="flex-1 py-2 bg-accent-blue text-white text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity"
            >
              Salva
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AlertsTab;
