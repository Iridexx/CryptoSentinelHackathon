import { type FC, useState, useEffect, useRef, useCallback } from 'react';

const SESSION_KEY = 'cs_splash_shown';
const AUTO_DISMISS_MS = 3500;

interface Props {
  onDone: () => void;
}

const SplashOverlay: FC<Props> = ({ onDone }) => {
  const [visible, setVisible] = useState(true);
  const [iframeOk, setIframeOk] = useState(true);
  const dismissed = useRef(false);

  const dismiss = useCallback(() => {
    if (dismissed.current) return;
    dismissed.current = true;
    sessionStorage.setItem(SESSION_KEY, '1');
    setVisible(false);
    setTimeout(onDone, 380);
  }, [onDone]);

  // Auto-dismiss after timeout
  useEffect(() => {
    const t = setTimeout(dismiss, AUTO_DISMISS_MS);
    return () => clearTimeout(t);
  }, [dismiss]);

  return (
    <div
      className="fixed inset-0 z-[9999]"
      style={{
        transition: 'opacity 380ms ease',
        opacity: visible ? 1 : 0,
        pointerEvents: visible ? 'auto' : 'none',
      }}
      onClick={dismiss}
    >
      {iframeOk ? (
        <iframe
          src="/splash.html"
          className="w-full h-full border-none block"
          title="Splash"
          onError={() => setIframeOk(false)}
        />
      ) : (
        /* Fallback se l'iframe non carica */
        <div className="w-full h-full flex flex-col items-center justify-center bg-[#0a1220]">
          <div className="flex flex-col items-center gap-4">
            <svg width="80" height="80" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
              <rect width="100" height="100" rx="20" fill="#0a1730" />
              <circle cx="50" cy="38" r="11" fill="#6fb0ff" />
              <rect x="44" y="46" width="12" height="34" rx="2" fill="#dfe8fb" />
              <line x1="20" y1="40" x2="80" y2="40" stroke="#6fb0ff" strokeWidth="2" opacity="0.5" />
            </svg>
            <p className="text-white text-2xl font-bold tracking-wide">CryptoSentinel</p>
            <p className="text-[#6fb0ff] text-sm tracking-widest uppercase">Market Watch</p>
          </div>
        </div>
      )}
    </div>
  );
};

export function shouldShowSplash(): boolean {
  return !sessionStorage.getItem(SESSION_KEY);
}

export default SplashOverlay;
