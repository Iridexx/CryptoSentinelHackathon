import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import type { Coin } from './types';
import { useCryptoData } from './hooks/useCryptoData';
import { useFavorites } from './hooks/useFavorites';
import { useAlerts } from './hooks/useAlerts';
import { useRangeAlerts } from './hooks/useRangeAlerts';
import { useCurrency } from './hooks/useCurrency';
import { getNotificationPermission, initNotifications } from './utils/notifications';
import { isBatteryBannerDismissed } from './utils/energySaving';
import { onDownloadComplete, triggerImmediateCheck, checkForUpdates, type UpdateResult } from './utils/update';
import { useSearch } from './hooks/useSearch';
import { usePullToRefresh } from './hooks/usePullToRefresh';
import { hapticLight } from './utils/haptics';
import UpdateNotification from './components/UpdateNotification';
import Navbar, { type Tab } from './components/Navbar';
import LogoLighthouse from './components/LogoLighthouse';
import CoinCard from './components/CoinCard';
import AlertModal from './components/AlertModal';
import AlertsTab from './components/AlertsTab';
import NotificationBanner from './components/NotificationBanner';
import EnergySavingBanner from './components/EnergySavingBanner';
import SettingsTab from './components/SettingsTab';

const INTERVAL_KEY = 'cryptosentinel_refresh_interval';
const SLIDER_RANGE_KEY = 'cryptosentinel_alert_slider_range';

