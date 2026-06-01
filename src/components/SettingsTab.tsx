import { useState, type FC } from 'react';
import { Capacitor } from '@capacitor/core';
import { openNotificationSettings } from '../utils/notifications';
import { openBatterySettings } from '../utils/energySaving';
import { checkForUpdates, downloadAndInstall, openDownloadsFolder, getDevBuildInfo, mergeToMain, APK_PAGES_URL, type UpdateResult, type DevBuildInfo } from '../utils/update';
import type { Currency } from '../hooks/useCurrency';

const DONATION_OPTIONS = [
  {
    icon: '⚡',
    label: 'Lightning Network',
    subtitle: 'Bitcoin istantaneo · zero commissioni',
    address: 'eifel@getalby.com',
    appUri: 'lightning:eifel@getalby.com',
  },
  {
    icon: '₿',
    label: 'Bitcoin',
    subtitle: 'On-chain · Taproot',
    address: 'bc1pfzyjm5759qv0rjfsxld4jcejqv7elkuw6j9w2dxcsyrdf4vsw6yq6lexdg',
    appUri: 'bitcoin:bc1pfzyjm5759qv0rjfsxld4jcejqv7elkuw6j9w2dxcsyrdf4vsw6yq6lexdg',
  },
  {
    icon: '💎',
    label: 'USDT / USDC',
    subtitle: 'EVM · Ethereum, Polygon, BSC, Arbitrum…',
    address: '0x80f8Fc375bCf1a7BC38394d6048e8364628Bd6C0',
    appUri: 'ethereum:0x80f8Fc375bCf1a7BC38394d6048e8364628Bd6C0',
  },
] as const;

const DonationRow: FC<{ icon: string; label: string; subtitle: string; address: string; appUri?: string | null; last?: boolean }> = ({
  icon, label, subtitle, address, appUri, last,
}) => {
  const [copied, setCopied] = useState(false);

  const truncated = address.length > 20
    ? `${address.slice(0, 10)}…${address.slice(-6)}`
    : address;

  const handleOpen = () => {
    if (appUri) window.open(appUri, '_system');
  };

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(address);
    } catch {
      const el = document.createElement('textarea');
      el.value = address;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={`px-4 py-3 flex items-center gap-3 transition-colors ${last ? 'rounded-b-xl' : ''} ${appUri ? 'cursor-pointer hover:bg-dark-700 active:bg-dark-600' : ''}`}
      onClick={appUri ? handleOpen : undefined}
    >
      <span className="text-xl w-7 text-center flex-shrink-0">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-white font-medium">{label}</p>
        <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>
        <p className="text-xs text-gray-600 font-mono mt-0.5 truncate">{truncated}</p>
      </div>
      <button
        onClick={handleCopy}
        className={`flex-shrink-0 text-xs px-3 py-1.5 rounded-lg font-semibold transition-all ${
          copied ? 'bg-accent-green/20 text-accent-green' : 'bg-dark-700 text-gray-400 hover:text-white'
        }`}
      >
        {copied ? '✓' : 'Copia'}
      </button>
    </div>
  );
};

const INTERVALS = [
  { label: '30 sec', ms: 30_000 },
  { label: '1 min', ms: 60_000 },
  { label: '5 min', ms: 300_000 },
];

const DEV_PIN = '6878';

type UpdateState = 'idle' | 'checking' | 'up-to-date' | 'available' | 'error';
type DevState = 'locked' | 'pin-entry' | 'unlocked';
type DevLoadState = 'idle' | 'loading' | 'loaded' | 'error';

interface Props {
  refreshInterval: number;
  onIntervalChange: (ms: number) => void;
  favoritesCount: number;
  alertsCount: number;
  onClearFavorites: () => void;
  onClearAlerts: () => void;
  notifPerm: NotificationPermission;
  onPermissionChange: (p: NotificationPermission) => void;
  batteryDismissed: boolean;
  dlState: 'idle' | 'downloading' | 'done';
  onDownloadStart: () => void;
  onDownloadDone: () => void;
  currency: Currency;
  onCurrencyChange: (c: Currency) => void;
  sliderRange: number;
  onSliderRangeChange: (n: number) => void;
}

