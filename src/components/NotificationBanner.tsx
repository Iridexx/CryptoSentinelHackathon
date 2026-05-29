import { useState, type FC } from 'react';

interface Props {
  permission: NotificationPermission;
  onPermissionChange: (p: NotificationPermission) => void;
  onRequest: () => Promise<NotificationPermission>;
}

const NotificationBanner: FC<Props> = ({ permission, onPermissionChange, onRequest }) => {
  const [dismissed, setDismissed] = useState(false);

  if (permission === 'granted' || dismissed) return null;

  const handleRequest = async () => {
    const result = await onRequest();
    onPermissionChange(result);
    if (result !== 'default') setDismissed(true);
  };

  return (
    <div className="bg-accent-blue/10 border border-accent-blue/30 rounded-xl px-4 py-3 flex items-center gap-3 mb-3">
      <span className="text-xl flex-shrink-0">🔔</span>
      <div className="flex-1 min-w-0">
        {permission === 'denied' ? (
          <p className="text-xs text-gray-300">
            Le notifiche sono bloccate. Abilitale nelle impostazioni del telefono.
          </p>
        ) : (
          <p className="text-xs text-gray-300">
            Abilita le notifiche per ricevere gli allarmi anche a schermo bloccato.
          </p>
        )}
      </div>
      {permission !== 'denied' && (
        <button
          onClick={handleRequest}
          className="flex-shrink-0 text-xs bg-accent-blue text-white px-3 py-1.5 rounded-lg font-semibold hover:opacity-90 transition-opacity"
        >
          Abilita
        </button>
      )}
      <button
        onClick={() => setDismissed(true)}
        className="flex-shrink-0 text-gray-500 hover:text-gray-300 text-lg leading-none"
        aria-label="Chiudi"
      >
        ×
      </button>
    </div>
  );
};

export default NotificationBanner;