type SortBy = 'rank' | 'change' | '7d' | 'volume' | 'price';
type TimeFrame = '1h' | '24h' | '7d';

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [search, setSearch] = useState('');
  const [selectedCoin, setSelectedCoin] = useState<Coin | null>(null);
  const [notifPerm, setNotifPerm] = useState<NotificationPermission>('default');
  const [batteryDismissed, setBatteryDismissed] = useState(isBatteryBannerDismissed);
  const [dlState, setDlState] = useState<'idle' | 'downloading' | 'done'>('idle');
  const [perPage, setPerPage] = useState<50 | 100>(50);
  const [timeFrame, setTimeFrame] = useState<TimeFrame>('24h');
  const [page, setPage] = useState(1);
  const [availableUpdate, setAvailableUpdate] = useState<UpdateResult | null>(null);
  const [sortBy, setSortBy] = useState<SortBy>('rank');
  const [sortDesc, setSortDesc] = useState(true);
  const lastUpdateCheckRef = useRef<number>(0);

  // — Update dismiss/snooze —
  const [dismissedBuild, setDismissedBuild] = useState<string | null>(() =>
    localStorage.getItem('cs_dismissed_build')
  );
  const [snoozedBuild, setSnoozedBuild] = useState<string | null>(() =>
    localStorage.getItem('cs_snoozed_build')
  );
  const [snoozedUntil, setSnoozedUntil] = useState<number>(() =>
    Number(localStorage.getItem('cs_snoozed_until') ?? 0)
  );

  // Re-mostra il popup quando lo snooze scade (senza bisogno di riaprire l'app)
  useEffect(() => {
    if (!snoozedUntil || Date.now() > snoozedUntil) return;
    const t = setTimeout(() => setSnoozedUntil(0), snoozedUntil - Date.now());
    return () => clearTimeout(t);
  }, [snoozedUntil]);

  const isUpdateVisible = useMemo(() =>
    availableUpdate != null &&
    availableUpdate.buildNumber !== dismissedBuild &&
    (snoozedBuild !== availableUpdate.buildNumber || Date.now() > snoozedUntil),
    [availableUpdate, dismissedBuild, snoozedBuild, snoozedUntil]
  );

  // "Ignora": nasconde questa versione specifica per sempre (fino a build più nuovo)
  const handleIgnoreUpdate = useCallback(() => {
    const build = availableUpdate?.buildNumber ?? '_';
    localStorage.setItem('cs_dismissed_build', build);
    setDismissedBuild(build);
  }, [availableUpdate]);

  // "Dopo": riappare dopo 4 ore, oppure subito se esce un build più nuovo
  const handleSnoozeUpdate = useCallback(() => {
    const build = availableUpdate?.buildNumber ?? '_';
    const until = Date.now() + 4 * 60 * 60 * 1000;
    localStorage.setItem('cs_snoozed_build', build);
    localStorage.setItem('cs_snoozed_until', String(until));
    setSnoozedBuild(build);
    setSnoozedUntil(until);
  }, [availableUpdate]);

  // Dopo download completato: resetta tutto
  const handleUpdateDone = useCallback(() => {
    setAvailableUpdate(null);
    localStorage.removeItem('cs_dismissed_build');
    localStorage.removeItem('cs_snoozed_build');
    localStorage.removeItem('cs_snoozed_until');
    setDismissedBuild(null);
    setSnoozedBuild(null);
    setSnoozedUntil(0);
  }, []);

  const runUpdateCheck = useCallback(async () => {
    lastUpdateCheckRef.current = Date.now();
    try {
      const result = await checkForUpdates(__APP_BUILD_NUMBER__);
      if (result.available) setAvailableUpdate(result);
    } catch {
      // Rete non ancora pronta (primo avvio post-installazione): riprova dopo 15s
      lastUpdateCheckRef.current = 0;
      setTimeout(async () => {
        try {
          const result = await checkForUpdates(__APP_BUILD_NUMBER__);
          if (result.available) setAvailableUpdate(result);
        } catch { /* silent */ }
      }, 15_000);
    }
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

  const [sliderRange, setSliderRange] = useState<number>(() => {
    return parseInt(localStorage.getItem(SLIDER_RANGE_KEY) || '20', 10);
  });

  const handleSliderRangeChange = useCallback((n: number) => {
    setSliderRange(n);
    localStorage.setItem(SLIDER_RANGE_KEY, String(n));
  }, []);

  const { currency, changeCurrency } = useCurrency();
  const { coins, loading, error, lastUpdated, refresh } = useCryptoData(refreshInterval, perPage, page, currency);
  const { results: searchResults, searching } = useSearch(search, currency);
  const { favorites, toggle: toggleFavorite, isFavorite, clear: clearFavorites } = useFavorites();
  const { alerts, addAlert, removeAlert, resetAlert, editAlert, clearAlerts, history, clearHistory } = useAlerts(coins);
  const { rangeAlerts, addRangeAlert, removeRangeAlert, editRangeAlert } = useRangeAlerts(coins);

  const [refreshFlash, setRefreshFlash] = useState(false);

  const handleRefresh = useCallback(async () => {
    await refresh();
    setRefreshFlash(true);
    setTimeout(() => setRefreshFlash(false), 1500);
  }, [refresh]);

  const { containerRef: mainRef, indicatorRef: ptrRef, isRefreshing: ptrRefreshing } = usePullToRefresh(handleRefresh, isUpdateVisible);

  const handleIntervalChange = useCallback((ms: number) => {
    setRefreshInterval(ms);
    localStorage.setItem(INTERVAL_KEY, String(ms));
  }, []);

  const handlePerPageChange = useCallback((n: 50 | 100) => {
    setPerPage(n);
    setPage(1);
  }, []);

  const handleSort = useCallback((key: SortBy) => {
    setSortBy((prev) => {
      if (prev === key) { setSortDesc((d) => !d); return key; }
      setSortDesc(true);
      return key;
    });
  }, []);

  const isSearching = search.trim().length > 0;
  const rawDisplayCoins = isSearching ? searchResults : coins;
  const displayLoading = isSearching ? searching : loading;

  const displayCoins = useMemo(() => {
    const arr = [...rawDisplayCoins];
    if (sortBy === 'rank') {
      arr.sort((a, b) => {
        const ar = a.market_cap_rank ?? 9999;
        const br = b.market_cap_rank ?? 9999;
        return sortDesc ? ar - br : br - ar;
      });
    } else if (sortBy === '7d') {
      arr.sort((a, b) => {
        const av = a.price_change_percentage_7d_in_currency ?? 0;
        const bv = b.price_change_percentage_7d_in_currency ?? 0;
        return sortDesc ? bv - av : av - bv;
      });
    } else {
      const key = sortBy === 'change' ? 'price_change_percentage_24h'
        : sortBy === 'volume' ? 'total_volume'
        : 'current_price';
      arr.sort((a, b) => sortDesc ? b[key] - a[key] : a[key] - b[key]);
    }
    return arr;
  }, [rawDisplayCoins, sortBy, sortDesc]);

  const favoriteCoins = useMemo(
    () => coins.filter((c) => isFavorite(c.id)),
    [coins, isFavorite]
  );

  const handleAddAlert = useCallback((coin: Coin) => {
    setSelectedCoin(coin);
  }, []);

  const handleConfirmAlert = useCallback(
    (direction: 'above' | 'below', threshold: number, percentChange?: number, note?: string) => {
      if (!selectedCoin) return;
      addAlert({
        coinId: selectedCoin.id,
        coinName: selectedCoin.name,
        coinSymbol: selectedCoin.symbol,
        coinImage: selectedCoin.image,
        direction,
        threshold,
        percentChange,
        note,
      });
    },
    [selectedCoin, addAlert]
  );

  const handleConfirmRange = useCallback(
    (minPrice: number, maxPrice: number, note?: string) => {
      if (!selectedCoin) return;
      addRangeAlert({
        coinId: selectedCoin.id,
        coinName: selectedCoin.name,
        coinSymbol: selectedCoin.symbol,
        coinImage: selectedCoin.image,
        minPrice,
        maxPrice,
        note,
      });
    },
    [selectedCoin, addRangeAlert]
  );

  const triggeredCount = alerts.filter((a) => a.triggered).length;

  return (
    <div className="flex flex-col h-full bg-dark-900">
      <div
        className="fixed inset-x-0 top-0 bg-dark-900 z-50 pointer-events-none"
        style={{ height: 'env(safe-area-inset-top)' }}
      />
      <header
        className="px-4 pt-safe sticky top-0 z-40"
        style={{
          background: 'linear-gradient(180deg, #07101F 0%, #0A1628 70%, #0D1A2E 100%)',
          borderBottom: '1px solid rgba(59,130,246,0.18)',
        }}
      >
        <div className="max-w-lg mx-auto">
          <div className="flex items-center justify-between py-2.5">
            <div className="flex items-center gap-2">
              <LogoLighthouse />
              <h1
                className="text-white font-bold text-xl tracking-tight"
                style={{ textShadow: '0 0 22px rgba(96,165,250,0.38), 0 0 48px rgba(59,130,246,0.12)' }}
              >
                CryptoSentinel
              </h1>
            </div>
            <div className="flex items-center gap-2">
              {lastUpdated && (
                <div className="flex items-center gap-1.5">
                  <span
                    className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                    style={{ background: '#3B82F6', boxShadow: '0 0 6px rgba(59,130,246,0.9)' }}
                  />
                  <span className={`text-xs tabular-nums transition-colors ${refreshFlash ? 'text-accent-green font-medium' : 'text-gray-500'}`}>
                    {refreshFlash ? '✓ OK' : lastUpdated.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </div>
              )}
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

      <main ref={mainRef} className="flex-1 overflow-y-auto overscroll-y-none pb-20">
        {/* Pull-to-refresh indicator — altezza gestita direttamente via DOM */}
        <div ref={ptrRef} className="h-0 flex items-center justify-center overflow-hidden">
          {ptrRefreshing ? (
            <svg className="w-5 h-5 text-accent-blue animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg
              data-ptr-arrow=""
              style={{ transition: 'transform 150ms, color 150ms' }}
              className="w-5 h-5 text-gray-400"
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </div>

        <div className="max-w-lg mx-auto px-4 py-3">
          <NotificationBanner permission={notifPerm} onPermissionChange={setNotifPerm} />
          <EnergySavingBanner dismissed={batteryDismissed} onDismiss={() => setBatteryDismissed(true)} />

          {error && (
            <div className="bg-accent-red/10 border border-accent-red/30 rounded-xl px-4 py-2 text-xs text-accent-red mb-3">
              {error}
            </div>
          )}

          {availableUpdate && isUpdateVisible && (
            <UpdateNotification
              update={availableUpdate}
              dlState={dlState}
              onIgnore={handleIgnoreUpdate}
              onSnooze={handleSnoozeUpdate}
              onDismiss={handleUpdateDone}
              onDownloadStart={() => setDlState('downloading')}
            />
          )}

          {tab === 'dashboard' && (
            <div>
              {!isSearching && (
                <>
                  <div className="flex items-center justify-between mb-2">
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
                  <div className="flex items-center gap-1.5 mb-2">
                    <span className="text-gray-600 text-xs flex-shrink-0">Periodo:</span>
                    {([
                      { key: '1h' as TimeFrame, label: '1h' },
                      { key: '24h' as TimeFrame, label: '24h' },
                      { key: '7d' as TimeFrame, label: '7g' },
                    ]).map(({ key, label }) => (
                      <button
                        key={key}
                        onClick={() => setTimeFrame(key)}
                        className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                          timeFrame === key ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-1.5 mb-3 overflow-x-auto pb-0.5 scrollbar-none">
                    {([
                      { key: 'rank' as SortBy, label: 'Rank' },
                      { key: 'change' as SortBy, label: '24h %' },
                      { key: '7d' as SortBy, label: '7g %' },
                      { key: 'volume' as SortBy, label: 'Volume' },
                      { key: 'price' as SortBy, label: 'Prezzo' },
                    ]).map(({ key, label }) => (
                      <button
                        key={key}
                        onClick={() => { hapticLight(); handleSort(key); }}
                        className={`flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                          sortBy === key ? 'bg-accent-blue/20 text-accent-blue border border-accent-blue/30' : 'bg-dark-700 text-gray-400 hover:text-white border border-transparent'
                        }`}
                      >
                        {label}
                        {sortBy === key && <span className="text-xs">{sortDesc ? '↓' : '↑'}</span>}
                      </button>
                    ))}
                  </div>
                </>
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
                      showVolume={sortBy === 'volume'}
                      timeFrame={timeFrame}
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
            <AlertsTab alerts={alerts} onRemove={removeAlert} onReset={resetAlert} coins={coins} onEdit={editAlert} history={history} onClearHistory={clearHistory} sliderRange={sliderRange} rangeAlerts={rangeAlerts} onRemoveRange={removeRangeAlert} onEditRange={editRangeAlert} />
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
              sliderRange={sliderRange}
              onSliderRangeChange={handleSliderRangeChange}
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
          onConfirmRange={handleConfirmRange}
          onClose={() => setSelectedCoin(null)}
        />
      )}
    </div>
  );
}
