package com.cryptowatch.app;

import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.os.Bundle;
import com.getcapacitor.BridgeActivity;
import java.io.File;

public class MainActivity extends BridgeActivity {
    private static final String PREFS = "cryptowatch_prefs";
    private static final String KEY_VER = "last_version_code";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(AppSettingsPlugin.class);
        clearWebCacheOnUpdate();
        super.onCreate(savedInstanceState);
        // Avvia il controllo prezzi in background (ogni 15 min, solo con rete)
        PriceCheckWorker.schedule(this);
    }

    private void clearWebCacheOnUpdate() {
        try {
            PackageInfo info = getPackageManager().getPackageInfo(getPackageName(), 0);
            long current = info.getLongVersionCode();
            SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
            long last = prefs.getLong(KEY_VER, -1);

            if (current != last) {
                // Cache HTTP + Service Worker (causa schermata bianca dopo aggiornamento)
                // localStorage/IndexedDB (token, allarmi, preferiti) restano intatti
                deleteDir(new File(getCacheDir(), "WebView"));
                deleteDir(new File(getDataDir(), "app_webview/Default/Cache"));
                deleteDir(new File(getDataDir(), "app_webview/Default/Code Cache"));
                deleteDir(new File(getDataDir(), "app_webview/Default/Service Worker"));
                prefs.edit().putLong(KEY_VER, current).apply();
            }
        } catch (Exception ignored) {}
    }

    private void deleteDir(File dir) {
        if (dir == null || !dir.exists()) return;
        if (dir.isDirectory()) {
            File[] files = dir.listFiles();
            if (files != null) for (File f : files) deleteDir(f);
        }
        dir.delete();
    }
}
