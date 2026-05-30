package com.cryptowatch.app;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;
import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.work.Constraints;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class PriceCheckWorker extends Worker {
    private static final String PREFS   = "cryptowatch_prefs";
    private static final String KEY     = "alerts_json";
    private static final String CHANNEL = "price_alerts";
    private static final String TAG     = "PriceCheckWorker";
    private static final String WORK_TAG = "price_check";

    public PriceCheckWorker(@NonNull Context context, @NonNull WorkerParameters p) {
        super(context, p);
    }

    public static void schedule(Context ctx) {
        Constraints constraints = new Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build();
        PeriodicWorkRequest request = new PeriodicWorkRequest.Builder(
            PriceCheckWorker.class, 15, TimeUnit.MINUTES)
            .setConstraints(constraints)
            .addTag(WORK_TAG)
            .build();
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
            WORK_TAG,
            androidx.work.ExistingPeriodicWorkPolicy.KEEP,
            request
        );
    }

    @NonNull
    @Override
    public Result doWork() {
        try {
            SharedPreferences prefs = getApplicationContext()
                .getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String alertsJson = prefs.getString(KEY, "[]");
            JSONArray alerts = new JSONArray(alertsJson);

            List<String> coinIds = new ArrayList<>();
            for (int i = 0; i < alerts.length(); i++) {
                JSONObject a = alerts.getJSONObject(i);
                if (!a.optBoolean("triggered", false)) {
                    String id = a.optString("coinId");
                    if (!id.isEmpty() && !coinIds.contains(id)) coinIds.add(id);
                }
            }
            if (coinIds.isEmpty()) return Result.success();

            String ids = String.join(",", coinIds);
            JSONObject prices = fetchJson(
                "https://api.coingecko.com/api/v3/simple/price?ids=" + ids + "&vs_currencies=usd");
            if (prices == null) return Result.retry();

            ensureChannel();
            boolean changed = false;
            for (int i = 0; i < alerts.length(); i++) {
                JSONObject a = alerts.getJSONObject(i);
                if (a.optBoolean("triggered", false)) continue;
                String coinId   = a.optString("coinId");
                String dir      = a.optString("direction");
                double threshold = a.optDouble("threshold", 0);
                if (!prices.has(coinId)) continue;
                double price = prices.getJSONObject(coinId).optDouble("usd", -1);
                if (price < 0) continue;

                boolean fire = (dir.equals("above") && price >= threshold) ||
                               (dir.equals("below") && price <= threshold);
                if (fire) {
                    a.put("triggered", true);
                    changed = true;
                    notify(a.optString("coinName"), dir, threshold, price);
                }
            }
            if (changed) prefs.edit().putString(KEY, alerts.toString()).apply();
            return Result.success();
        } catch (Exception e) {
            Log.e(TAG, "doWork error", e);
            return Result.retry();
        }
    }

    private JSONObject fetchJson(String urlStr) {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(urlStr).openConnection();
            c.setRequestMethod("GET");
            c.setConnectTimeout(10_000);
            c.setReadTimeout(10_000);
            c.setRequestProperty("Accept", "application/json");
            if (c.getResponseCode() != 200) return null;
            BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream()));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) sb.append(line);
            r.close();
            return new JSONObject(sb.toString());
        } catch (Exception e) { return null; }
    }

    private void ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                CHANNEL, "Allarmi Prezzi", NotificationManager.IMPORTANCE_HIGH);
            ch.setDescription("Notifiche allarmi di prezzo crypto");
            ch.enableVibration(true);
            ((NotificationManager) getApplicationContext()
                .getSystemService(Context.NOTIFICATION_SERVICE))
                .createNotificationChannel(ch);
        }
    }

    private void notify(String coinName, String dir, double threshold, double price) {
        String label = dir.equals("above") ? "sopra" : "sotto";
        String body  = "Prezzo " + label + " $" + fmt(threshold) + " · Ora: $" + fmt(price);
        NotificationCompat.Builder b = new NotificationCompat.Builder(getApplicationContext(), CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("🚨 " + coinName)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(true)
            .setVibrate(new long[]{0, 250, 100, 250});
        try {
            NotificationManagerCompat.from(getApplicationContext())
                .notify((int)(System.currentTimeMillis() % Integer.MAX_VALUE), b.build());
        } catch (SecurityException ignored) {}
    }

    private String fmt(double v) {
        if (v >= 1000) return String.format("%.0f", v);
        if (v >= 1)    return String.format("%.2f", v);
        return String.format("%.6f", v);
    }
}