const SettingsTab: FC<Props> = ({
  refreshInterval,
  onIntervalChange,
  favoritesCount,
  alertsCount,
  onClearFavorites,
  onClearAlerts,
  notifPerm,
  batteryDismissed,
  dlState,
  onDownloadStart,
  onDownloadDone,
  currency,
  onCurrencyChange,
  sliderRange,
  onSliderRangeChange,
}) => {
  const [updateState, setUpdateState] = useState<UpdateState>('idle');
  const [updateInfo, setUpdateInfo] = useState<UpdateResult | null>(null);
  const [devState, setDevState] = useState<DevState>('locked');
  const [pinInput, setPinInput] = useState('');
  const [pinError, setPinError] = useState(false);
  const [devLoadState, setDevLoadState] = useState<DevLoadState>('idle');
  const [devBuildInfo, setDevBuildInfo] = useState<DevBuildInfo | null>(null);
  const [ghToken, setGhToken] = useState(() => localStorage.getItem('cryptosentinel_dev_token') ?? '');
  const [showToken, setShowToken] = useState(false);
  const [mergeState, setMergeState] = useState<'idle' | 'merging' | 'done' | 'error'>('idle');
  const [mergeError, setMergeError] = useState('');

  const handleCheckUpdate = async () => {
    setUpdateState('checking');
    try {
      const result = await checkForUpdates(__APP_BUILD_NUMBER__);
      setUpdateInfo(result);
      setUpdateState(result.available ? 'available' : 'up-to-date');
    } catch {
      setUpdateState('error');
    }
  };

  const handlePinSubmit = () => {
    if (pinInput === DEV_PIN) {
      setDevState('unlocked');
      setPinError(false);
      setPinInput('');
    } else {
      setPinError(true);
      setPinInput('');
    }
  };

  const handleSaveToken = (val: string) => {
    setGhToken(val);
    localStorage.setItem('cryptosentinel_dev_token', val);
  };

  const handleMerge = async () => {
    if (!devBuildInfo?.branch || !ghToken) return;
    setMergeState('merging');
    setMergeError('');
    try {
      await mergeToMain(devBuildInfo.branch, ghToken);
      setMergeState('done');
    } catch (e) {
      setMergeError((e as Error).message);
      setMergeState('error');
    }
  };

  const handleLoadDevBuild = async () => {
    setDevLoadState('loading');
    try {
      const info = await getDevBuildInfo();
      setDevBuildInfo(info);
      setDevLoadState('loaded');
    } catch {
      setDevLoadState('error');
    }
  };

  const handleDownload = async (url: string) => {
    onDownloadStart();
    await downloadAndInstall(url);
    onDownloadDone();
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
              <p className="text-sm text-white font-medium">CryptoSentinel</p>
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
              onClick={() => handleDownload(APK_PAGES_URL)}
              disabled={dlState === 'downloading'}
              className="w-full py-2.5 bg-accent-blue text-white text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity disabled:opacity-60"
            >
              {dlState === 'downloading' ? 'Download in corso…' : 'Scarica e installa'}
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

          {updateState === 'available' && dlState !== 'idle' && (
            <div className={`rounded-lg px-3 py-2.5 flex items-center justify-between gap-3 ${
              dlState === 'done'
                ? 'bg-accent-green/10 border border-accent-green/20'
                : 'bg-accent-blue/10 border border-accent-blue/20'
            }`}>
              <div className="flex items-center gap-2">
                {dlState === 'downloading' ? (
                  <svg className="w-4 h-4 text-accent-blue animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                ) : (
                  <span className="text-accent-green text-sm">✓</span>
                )}
                <p className="text-xs text-gray-300">
                  {dlState === 'downloading' ? 'Download in corso…' : 'Download completato'}
                </p>
              </div>
              <button
                onClick={openDownloadsFolder}
                className="text-xs text-accent-blue underline underline-offset-2 whitespace-nowrap"
              >
                📁 Apri Download
              </button>
            </div>
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
          <button
            onClick={openNotificationSettings}
            className="w-full px-4 py-3 flex items-center justify-between text-accent-blue hover:bg-dark-700 transition-colors rounded-b-xl"
          >
            <span className="text-sm">Apri impostazioni notifiche</span>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </section>

      {/* Risparmio energetico */}
      {Capacitor.isNativePlatform() && (
        <section>
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Risparmio energetico</h2>
          <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
            <div className="px-4 py-3 flex items-center justify-between">
              <div>
                <p className="text-sm text-white">Ottimizzazione batteria</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {batteryDismissed ? 'Impostazione verificata' : 'Potrebbe bloccare gli aggiornamenti'}
                </p>
              </div>
              {batteryDismissed ? (
                <span className="text-xs font-semibold text-accent-green bg-accent-green/10 px-2.5 py-1 rounded-full">OK</span>
              ) : (
                <span className="text-xs font-semibold text-accent-yellow bg-accent-yellow/10 px-2.5 py-1 rounded-full">Attenzione</span>
              )}
            </div>
            <button
              onClick={openBatterySettings}
              className="w-full px-4 py-3 flex items-center justify-between text-accent-yellow hover:bg-dark-700 transition-colors rounded-b-xl"
            >
              <span className="text-sm">Apri impostazioni batteria</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </section>
      )}

      {/* Personalizzazione */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Personalizzazione</h2>
        <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
          <div className="px-4 py-3">
            <p className="text-sm text-white mb-1">Valuta di visualizzazione</p>
            <p className="text-xs text-gray-500 mb-3">Cambia la valuta con cui vengono mostrati prezzi e capitalizzazione</p>
            <div className="flex gap-2">
              {([['usd', '$ USD'], ['eur', '€ EUR'], ['btc', '₿ BTC']] as const).map(([c, label]) => (
                <button
                  key={c}
                  onClick={() => onCurrencyChange(c)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    currency === c ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="px-4 py-3">
            <p className="text-sm text-white mb-1">Range slider allarmi</p>
            <p className="text-xs text-gray-500 mb-3">Variazione massima gestibile dallo slider nella modifica di un allarme</p>
            <div className="flex gap-2">
              {([5, 10, 20, 30, 50] as const).map((pct) => (
                <button
                  key={pct}
                  onClick={() => onSliderRangeChange(pct)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    sliderRange === pct ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
                  }`}
                >
                  ±{pct}%
                </button>
              ))}
            </div>
          </div>
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
            <span className="text-sm text-white font-medium">CryptoSentinel</span>
          </div>
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-gray-400">Versione</span>
            <span className="text-sm text-white font-medium font-mono">
              v1.0.{__APP_BUILD_NUMBER__}
            </span>
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
          <a
            href="https://www.gnu.org/licenses/gpl-3.0.html"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-3 flex items-center justify-between hover:bg-dark-700 transition-colors rounded-b-xl"
          >
            <span className="text-sm text-gray-400">Licenza</span>
            <div className="flex items-center gap-1.5">
              <span className="text-sm text-white font-medium">GPL v3</span>
              <svg className="w-3.5 h-3.5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </div>
          </a>
        </div>
      </section>

      {/* Social */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Sviluppatore</h2>
        <a
          href="https://x.com/eifel3btc"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 bg-dark-800 rounded-xl px-4 py-3 hover:bg-dark-700 active:bg-dark-600 transition-colors group"
        >
          <div className="w-9 h-9 bg-white rounded-lg flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="black">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.748l7.73-8.835L1.254 2.25H8.08l4.253 5.622 5.91-5.622Zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-white font-semibold">Seguimi su X</p>
            <p className="text-xs text-gray-500 mt-0.5">@eifel3btc</p>
          </div>
          <svg className="w-4 h-4 text-gray-600 group-hover:text-gray-400 transition-colors flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </a>
      </section>

      {/* Donazioni */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Supporta lo sviluppatore</h2>
        <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
          <a
            href="https://buymeacoffee.com/eifel3btc"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-3 flex items-center gap-3 hover:bg-dark-700 transition-colors rounded-t-xl group"
          >
            <span className="text-xl w-7 text-center flex-shrink-0">☕</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-white font-medium">Buy Me a Coffee</p>
              <p className="text-xs text-gray-500 mt-0.5">Carta di credito · PayPal</p>
            </div>
            <svg className="w-4 h-4 text-gray-600 group-hover:text-gray-400 transition-colors flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
          {DONATION_OPTIONS.map((opt, i) => (
            <DonationRow
              key={opt.address}
              {...opt}
              last={i === DONATION_OPTIONS.length - 1}
            />
          ))}
        </div>
      </section>

      <p className="text-center text-xs text-gray-600 pb-2">
        I dati di mercato sono forniti da CoinGecko API (gratuita).
      </p>

      {/* Modalità Sviluppatore */}
      <section>
        {devState === 'locked' && (
          <button
            onClick={() => { setDevState('pin-entry'); setPinError(false); setPinInput(''); }}
            className="w-full text-center text-xs text-gray-700 hover:text-gray-500 transition-colors py-2"
          >
            🔒 Modalità Sviluppatore
          </button>
        )}

        {devState === 'pin-entry' && (
          <div className="bg-dark-800 rounded-xl px-4 py-4">
            <p className="text-sm text-white font-medium text-center mb-3">Inserisci PIN</p>
            <input
              type="password"
              inputMode="numeric"
              maxLength={4}
              value={pinInput}
              onChange={(e) => { setPinInput(e.target.value.replace(/\D/g, '')); setPinError(false); }}
              onKeyDown={(e) => e.key === 'Enter' && handlePinSubmit()}
              placeholder="• • • •"
              className={`w-full bg-dark-700 border rounded-lg px-4 py-2.5 text-center text-white text-xl tracking-widest outline-none transition-colors mb-3 ${
                pinError ? 'border-accent-red' : 'border-dark-600 focus:border-accent-blue'
              }`}
              autoFocus
            />
            {pinError && <p className="text-xs text-accent-red text-center mb-3">PIN errato</p>}
            <div className="flex gap-2">
              <button onClick={() => setDevState('locked')} className="flex-1 py-2 bg-dark-700 text-gray-400 text-sm rounded-lg">Annulla</button>
              <button onClick={handlePinSubmit} disabled={pinInput.length !== 4} className="flex-1 py-2 bg-accent-blue text-white text-sm font-semibold rounded-lg disabled:opacity-40">Sblocca</button>
            </div>
          </div>
        )}

        {devState === 'unlocked' && (
          <div className="bg-dark-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-accent-blue/10 border-b border-dark-700 flex items-center justify-between">
              <span className="text-sm font-semibold text-accent-blue">⚙️ Modalità Sviluppatore</span>
              <button onClick={() => setDevState('locked')} className="text-gray-500 text-lg">×</button>
            </div>
            <div className="px-4 py-4 space-y-3">
              {devLoadState === 'idle' && (
                <button onClick={handleLoadDevBuild} className="w-full py-2.5 bg-dark-700 text-gray-300 text-sm rounded-lg hover:bg-dark-600 transition-colors">Controlla ultima dev build</button>
              )}
              {devLoadState === 'loading' && (
                <div className="flex items-center justify-center gap-2 py-2 text-gray-400 text-sm">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Caricamento…
                </div>
              )}
              {devLoadState === 'error' && (
                <p className="text-xs text-accent-red text-center">Errore nel caricamento. Nessuna dev build disponibile.</p>
              )}
              {devLoadState === 'loaded' && devBuildInfo && (
                <>
                  <div className="bg-dark-700 rounded-lg divide-y divide-dark-600">
                    <div className="px-3 py-2 flex justify-between"><span className="text-xs text-gray-500">Build</span><span className="text-xs text-white font-mono">#{devBuildInfo.buildNumber ?? '—'}</span></div>
                    <div className="px-3 py-2 flex justify-between"><span className="text-xs text-gray-500">Branch</span><span className="text-xs text-accent-blue font-mono truncate max-w-[60%] text-right">{devBuildInfo.branch ?? '—'}</span></div>
                    <div className="px-3 py-2 flex justify-between"><span className="text-xs text-gray-500">Data</span><span className="text-xs text-white">{devBuildInfo.buildDate}</span></div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={handleLoadDevBuild} className="p-2.5 bg-dark-700 text-gray-400 rounded-lg hover:text-white transition-colors" title="Aggiorna">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                    </button>
                    {devBuildInfo.downloadUrl && (
                      <button onClick={() => handleDownload(devBuildInfo.downloadUrl!)} disabled={dlState === 'downloading'} className="flex-1 py-2.5 bg-accent-blue text-white text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity disabled:opacity-60">
                        {dlState === 'downloading' ? 'Download in corso…' : `Scarica build #${devBuildInfo.buildNumber}`}
                      </button>
                    )}
                  </div>
                  {dlState !== 'idle' && (
                    <div className={`rounded-lg px-3 py-2.5 flex items-center justify-between gap-3 ${dlState === 'done' ? 'bg-accent-green/10 border border-accent-green/20' : 'bg-accent-blue/10 border border-accent-blue/20'}`}>
                      <div className="flex items-center gap-2 min-w-0">
                        {dlState === 'downloading' ? (<svg className="w-4 h-4 text-accent-blue flex-shrink-0 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>) : (<span className="text-accent-green text-sm flex-shrink-0">✓</span>)}
                        <p className="text-xs text-gray-300 truncate">{dlState === 'downloading' ? 'Download in corso…' : 'Download completato'}</p>
                      </div>
                      <button onClick={openDownloadsFolder} className="flex-shrink-0 text-xs text-accent-blue underline underline-offset-2 whitespace-nowrap">📁 Apri Download</button>
                    </div>
                  )}
                  <div className="border-t border-dark-600 pt-3 space-y-2">
                    <p className="text-xs text-gray-500">GitHub Token (PAT con scope repo)</p>
                    <div className="flex gap-2">
                      <input type={showToken ? 'text' : 'password'} value={ghToken} onChange={(e) => handleSaveToken(e.target.value)} placeholder="ghp_xxxxxxxxxxxx" className="flex-1 bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-accent-blue font-mono" />
                      <button onClick={() => setShowToken(v => !v)} className="px-2.5 bg-dark-700 text-gray-400 rounded-lg text-xs">{showToken ? 'Nascondi' : 'Mostra'}</button>
                    </div>
                    {mergeState === 'done' ? (
                      <div className="py-2.5 bg-accent-green/10 border border-accent-green/20 rounded-lg text-center text-xs text-accent-green font-semibold">✓ Merge completato su main</div>
                    ) : (
                      <button onClick={handleMerge} disabled={!ghToken || !devBuildInfo.branch || mergeState === 'merging'} className="w-full py-2.5 bg-accent-green/20 text-accent-green text-sm font-semibold rounded-lg hover:bg-accent-green/30 transition-colors disabled:opacity-40 flex items-center justify-center gap-2">
                        {mergeState === 'merging' ? (<><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>Merge in corso…</>) : ('Valida e merga in main')}
                      </button>
                    )}
                    {mergeState === 'error' && <p className="text-xs text-accent-red">{mergeError}</p>}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </section>

    </div>
  );
};

export default SettingsTab;
