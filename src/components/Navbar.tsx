import type { FC } from 'react';

export type Tab = 'dashboard' | 'favorites' | 'alerts' | 'settings';

interface Props {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  alertCount: number;
  favoriteCount: number;
}

const Navbar: FC<Props> = ({ activeTab, onTabChange, alertCount, favoriteCount }) => {
  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'dashboard', label: 'Mercato', icon: '📈' },
    { id: 'favorites', label: 'Preferiti', icon: '⭐' },
    { id: 'alerts', label: 'Allarmi', icon: '🔔' },
    { id: 'settings', label: 'Impostazioni', icon: '⚙️' },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-dark-800 border-t border-dark-600 safe-bottom z-50">
      <div className="flex max-w-lg mx-auto">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          const badge = tab.id === 'favorites' ? favoriteCount : tab.id === 'alerts' ? alertCount : 0;
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`flex-1 flex flex-col items-center py-3 gap-0.5 transition-colors relative ${
                isActive ? 'text-accent-blue' : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              <span className="text-xl leading-none">{tab.icon}</span>
              <span className="text-xs font-medium">{tab.label}</span>
              {badge > 0 && (
                <span className="absolute top-2 right-1/2 translate-x-3 bg-accent-red text-white text-xs rounded-full min-w-[16px] h-4 flex items-center justify-center px-1 leading-none">
                  {badge > 99 ? '99+' : badge}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
};

export default Navbar;
