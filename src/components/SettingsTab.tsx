import { useState, type FC } from 'react';
import { getNotificationPermission, openNotificationSettings } from '../utils/notifications';
import { checkForUpdates, downloadAndInstall, APK_PAGES_URL, type UpdateResult } from '../utils/update';

const INTERVALS = [
  { label: '30 sec', ms: 30_000 },
  { label: '1 min', ms: 60_000 },
  { label: '5 min', ms: 300_000 },
];

type UpdateState = 'idle' | 'checking' | 'up-to-date' | 'available' | 'error';

interface Props {
  refreshInterval: number;
  onIntervalChange: (ms: number) => void;
  favoritesCount: number;
  alertsCount: number;
  onClearFavorites: () => void;
  onClearAlerts: () => void;
}

const SettingsTab: FC<Props> = ({
  refreshInterval,
  onIntervalChange,
  favoritesCount,
  alertsCount,
  onClearFavorites,
  onClearAlerts,
}) => {
  const notifPerm = getNotificationPermission();
  const [updateState, setUpdateState] = useState<UpdateState>('idle');
  const [updateInfo, setUpdateInfo] = useState<UpdateResult | null>(null);

  const handleCheckUpdate = async () => {
    setUpdateState('checking');
    try {
      const result = await checkForUpdates(__APP_BUILD_DATE__);
      setUpdateInfo(result);
      setUpdateState(result.available ? 'available' : 'up-to-date');
    } catch {
      setUpdateState('error');
    }
  };

  const handleClearFavorites = () => {
    if (favoritesCount === 0) return;
    if (confirm(`Rimuovere tutti i ${favoritesCount} preferiti?`)) onClearFavorites();
  };

  const handleClearAlerts = () => {
    if (alertsCount === 0) return;
    if (confirm(`Eliminare tutti i ${alertsCount} allarmi?`)) onClearAlerts();
  };

  return (
    <div className="space-y-5">

      {/* Aggiornamento app */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Aggiornamento app</h2>
        <div className="bg-dark-800 rounded-xl px-4 py-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-white font-medium">CryptoWatch</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Build: {new Date(__APP_BUILD_DATE__).toLocaleDateString('it-IT', {
                  day: '2-digit', month: '2-digit', year: 'numeric',
                })}
              </p>
            </div>
            {updateState === 'up-to-date' && (
              <span className="text-xs font-semibold text-accent-green bg-accent-green/10 px-2.5 py-1 rounded-full">
                Aggiornata
              </span>
            )}
            {updateState === 'available' && (
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-accent-blue bg-accent-blue/10 px-2.5 py-1 rounded-full">
                  Disponibile
                </span>
                <button
                  onClick={handleCheckUpdate}
                  title="Ricontrolla"
                  className="text-gray-500 hover:text-gray-300 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                </button>
              </div>
            )}
          </div>

          {updateState === 'available' && updateInfo && (
            <div className="bg-accent-blue/10 border border-accent-blue/20 rounded-lg px-3 py-2 flex items-center justify-between">
              <p className="text-xs text-gray-300">
                Aggiornamento del <span className="text-white font-medium">{updateInfo.releaseDate}</span>
              </p>
              {updateInfo.buildNumber && (
                <span className="text-xs text-gray-400 font-mono ml-2">#{updateInfo.buildNumber}</span>
              )}
            </div>
          )}

          {updateState === 'error' && (
            <p className="text-xs text-accent-red">Impossibile verificare. Controlla la connessione.</p>
          )}

          {updateState === 'available' ? (
            <button
              onClick={() => downloadAndInstall(APK_PAGES_URL)}
              className="w-full py-2.5 bg-accent-blue text-white text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity"
            >
              Scarica e installa
            </button>
          ) : (
            <button
              onClick={handleCheckUpdate}
              disabled={updateState === 'checking'}
              className="w-full py-2.5 bg-dark-700 text-gray-300 text-sm font-medium rounded-lg hover:bg-dark-600 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {updateState === 'checking' ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Verifica in corso…
                </>
              ) : (
                'Controlla aggiornamenti'
              )}
            </button>
          )}
        </div>
      </section>

      {/* Notifiche */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Notifiche</h2>
        <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
          <div className="px-4 py-3 flex items-center justify-between">
            <div>
              <p className="text-sm text-white">Stato permesso</p>
              <p className="text-xs text-gray-500 mt-0.5">
                {notifPerm === 'granted' ? 'Notifiche attive' : 'Notifiche bloccate'}
              </p>
            </div>
            {notifPerm === 'granted' ? (
              <span className="text-xs font-semibold text-accent-green bg-accent-green/10 px-2.5 py-1 rounded-full">Attive</span>
            ) : (
              <span className="text-xs font-semibold text-accent-red bg-accent-red/10 px-2.5 py-1 rounded-full">Bloccate</span>
            )}
          </div>
          {notifPerm !== 'granted' && (
            <button
              onClick={openNotificationSettings}
              className="w-full px-4 py-3 flex items-center justify-between text-accent-blue hover:bg-dark-700 transition-colors rounded-b-xl"
            >
              <span className="text-sm">Apri impostazioni telefono</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          )}
        </div>
      </section>

      {/* Aggiornamento prezzi */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Aggiornamento prezzi</h2>
        <div className="bg-dark-800 rounded-xl px-4 py-3">
          <p className="text-sm text-white mb-3">Intervallo di aggiornamento</p>
          <div className="flex gap-2">
            {INTERVALS.map(({ label, ms }) => (
              <button
                key={ms}
                onClick={() => onIntervalChange(ms)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                  refreshInterval === ms
                    ? 'bg-accent-blue text-white'
                    : 'bg-dark-700 text-gray-400 hover:text-white'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Cancella dati */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Dati</h2>
        <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
          <button
            onClick={handleClearFavorites}
            disabled={favoritesCount === 0}
            className="w-full px-4 py-3 flex items-center justify-between disabled:opacity-40 hover:bg-dark-700 transition-colors rounded-t-xl"
          >
            <div className="text-left">
              <p className="text-sm text-white">Cancella preferiti</p>
              <p className="text-xs text-gray-500 mt-0.5">{favoritesCount} salvati</p>
            </div>
            <span className="text-accent-red text-sm font-medium">Cancella</span>
          </button>
          <button
            onClick={handleClearAlerts}
            disabled={alertsCount === 0}
            className="w-full px-4 py-3 flex items-center justify-between disabled:opacity-40 hover:bg-dark-700 transition-colors rounded-b-xl"
          >
            <div className="text-left">
              <p className="text-sm text-white">Cancella allarmi</p>
              <p className="text-xs text-gray-500 mt-0.5">{alertsCount} impostati</p>
            </div>
            <span className="text-accent-red text-sm font-medium">Cancella</span>
          </button>
        </div>
      </section>

      {/* Informazioni */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Informazioni</h2>
        <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-gray-400">Applicazione</span>
            <span className="text-sm text-white font-medium">CryptoWatch</span>
          </div>
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-gray-400">Sviluppatore</span>
            <span className="text-sm text-white font-medium">Iridexx</span>
          </div>
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-gray-400">Fonte dati</span>
            <span className="text-sm text-white font-medium">CoinGecko API</span>
          </div>
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-gray-400">Dati personali</span>
            <span className="text-sm text-accent-green font-medium">Nessuno raccolto</span>
          </div>
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-gray-400">Archiviazione</span>
            <span className="text-sm text-white font-medium">Solo locale</span>
          </div>
        </div>
      </section>

      <p className="text-center text-xs text-gray-600 pb-2">
        I dati di mercato sono forniti da CoinGecko API (gratuita).
      </p>

    </div>
  );
};

export default SettingsTab;
