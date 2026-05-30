package com.cryptowatch.app;

import android.content.Intent;
import android.net.Uri;
import android.provider.Settings;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "AppSettings")
public class AppSettingsPlugin extends Plugin {

    @PluginMethod
    public void openNotifications(PluginCall call) {
        Intent intent = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS);
        intent.putExtra(Settings.EXTRA_APP_PACKAGE, getContext().getPackageName());
        getActivity().startActivity(intent);
        call.resolve();
    }

    @PluginMethod
    public void openWithChooser(PluginCall call) {
        String url = call.getString("url");
        if (url == null) { call.reject("url mancante"); return; }
        String title = call.getString("title", "Apri con");

        Intent view = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
        Intent chooser = Intent.createChooser(view, title);
        chooser.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(chooser);
        call.resolve();
    }
}
