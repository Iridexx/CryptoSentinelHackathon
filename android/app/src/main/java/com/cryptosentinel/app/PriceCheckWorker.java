package com.cryptosentinel.app;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;
import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.work.BackoffPolicy;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.OutOfQuotaPolicy;
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
    private static final String PREFS            = "cryptosentinel_prefs";
    private static final String KEY              = "alerts_json";
    private static final String RANGE_KEY        = "range_alerts_json";
    private static final String FAV_COINS_KEY    = "fav_coins_json";
    private static final String FAV_UP_KEY       = "fav_up_pct";
    private static final String FAV_DOWN_KEY     = "fav_down_pct";
    private static final String FAV_REF_KEY        = "fav_ref_prices";
    private static final String FAV_CURRENCY_KEY   = "fav_currency";
    private static final String PENDING_FAV_KEY    = "pending_fav_alerts_json";
    private static final String CHANNEL          = "price_alerts";
    private static final String TAG              = "PriceCheckWorker";
    private static final long   COOLDOWN_MS      = 5 * 60 * 1000L;
    private static final String WORK_TAG         = "price_check";
    private static final String WORK_IMMEDIATE   = "price_check_immediate";

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
            // LINEAR backoff: if a retry is needed, wait 10 min then 20 min — avoids hours-long backoff
            .setBackoffCriteria(BackoffPolicy.LINEAR, 10, TimeUnit.MINUTES)
            .addTag(WORK_TAG)
            .build();
        // KEEP: don't reset the timer if the job is already running fine
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
            WORK_TAG,
            ExistingPeriodicWorkPolicy.KEEP,
            request
        );
    }

    public static void scheduleImmediate(Context ctx) {
        Constraints constraints = new Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build();
        OneTimeWorkRequest request = new OneTimeWorkRequest.Builder(PriceCheckWorker.class)
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .setConstraints(constraints)
            .addTag(WORK_IMMEDIATE)
            .build();
        WorkManager.getInstance(ctx).enqueueUniqueWork(
            WORK_IMMEDIATE,
            ExistingWorkPolicy.REPLACE,
            request
        );
    }

    @NonNull
    @Override
    public Result doWork() {
        try {
            SharedPreferences prefs = getApplicationContext()
                .getSharedPreferences(PREFS, Context.MODE_PRIVATE);

            String alertsJson      = prefs.getString(KEY, "[]");
            String rangeAlertsJson = prefs.getString(RANGE_KEY, "[]");
            String favCoinsJson    = prefs.getString(FAV_COINS_KEY, "[]");
            float  favUpPct        = prefs.getFloat(FAV_UP_KEY, 0f);
            float  favDownPct      = prefs.getFloat(FAV_DOWN_KEY, 0f);
            String favCurrency     = prefs.getString(FAV_CURRENCY_KEY, "usd").toLowerCase();

            JSONArray alerts      = new JSONArray(alertsJson);
            JSONArray rangeAlerts = new JSONArray(rangeAlertsJson);
            JSONArray favCoins    = new JSONArray(favCoinsJson);

            // Collect all coin IDs from every source in a single list
            List<String> coinIds = new ArrayList<>();
            for (int i = 0; i < alerts.length(); i++) {
                JSONObject a = alerts.getJSONObject(i);
                if (!a.optBoolean("triggered", false)) {
                    String id = a.optString("coinId");
                    if (!id.isEmpty() && !coinIds.contains(id)) coinIds.add(id);
                }
            }
            for (int i = 0; i < rangeAlerts.length(); i++) {
                String id = rangeAlerts.getJSONObject(i).optString("coinId");
                if (!id.isEmpty() && !coinIds.contains(id)) coinIds.add(id);
            }
            boolean hasFavAlerts = (favUpPct > 0 || favDownPct > 0) && favCoins.length() > 0;
            if (hasFavAlerts) {
                for (int i = 0; i < favCoins.length(); i++) {
                    String id = favCoins.getJSONObject(i).optString("id");
                    if (!id.isEmpty() && !coinIds.contains(id)) coinIds.add(id);
                }
            }

            if (coinIds.isEmpty()) return Result.success();

            // Single API call -- include fav currency if different from usd
            String ids = String.join(",", coinIds);
            String vsParams = favCurrency.equals("usd") ? "usd" : "usd," + favCurrency;
            JSONObject prices = fetchJson(
                "https://api.coingecko.com/api/v3/simple/price?ids=" + ids + "&vs_currencies=" + vsParams);
            // Don't retry on API failure — periodic job would go into exponential backoff
            // (up to 5 hours) causing notifications to stop. Just wait for the next period.
            if (prices == null) return Result.success();

            ensureChannel();

            // --- Regular price alerts ---
            boolean alertsChanged = false;
            for (int i = 0; i < alerts.length(); i++) {
                JSONObject a = alerts.getJSONObject(i);
                if (a.optBoolean("triggered", false)) continue;
                String coinId    = a.optString("coinId");
                String dir       = a.optString("direction");
                double threshold = a.optDouble("threshold", 0);
                if (!prices.has(coinId)) continue;
                double price = prices.getJSONObject(coinId).optDouble("usd", -1);
                if (price < 0) continue;
                boolean fire = (dir.equals("above") && price >= threshold) ||
                               (dir.equals("below") && price <= threshold);
                if (fire) {
                    a.put("triggered", true);
                    alertsChanged = true;
                    notify(a.optString("coinName"), dir, threshold, price, a.optString("note", null));
                }
            }
            if (alertsChanged) prefs.edit().putString(KEY, alerts.toString()).apply();

            // --- Range alerts ---
            boolean rangeChanged = false;
            long nowMs = System.currentTimeMillis();
            for (int i = 0; i < rangeAlerts.length(); i++) {
                JSONObject a = rangeAlerts.getJSONObject(i);
                String coinId = a.optString("coinId");
                if (!prices.has(coinId)) continue;
                double price = prices.getJSONObject(coinId).optDouble("usd", -1);
                if (price < 0) continue;
                double minPrice = a.optDouble("minPrice", 0);
                double maxPrice = a.optDouble("maxPrice", 0);
                boolean isInside = price >= minPrice && price <= maxPrice;
                if (!a.has("isInsideRange") || a.isNull("isInsideRange")) {
                    a.put("isInsideRange", isInside);
                    rangeChanged = true;
                    continue;
                }
                boolean wasInside = a.optBoolean("isInsideRange", false);
                if (isInside == wasInside) continue;
                long lastNotified = a.optLong("lastNotifiedAt", 0);
                a.put("isInsideRange", isInside);
                rangeChanged = true;
                if (nowMs - lastNotified >= COOLDOWN_MS) {
                    a.put("lastNotifiedAt", nowMs);
                    notifyRange(a.optString("coinName"), minPrice, maxPrice, price, isInside, a.optString("note", null));
                }
            }
            if (rangeChanged) prefs.edit().putString(RANGE_KEY, rangeAlerts.toString()).apply();

            // --- Favorite price alerts ---
            if (hasFavAlerts) {
                checkFavAlerts(prefs, favCoins, favUpPct, favDownPct, prices, favCurrency);
            }

            return Result.success();
        } catch (Exception e) {
            Log.e(TAG, "doWork error", e);
            return Result.success();
        }
    }

    private void checkFavAlerts(SharedPreferences prefs, JSONArray favCoins,
                                 float upPct, float downPct, JSONObject prices, String currency) {
        try {
            String refPricesStr = prefs.getString(FAV_REF_KEY, "{}");
            JSONObject refPrices = new JSONObject(refPricesStr);
            boolean changed = false;

            JSONArray pendingAlerts;
            try { pendingAlerts = new JSONArray(prefs.getString(PENDING_FAV_KEY, "[]")); }
            catch (Exception e) { pendingAlerts = new JSONArray(); }
            boolean pendingChanged = false;

            for (int i = 0; i < favCoins.length(); i++) {
                JSONObject coin = favCoins.getJSONObject(i);
                String coinId     = coin.optString("id");
                String coinName   = coin.optString("name");
                String coinSymbol = coin.optString("symbol");

                if (!prices.has(coinId)) continue;
                double current = prices.getJSONObject(coinId).optDouble(currency, -1);
                if (current < 0) continue;

                if (!refPrices.has(coinId)) {
                    refPrices.put(coinId, current);
                    changed = true;
                    continue;
                }

                double ref = refPrices.getDouble(coinId);
                if (ref <= 0) {
                    refPrices.put(coinId, current);
                    changed = true;
                    continue;
                }

                double pct = (current - ref) / ref * 100.0;
                String direction = null;

                if (upPct > 0 && pct >= upPct) {
                    direction = "up";
                } else if (downPct > 0 && pct <= -downPct) {
                    direction = "down";
                }

                if (direction != null) {
                    refPrices.put(coinId, current);
                    changed = true;
                    notifyFavMove(coinName, coinSymbol, direction, Math.abs(pct), current);
                    // Queue alert for JS to pick up when app returns to foreground
                    JSONObject pending = new JSONObject();
                    pending.put("coinId", coinId);
                    pending.put("coinName", coinName);
                    pending.put("coinSymbol", coinSymbol);
                    pending.put("direction", direction);
                    pending.put("pct", Math.abs(pct));
                    pending.put("currentPrice", current);
                    pending.put("refPrice", ref);
                    pendingAlerts.put(pending);
                    pendingChanged = true;
                }
            }

            SharedPreferences.Editor ed = prefs.edit();
            if (changed) ed.putString(FAV_REF_KEY, refPrices.toString());
            if (pendingChanged) ed.putString(PENDING_FAV_KEY, pendingAlerts.toString());
            if (changed || pendingChanged) ed.apply();
        } catch (Exception e) {
            Log.e(TAG, "checkFavAlerts error", e);
        }
    }

    private void notifyFavMove(String coinName, String coinSymbol,
                                String direction, double pct, double price) {
        Context ctx = getApplicationContext();
        String arrow = direction.equals("up") ? "▲" : "▼";
        String label = direction.equals("up") ? "rialzo" : "ribasso";
        String title = arrow + " " + coinName + " (" + coinSymbol.toUpperCase() + ")"
                       + " — " + label + " del " + String.format("%.1f", pct) + "%";
        String body  = "Movimento del " + String.format("%.1f", pct) + "% verso il "
                       + label + "  ·  Ora: " + fmt(price);

        Intent intent = new Intent(ctx, MainActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        int flags = Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
            ? PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
            : PendingIntent.FLAG_UPDATE_CURRENT;
        PendingIntent pi = PendingIntent.getActivity(ctx, 2, intent, flags);

        NotificationCompat.Builder b = new NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(pi)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(true)
            .setVibrate(new long[]{0, 250, 100, 250});
        try {
            NotificationManagerCompat.from(ctx)
                .notify(notifId(coinName + direction), b.build());
        } catch (SecurityException ignored) {}
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

    private void notify(String coinName, String dir, double threshold, double price, String note) {
        Context ctx = getApplicationContext();
        String arrow = dir.equals("above") ? "▲" : "▼";
        String label = dir.equals("above") ? "superato al rialzo" : "superato al ribasso";
        String title = arrow + " " + coinName + " — soglia " + label;
        String body  = "Soglia: $" + fmt(threshold) + "  ·  Prezzo attuale: $" + fmt(price);
        if (note != null && !note.isEmpty()) body += "\n📝 " + note;

        Intent intent = new Intent(ctx, MainActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        int flags = Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
            ? PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
            : PendingIntent.FLAG_UPDATE_CURRENT;
        PendingIntent pi = PendingIntent.getActivity(ctx, 0, intent, flags);

        NotificationCompat.Builder b = new NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(pi)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(true)
            .setVibrate(new long[]{0, 250, 100, 250});
        try {
            NotificationManagerCompat.from(ctx)
                .notify(notifId(coinName + dir + threshold), b.build());
        } catch (SecurityException ignored) {}
    }

    private void notifyRange(String coinName, double minPrice, double maxPrice,
                              double price, boolean entered, String note) {
        Context ctx = getApplicationContext();
        String status = entered ? "↔ Entrato nel range" : "↗ Uscito dal range";
        String title = status + " — " + coinName;
        String body = "Range: $" + fmt(minPrice) + " – $" + fmt(maxPrice) + "  ·  Ora: $" + fmt(price);
        if (note != null && !note.isEmpty()) body += "\n📝 " + note;

        Intent intent = new Intent(ctx, MainActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        int flags = Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
            ? PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
            : PendingIntent.FLAG_UPDATE_CURRENT;
        PendingIntent pi = PendingIntent.getActivity(ctx, 1, intent, flags);

        NotificationCompat.Builder b = new NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(pi)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(true)
            .setVibrate(new long[]{0, 250, 100, 250});
        try {
            NotificationManagerCompat.from(ctx)
                .notify(notifId(coinName + minPrice + maxPrice), b.build());
        } catch (SecurityException ignored) {}
    }

    private int notifId(String seed) {
        int h = 5381;
        for (int i = 0; i < seed.length(); i++) {
            h = 33 * h ^ seed.charAt(i);
        }
        return (Math.abs(h) % 1_900_000) + 1;
    }

    private String fmt(double v) {
        if (v >= 1000) return String.format("%.0f", v);
        if (v >= 1)    return String.format("%.2f", v);
        return String.format("%.6f", v);
    }
}
