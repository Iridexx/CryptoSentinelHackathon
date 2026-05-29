import type { FC } from 'react';
import type { PriceAlert } from '../types';

interface Props {
  alerts: PriceAlert[];
  onRemove: (id: string) => void;
  onReset: (id: string) => void;
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString('it-IT', { maximumFractionDigits: 0 });
  if (price >= 1) return price.toFixed(2);
  return price.toFixed(6);
}

const AlertsTab: FC<Props> = ({ alerts, onRemove, onReset }) => {
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
            <AlertRow key={alert.id} alert={alert} onRemove={onRemove} onReset={onReset} />
          ))}
        </div>
      )}

      {active.length > 0 && (
        <div>
          <h3 className="text-gray-400 text-xs font-semibold uppercase tracking-wide px-1 mb-2">
            Attivi ({active.length})
          </h3>
          {active.map((alert) => (
            <AlertRow key={alert.id} alert={alert} onRemove={onRemove} onReset={onReset} />
          ))}
        </div>
      )}
    </div>
  );
};

const AlertRow: FC<{ alert: PriceAlert; onRemove: (id: string) => void; onReset: (id: string) => void }> = ({
  alert, onRemove, onReset,
}) => {
  const isAbove = alert.direction === 'above';
  return (
    <div className={`flex items-center gap-3 rounded-xl p-3 mb-2 border ${
      alert.triggered ? 'bg-dark-700 border-accent-yellow/30' : 'bg-dark-800 border-dark-600'
    }`}>
      <img src={alert.coinImage} alt={alert.coinName} className="w-8 h-8 rounded-full flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1">
          <span className="text-white text-sm font-semibold">{alert.coinName}</span>
          {alert.triggered && <span className="text-xs bg-accent-yellow/20 text-accent-yellow px-1.5 py-0.5 rounded-full">Scattato</span>}
        </div>
        <div className={`text-xs mt-0.5 ${isAbove ? 'text-accent-green' : 'text-accent-red'}`}>
          {isAbove ? '▲ Sopra' : '▼ Sotto'} ${formatPrice(alert.threshold)}
        </div>
      </div>
      <div className="flex gap-1 flex-shrink-0">
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
  );
};

export default AlertsTab;
