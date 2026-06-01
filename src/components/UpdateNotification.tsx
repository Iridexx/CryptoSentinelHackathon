import { useState, useEffect, type FC } from 'react';
import type { UpdateResult } from '../utils/update';
import { APK_PAGES_URL, downloadAndInstall, openDownloadsFolder } from '../utils/update';

interface Props {
  update: UpdateResult;
  dlState: 'idle' | 'downloading' | 'done';
  onIgnore: () => void;       // ignora questa versione (riappare solo con build più nuovo)
  onSnooze: () => void;       // rimanda di 4 ore
  onDismiss: () => void;      // chiudi dopo download completato
  onDownloadStart: () => void;
}

const APK_FILENAME = 'CryptoSentinel-debug.apk';

const UpdateNotification: FC<Props> = ({ update, dlState, onIgnore, onSnooze, onDismiss, onDownloadStart }) => {
  const [showModal, setShowModal] = useState(false);

  // Auto-apri il popup quando il download termina
  useEffect(() => {
    if (dlState === 'done') setShowModal(true);
  }, [dlState]);

  const handleDownload = async () => {
    setShowModal(false);
    onDownloadStart();
    await downloadAndInstall(update.downloadUrl ?? APK_PAGES_URL);
  };

  const handleOpenDownloads = async () => {
    await openDownloadsFolder();
    setShowModal(false);
    onDismiss();
  };

  const handleDismissDone = () => {
    setShowModal(false);
    onDismiss();
  };

  return (
    <>
      {/* Floating indicator — nascosto durante il download */}
      {dlState !== 'downloading' && (
        <button
          onClick={() => setShowModal(true)}
          className="fixed bottom-24 right-4 z-30 w-12 h-12 flex items-center justify-center"
          aria-label={dlState === 'done' ? 'Download completato' : 'Aggiornamento disponibile'}
        >
          {dlState === 'done' ? (
            <>
              <span className="absolute w-full h-full rounded-full bg-accent-green/20 border border-accent-green/40" />
              <svg className="relative z-10 w-5 h-5 text-accent-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
              </svg>
            </>
          ) : (
            <>
              <span className="absolute w-full h-full rounded-full bg-accent-green/25 animate-ping" />
              <span className="absolute w-full h-full rounded-full bg-accent-green/15 border border-accent-green/40" />
              <svg className="relative z-10 w-5 h-5 text-accent-green drop-shadow" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            </>
          )}
        </button>
      )}

      {/* Modal */}
      {showModal && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
          onClick={dlState === 'done' ? handleDismissDone : onSnooze}
        >
          <div
            className="bg-dark-800 rounded-2xl w-full max-w-sm p-5 shadow-2xl border border-dark-600 flex flex-col max-h-[85vh]"
            onClick={(e) => e.stopPropagation()}
            onTouchMove={(e) => e.stopPropagation()}
          >
            {dlState === 'done' ? (
              /* ── Stato: download completato ── */
              <>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <span className="w-8 h-8 rounded-full bg-accent-green/20 flex items-center justify-center flex-shrink-0">
                      <svg className="w-4 h-4 text-accent-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                    </span>
                    <h2 className="text-white font-bold text-base">Download completato</h2>
                  </div>
                  <button onClick={handleDismissDone} className="text-gray-500 hover:text-gray-300 text-xl leading-none">×</button>
                </div>

                <div className="bg-dark-700 rounded-xl px-4 py-3 mb-4">
                  <p className="text-xs text-gray-500 mb-1">File salvato in</p>
                  <p className="text-sm text-white font-mono break-all">Download/{APK_FILENAME}</p>
                </div>

                <p className="text-xs text-gray-500 mb-4 leading-relaxed">
                  Apri la cartella Download e tocca il file per installare l&apos;aggiornamento.
                </p>

                <div className="flex gap-2">
                  <button
                    onClick={handleDismissDone}
                    className="flex-1 py-2.5 bg-dark-700 text-gray-300 text-sm rounded-xl hover:bg-dark-600 transition-colors"
                  >
                    Chiudi
                  </button>
                  <button
                    onClick={handleOpenDownloads}
                    className="flex-1 py-2.5 bg-accent-green text-white text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity"
                  >
                    Apri Download
                  </button>
                </div>
              </>
            ) : (
              /* ── Stato: aggiornamento disponibile ── */
              <>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <span className="w-8 h-8 rounded-full bg-accent-green/20 flex items-center justify-center flex-shrink-0">
                      <svg className="w-4 h-4 text-accent-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                    </span>
                    <h2 className="text-white font-bold text-base">Aggiornamento disponibile</h2>
                  </div>
                  <button onClick={() => { setShowModal(false); onSnooze(); }} className="text-gray-500 hover:text-gray-300 text-xl leading-none">×</button>
                </div>

                <div className="bg-dark-700 rounded-xl px-4 py-3 mb-4">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-xs text-gray-500">CryptoSentinel</p>
                    <span className="flex-shrink-0 text-xs font-semibold text-accent-green bg-accent-green/10 px-2.5 py-1 rounded-full">
                      Nuova
                    </span>
                  </div>
                  <p className="text-white font-bold text-lg font-mono leading-snug break-words">
                    {update.releaseName ?? (update.buildNumber ? `Build #${update.buildNumber}` : 'Nuova versione')}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">{update.releaseDate}</p>
                </div>

                {update.releaseNotes && (
                  <div className="mb-4 flex flex-col min-h-0">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex-shrink-0">Note di rilascio</p>
                    <div className="overflow-y-auto max-h-40 overscroll-contain">
                      <p className="text-xs text-gray-300 leading-relaxed whitespace-pre-line">
                        {update.releaseNotes}
                      </p>
                    </div>
                  </div>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={() => { setShowModal(false); onIgnore(); }}
                    className="flex-1 py-2.5 rounded-xl text-xs text-gray-500 hover:text-gray-300 transition-colors"
                    style={{ background: 'rgba(255,255,255,0.04)' }}
                  >
                    Ignora
                  </button>
                  <button
                    onClick={() => { setShowModal(false); onSnooze(); }}
                    className="flex-1 py-2.5 bg-dark-700 text-gray-300 text-sm rounded-xl hover:bg-dark-600 transition-colors"
                  >
                    Dopo
                  </button>
                  <button
                    onClick={handleDownload}
                    className="flex-1 py-2.5 bg-accent-green text-white text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity"
                  >
                    Scarica
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
};

export default UpdateNotification;
