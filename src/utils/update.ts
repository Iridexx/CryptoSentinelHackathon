import { Capacitor, registerPlugin } from '@capacitor/core';
import type { PluginListenerHandle } from '@capacitor/core';

interface AppSettingsPlugin {
  downloadApk(options: { url: string }): Promise<void>;
  openDownloads(): Promise<void>;
  syncAlerts(options: { json: string }): Promise<void>;
  scheduleImmediateCheck(): Promise<void>;
  openWithChooser(options: { url: string; title?: string }): Promise<void>;
  addListener(event: 'downloadComplete', handler: (data: { status: string }) => void): Promise<PluginListenerHandle>;
}
const AppSettings = registerPlugin<AppSettingsPlugin>('AppSettings');

const RELEASES_API = 'https://api.github.com/repos/iridexx/test_app_cloude/releases/latest';
const DEV_RELEASES_API = 'https://api.github.com/repos/iridexx/test_app_cloude/releases/tags/dev';

// L'APK produzione è pubblicato su GitHub Pages, nessun login richiesto
export const APK_PAGES_URL = 'https://iridexx.github.io/test_app_cloude/CryptoSentinel-debug.apk';

export interface UpdateResult {
  available: boolean;
  releaseName: string | null;
  releaseDate: string;
  buildNumber: string | null;
  releaseNotes: string | null;
  downloadUrl: string | null;
}

export interface DevBuildInfo {
  buildNumber: string | null;
  branch: string | null;
  buildDate: string;
  downloadUrl: string | null;
}

export async function checkForUpdates(currentBuildNumber: string): Promise<UpdateResult> {
  const res = await fetch(RELEASES_API, {
    headers: { Accept: 'application/vnd.github+json' },
  });
  if (!res.ok) throw new Error(`GitHub API: ${res.status}`);
  const release = await res.json();

  const releaseDate = new Date(release.published_at as string);
  const apkAsset = (release.assets as { name: string; browser_download_url: string }[])
    ?.find((a) => a.name.endsWith('.apk'));
  const buildMatch = (release.name as string)?.match(/v\d+\.\d+\.(\d+)/);
  const releaseBuildNumber = buildMatch ? parseInt(buildMatch[1], 10) : 0;
  const currentBuildNum = parseInt(currentBuildNumber, 10);
  const available = !isNaN(currentBuildNum) && !isNaN(releaseBuildNumber)
    ? releaseBuildNumber > currentBuildNum
    : false;

  const rawNotes = (release.body as string | null)?.trim() ?? null;

  return {
    available,
    releaseName: (release.name as string) ?? null,
    releaseDate: releaseDate.toLocaleDateString('it-IT', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    }),
    buildNumber: buildMatch ? buildMatch[1] : null,
    releaseNotes: rawNotes && rawNotes.length > 0 ? rawNotes : null,
    downloadUrl: apkAsset?.browser_download_url ?? null,
  };
}

export async function getDevBuildInfo(): Promise<DevBuildInfo> {
  const res = await fetch(DEV_RELEASES_API, {
    headers: { Accept: 'application/vnd.github+json' },
  });
  if (!res.ok) throw new Error(`GitHub API: ${res.status}`);
  const release = await res.json();

  const buildMatch = (release.name as string)?.match(/#(\d+)/);
  const branchMatch = (release.body as string)?.match(/Branch: ([^\s|]+)/);
  const apkAsset = (release.assets as { name: string; browser_download_url: string }[])
    ?.find((a) => a.name.endsWith('.apk'));

  return {
    buildNumber: buildMatch?.[1] ?? null,
    branch: branchMatch?.[1] ?? null,
    buildDate: new Date(release.published_at as string).toLocaleDateString('it-IT', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    }),
    downloadUrl: apkAsset?.browser_download_url ?? null,
  };
}

export async function mergeToMain(branch: string, token: string): Promise<void> {
  const res = await fetch('https://api.github.com/repos/iridexx/test_app_cloude/merges', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'application/vnd.github+json',
    },
    body: JSON.stringify({
      base: 'main',
      head: branch,
      commit_message: `Merge ${branch} → main (da app)`,
    }),
  });
  if (res.status === 201 || res.status === 204) return;
  const data = await res.json().catch(() => ({}));
  throw new Error((data as { message?: string }).message ?? `Errore ${res.status}`);
}

export async function downloadAndInstall(url: string): Promise<void> {
  if (Capacitor.isNativePlatform()) {
    await AppSettings.downloadApk({ url });
  } else {
    window.open(url, '_blank');
  }
}

export async function syncAlertsToNative(alerts: unknown[]): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  try { await AppSettings.syncAlerts({ json: JSON.stringify(alerts) }); } catch { /* ignore */ }
}

export async function triggerImmediateCheck(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  try { await AppSettings.scheduleImmediateCheck(); } catch { /* ignore */ }
}

export async function openDownloadsFolder(): Promise<void> {
  if (Capacitor.isNativePlatform()) {
    await AppSettings.openDownloads();
  }
}

export async function onDownloadComplete(handler: () => void): Promise<() => void> {
  if (!Capacitor.isNativePlatform()) return () => {};
  const handle = await AppSettings.addListener('downloadComplete', handler);
  return () => handle.remove();
}
