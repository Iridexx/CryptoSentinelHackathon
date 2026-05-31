import { useState, type FC } from 'react';
import type { UpdateResult } from '../utils/update';
import { APK_PAGES_URL, downloadAndInstall } from '../utils/update';

interface Props {
  update: UpdateResult;
  onDismiss: () => void;
  onDownloadStart: () => void;
}

const UpdateNotification: FC<Props> = ({ update, onDismiss, onDownloadStart }) => {
  const [showModal, setShowModal] = useState(false);

  const handleDownload = async () => {
    setShowModal(false);
    onDismiss();
    onDownloadStart();
    await downloadAndInstall(update.downloadUrl ?? APK_PAGES_URL);
  };

  return (
    <>
      {/* Floating indicator */}
      <button
        onClick={() => setShowModal(true)}
        className="fixed bottom-24 right-4 z-30 w-12 h-12 flex items-center justify-center"
        aria-label="Aggiornamento disponibile"
      >
        <span className="absolute w-full h-full rounded-full bg-accent-green/25 animate-ping" />
        <span className="absolute w-full h-full rounded-full bg-accent-green/15 border border-accent-green/40" />
        <svg className="relative z-10 w-5 h-5 text-accent-green drop-shadow" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
      </button>

      {/* Modal */}
      {showModal && (
        <div
          className="fixed inset-0 bg-black/70 flex items-end sm:items-center justify-center z-50 p-4"
          onClick={() => setShowModal(false)}
        >
          <div
            className="bg-dark-800 rounded-2xl w-full max-w-sm p-5 shadow-2xl border border-dark-600"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="w-8 h-8 rounded-full bg-accent-green/20 flex items-center justify-center flex-shrink-0">
                  <svg className="w-4 h-4 text-accent-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                </span>
                <h2 className="text-white font-bold text-base">Aggiornamento disponibile</h2>
              </div>
              <button onClick={() => setShowModal(false)} className="text-gray-500 hover:text-gray-300 text-xl leading-none">×</button>
            </div>

            {/* Version card */}
            <div className="bg-dark-700 rounded-xl px-4 py-3 mb-4 flex items-center justify-between">
              <div>
                <p className="text-xs text-gray-500 mb-0.5">CryptoWatch</p>
                {update.buildNumber && (
                  <p className="text-white font-bold text-lg font-mono">Build #{update.buildNumber}</p>
                )}
                <p className="text-xs text-gray-500 mt-0.5">{update.releaseDate}</p>
              </div>
              <span className="text-xs font-semibold text-accent-green bg-accent-green/10 px-2.5 py-1 rounded-full">
                Nuova
              </span>
            </div>

            {/* Release notes */}
            {update.releaseNotes && (
              <div className="mb-4">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Note di rilascio</p>
                <p className="text-xs text-gray-300 leading-relaxed whitespace-pre-line">
                  {update.releaseNotes}
                </p>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2">
              <button
                onClick={() => { setShowModal(false); onDismiss(); }}
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
          </div>
        </div>
      )}
    </>
  );
};

export default UpdateNotification;
