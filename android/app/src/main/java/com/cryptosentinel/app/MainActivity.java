package com.cryptosentinel.app;

import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.graphics.Color;
import android.os.Bundle;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    private static final String PREFS = "cryptosentinel_prefs";
    private static final String KEY_VER = "last_version_code";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(AppSettingsPlugin.class);
        clearHttpCacheOnUpdate();
        super.onCreate(savedInstanceState);
        // Imposta dopo super.onCreate() così sovrascrive il tema di sistema
        getWindow().setStatusBarColor(Color.parseColor("#0a0e1a"));
        PriceCheckWorker.schedule(this);
    }

    private void clearHttpCacheOnUpdate() {
        try {
            PackageInfo info = getPackageManager().getPackageInfo(getPackageName(), 0);
            long current = info.getLongVersionCode();
            SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
            long last = prefs.getLong(KEY_VER, -1);

            if (current != last) {
                // clearCache(true) è app-wide: pulisce solo la cache HTTP,
                // localStorage/IndexedDB/token/allarmi/preferiti restano intatti
                WebView temp = new WebView(this);
                temp.clearCache(true);
                temp.destroy();
                prefs.edit().putLong(KEY_VER, current).apply();
            }
        } catch (Exception ignored) {}
    }
}
