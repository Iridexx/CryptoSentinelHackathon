import { useState, useMemo, useCallback } from 'react';
import type { Coin } from './types';
import { useCryptoData } from './hooks/useCryptoData';
import { useFavorites } from './hooks/useFavorites';
import { useAlerts } from './hooks/useAlerts';
import { getNotificationPermission } from './utils/notifications';
import Navbar, { type Tab } from './components/Navbar';
import CoinCard from './components/CoinCard';
import AlertModal from './components/AlertModal';
import AlertsTab from './components/AlertsTab';
import NotificationBanner from './components/NotificationBanner';
import SettingsTab from './components/SettingsTab';

const INTERVAL_KEY = 'cryptowatch_refresh_interval';

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [search, setSearch] = useState('');
  const [selectedCoin, setSelectedCoin] = useState<Coin | null>(null);
  const [notifPerm, setNotifPerm] = useState<NotificationPermission>(getNotificationPermission);
  const [refreshInterval, setRefreshInterval] = useState<number>(() => {
    return parseInt(localStorage.getItem(INTERVAL_KEY) || '30000', 10);
  });

  const { coins, loading, error, lastUpdated, refresh } = useCryptoData(refreshInterval);
  const { favorites, toggle: toggleFavorite, isFavorite, clear: clearFavorites } = useFavorites();
  const { alerts, addAlert, removeAlert, resetAlert, clearAlerts } = useAlerts(coins);

  const handleIntervalChange = useCallback((ms: number) => {
    setRefreshInterval(ms);
    localStorage.setItem(INTERVAL_KEY, String(ms));
  }, []);

  const filteredCoins = useMemo(() => {
    if (!search.trim()) return coins;
    const q = search.toLowerCase().trim();
    return coins.filter((c) => c.name.toLowerCase().includes(q) || c.symbol.toLowerCase().includes(q));
  }, [coins, search]);

  const favoriteCoins = useMemo(
    () => coins.filter((c) => isFavorite(c.id)),
    [coins, isFavorite]
  );

  const handleAddAlert = useCallback((coin: Coin) => {
    setSelectedCoin(coin);
  }, []);

  const handleConfirmAlert = useCallback(
    (direction: 'above' | 'below', threshold: number) => {
      if (!selectedCoin) return;
      addAlert({
        coinId: selectedCoin.id,
        coinName: selectedCoin.name,
        coinSymbol: selectedCoin.symbol,
        coinImage: selectedCoin.image,
        direction,
        threshold,
      });
    },
    [selectedCoin, addAlert]
  );

  const triggeredCount = alerts.filter((a) => a.triggered).length;

  return (
    <div className="flex flex-col h-full bg-dark-900">
      {/* Header */}
      <header className="bg-dark-900 border-b border-dark-700 px-4 pt-safe sticky top-0 z-40">
        <div className="max-w-lg mx-auto">
          <div className="flex items-center justify-between py-3">
            <div className="flex items-center gap-2">
              <span className="text-2xl">₿</span>
              <h1 className="text-white font-bold text-lg tracking-tight">CryptoWatch</h1>
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

      {/* Contenuto principale */}
      <main className="flex-1 overflow-y-auto pb-20">
        <div className="max-w-lg mx-auto px-4 py-3">
          <NotificationBanner permission={notifPerm} onPermissionChange={setNotifPerm} />

          {error && (
            <div className="bg-accent-red/10 border border-accent-red/30 rounded-xl px-4 py-2 text-xs text-accent-red mb-3">
              {error}
            </div>
          )}

          {/* Tab Dashboard */}
          {tab === 'dashboard' && (
            <div>
              {loading ? (
                <div className="space-y-2">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="h-16 bg-dark-800 rounded-xl animate-pulse" />
                  ))}
                </div>
              ) : filteredCoins.length === 0 ? (
                <div className="text-center py-12">
                  <div className="text-4xl mb-3">🔍</div>
                  <p className="text-gray-500 text-sm">Nessuna criptovaluta trovata per "{search}"</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredCoins.map((coin) => (
                    <CoinCard
                      key={coin.id}
                      coin={coin}
                      isFavorite={isFavorite(coin.id)}
                      onToggleFavorite={toggleFavorite}
                      onAddAlert={handleAddAlert}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Tab Preferiti */}
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
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Tab Allarmi */}
          {tab === 'alerts' && (
            <AlertsTab alerts={alerts} onRemove={removeAlert} onReset={resetAlert} />
          )}

          {/* Tab Impostazioni */}
          {tab === 'settings' && (
            <SettingsTab
              refreshInterval={refreshInterval}
              onIntervalChange={handleIntervalChange}
              favoritesCount={favorites.size}
              alertsCount={alerts.length}
              onClearFavorites={clearFavorites}
              onClearAlerts={clearAlerts}
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
