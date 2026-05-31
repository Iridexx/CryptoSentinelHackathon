import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import type { Coin } from './types';
import { useCryptoData } from './hooks/useCryptoData';
import { useFavorites } from './hooks/useFavorites';
import { useAlerts } from './hooks/useAlerts';
import { useCurrency } from './hooks/useCurrency';
import { getNotificationPermission, initNotifications } from './utils/notifications';
import { isBatteryBannerDismissed } from './utils/energySaving';
import { onDownloadComplete, triggerImmediateCheck, checkForUpdates, type UpdateResult } from './utils/update';
import { useSearch } from './hooks/useSearch';
import UpdateNotification from './components/UpdateNotification';
import Navbar, { type Tab } from './components/Navbar';
import CoinCard from './components/CoinCard';
import AlertModal from './components/AlertModal';
import AlertsTab from './components/AlertsTab';
import NotificationBanner from './components/NotificationBanner';
import EnergySavingBanner from './components/EnergySavingBanner';
import SettingsTab from './components/SettingsTab';

const INTERVAL_KEY = 'cryptosentinel_refresh_interval';

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [search, setSearch] = useState('');
  const [selectedCoin, setSelectedCoin] = useState<Coin | null>(null);
  const [notifPerm, setNotifPerm] = useState<NotificationPermission>('default');
  const [batteryDismissed, setBatteryDismissed] = useState(isBatteryBannerDismissed);
  const [dlState, setDlState] = useState<'idle' | 'downloading' | 'done'>('idle');
  const [perPage, setPerPage] = useState<50 | 100>(50);
  const [page, setPage] = useState(1);
  const [availableUpdate, setAvailableUpdate] = useState<UpdateResult | null>(null);
  const [updateDismissed, setUpdateDismissed] = useState(false);
  const lastUpdateCheckRef = useRef<number>(0);

  const runUpdateCheck = useCallback(async () => {
    lastUpdateCheckRef.current = Date.now();
    try {
      const result = await checkForUpdates(__APP_BUILD_NUMBER__);
      if (result.available) setAvailableUpdate(result);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    initNotifications();
    getNotificationPermission().then(setNotifPerm);

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        getNotificationPermission().then(setNotifPerm);
        if (Date.now() - lastUpdateCheckRef.current > 30 * 60 * 1000) {
          runUpdateCheck();
        }
      } else {
        triggerImmediateCheck();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    let unsubDl: (() => void) | null = null;
    onDownloadComplete(() => setDlState('done')).then((fn) => { unsubDl = fn; });

    const updateTimer = setTimeout(runUpdateCheck, 3000);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      unsubDl?.();
      clearTimeout(updateTimer);
    };
  }, [runUpdateCheck]);

  const [refreshInterval, setRefreshInterval] = useState<number>(() => {
    return parseInt(localStorage.getItem(INTERVAL_KEY) || '30000', 10);
  });

  const { currency, changeCurrency } = useCurrency();
  const { coins, loading, error, lastUpdated, refresh } = useCryptoData(refreshInterval, perPage, page, currency);
  const { results: searchResults, searching } = useSearch(search, currency);
  const { favorites, toggle: toggleFavorite, isFavorite, clear: clearFavorites } = useFavorites();
  const { alerts, addAlert, removeAlert, resetAlert, editAlert, clearAlerts } = useAlerts(coins);

  const handleIntervalChange = useCallback((ms: number) => {
    setRefreshInterval(ms);
    localStorage.setItem(INTERVAL_KEY, String(ms));
  }, []);

  const handlePerPageChange = useCallback((n: 50 | 100) => {
    setPerPage(n);
    setPage(1);
  }, []);

  const isSearching = search.trim().length > 0;
  const displayCoins = isSearching ? searchResults : coins;
  const displayLoading = isSearching ? searching : loading;

  const favoriteCoins = useMemo(
    () => coins.filter((c) => isFavorite(c.id)),
    [coins, isFavorite]
  );

  const handleAddAlert = useCallback((coin: Coin) => {
    setSelectedCoin(coin);
  }, []);

  const handleConfirmAlert = useCallback(
    (direction: 'above' | 'below', threshold: number, percentChange?: number) => {
      if (!selectedCoin) return;
      addAlert({
        coinId: selectedCoin.id,
        coinName: selectedCoin.name,
        coinSymbol: selectedCoin.symbol,
        coinImage: selectedCoin.image,
        direction,
        threshold,
        percentChange,
      });
    },
    [selectedCoin, addAlert]
  );

  const triggeredCount = alerts.filter((a) => a.triggered).length;

  return (
    <div className="flex flex-col h-full bg-dark-900">
      <div
        className="fixed inset-x-0 top-0 bg-dark-900 z-50 pointer-events-none"
        style={{ height: 'env(safe-area-inset-top)' }}
      />
      <header className="bg-dark-900 border-b border-dark-700 px-4 pt-safe sticky top-0 z-40">
        <div className="max-w-lg mx-auto">
          <div className="flex items-center justify-between py-3">
            <div className="flex items-center gap-2">
              <span className="text-2xl">₿</span>
              <h1 className="text-white font-bold text-lg tracking-tight">CryptoSentinel</h1>
            </div>
            <div className="flex items-center gap-2">
              {lastUpdated && (
                <span className="text-gray-600 text-xs hidden sm:block">
                  Aggiornato {lastUpdated.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
              )}
              <button
                onClick={refresh}
                className="text-gray-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-dark-700"
                aria-label="Aggiorna prezzi"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            </div>
          </div>

          {tab === 'dashboard' && (
            <div className="pb-3">
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Cerca criptovaluta…"
                  className="w-full bg-dark-700 border border-dark-600 rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-accent-blue transition-colors"
                />
              </div>
            </div>
          )}
        </div>
      </header>

      <main className="flex-1 overflow-y-auto pb-20">
        <div className="max-w-lg mx-auto px-4 py-3">
          <NotificationBanner permission={notifPerm} onPermissionChange={setNotifPerm} />
          <EnergySavingBanner dismissed={batteryDismissed} onDismiss={() => setBatteryDismissed(true)} />

          {error && (
            <div className="bg-accent-red/10 border border-accent-red/30 rounded-xl px-4 py-2 text-xs text-accent-red mb-3">
              {error}
            </div>
          )}

          {availableUpdate && !updateDismissed && (
            <UpdateNotification
              update={availableUpdate}
              dlState={dlState}
              onDismiss={() => setUpdateDismissed(true)}
              onDownloadStart={() => setDlState('downloading')}
            />
          )}

          {tab === 'dashboard' && (
            <div>
              {!isSearching && (
                <div className="flex items-center justify-between mb-3">
                  <div className="flex gap-1">
                    {([50, 100] as const).map((n) => (
                      <button
                        key={n}
                        onClick={() => handlePerPageChange(n)}
                        className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                          perPage === n ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page === 1}
                      className="px-2.5 py-1 rounded-lg bg-dark-700 text-gray-400 hover:text-white disabled:opacity-30 text-sm transition-colors"
                    >
                      ←
                    </button>
                    <span className="text-xs text-gray-500 tabular-nums">Pag. {page}</span>
                    <button
                      onClick={() => setPage((p) => p + 1)}
                      disabled={coins.length < perPage}
                      className="px-2.5 py-1 rounded-lg bg-dark-700 text-gray-400 hover:text-white disabled:opacity-30 text-sm transition-colors"
                    >
                      →
                    </button>
                  </div>
                </div>
              )}

              {displayLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="h-16 bg-dark-800 rounded-xl animate-pulse" />
                  ))}
                </div>
              ) : displayCoins.length === 0 ? (
                <div className="text-center py-12">
                  <div className="text-4xl mb-3">🔍</div>
                  <p className="text-gray-500 text-sm">
                    {isSearching
                      ? `Nessuna criptovaluta trovata per "${search}"`
                      : 'Nessuna criptovaluta disponibile'}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {displayCoins.map((coin) => (
                    <CoinCard
                      key={coin.id}
                      coin={coin}
                      isFavorite={isFavorite(coin.id)}
                      onToggleFavorite={toggleFavorite}
                      onAddAlert={handleAddAlert}
                      currency={currency}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === 'favorites' && (
            <div>
              {favoriteCoins.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center px-8">
                  <div className="text-5xl mb-4">⭐</div>
                  <h3 className="text-white font-semibold text-lg mb-2">Nessun preferito</h3>
                  <p className="text-gray-500 text-sm">
                    Premi la ★ accanto a una criptovaluta per aggiungerla ai tuoi preferiti.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {favoriteCoins.map((coin) => (
                    <CoinCard
                      key={coin.id}
                      coin={coin}
                      isFavorite={true}
                      onToggleFavorite={toggleFavorite}
                      onAddAlert={handleAddAlert}
                      currency={currency}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === 'alerts' && (
            <AlertsTab alerts={alerts} onRemove={removeAlert} onReset={resetAlert} coins={coins} onEdit={editAlert} />
          )}

          {tab === 'settings' && (
            <SettingsTab
              refreshInterval={refreshInterval}
              onIntervalChange={handleIntervalChange}
              favoritesCount={favorites.size}
              alertsCount={alerts.length}
              onClearFavorites={clearFavorites}
              onClearAlerts={clearAlerts}
              notifPerm={notifPerm}
              onPermissionChange={setNotifPerm}
              batteryDismissed={batteryDismissed}
              dlState={dlState}
              onDownloadStart={() => setDlState('downloading')}
              onDownloadDone={() => setDlState('done')}
              currency={currency}
              onCurrencyChange={changeCurrency}
            />
          )}
        </div>
      </main>

      <Navbar
        activeTab={tab}
        onTabChange={setTab}
        alertCount={triggeredCount}
        favoriteCount={favorites.size}
      />

      {selectedCoin && (
        <AlertModal
          coin={selectedCoin}
          onConfirm={handleConfirmAlert}
          onClose={() => setSelectedCoin(null)}
        />
      )}
    </div>
  );
}
