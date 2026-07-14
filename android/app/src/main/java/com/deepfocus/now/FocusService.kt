package com.deepfocus.now

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Foreground service: co kilka sekund pyta komp (LAN /status) o stan Deep Focus,
 * aktualizuje wspoldzielony FocusState i pokazuje licznik w powiadomieniu.
 */
class FocusService : Service() {

    private val channelId = "deepfocus"
    @Volatile private var running = false
    private var thread: Thread? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        startForeground(1, buildNotification("Deep Focus Now", "Laczenie z kompem..."))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!running) {
            running = true
            thread = Thread { loop() }.also { it.start() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        thread?.interrupt()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun loop() {
        var tick = 0
        while (running) {
            try {
                if (tick % 3 == 0) {
                    poll()
                } else if (FocusState.dayActive && FocusState.remaining > 0) {
                    FocusState.remaining -= 1     // plynne odliczanie miedzy zapytaniami
                }
                updateNotification()
            } catch (_: Exception) {
            }
            tick++
            try {
                Thread.sleep(1000)
            } catch (_: InterruptedException) {
                break
            }
        }
    }

    private fun poll() {
        val prefs = getSharedPreferences("cfg", Context.MODE_PRIVATE)
        val host = prefs.getString("host", "") ?: ""
        val port = prefs.getInt("port", 8770)
        if (host.isBlank()) {
            FocusState.connected = false
            return
        }
        try {
            val url = URL("http://$host:$port/status")
            val con = url.openConnection() as HttpURLConnection
            con.connectTimeout = 2500
            con.readTimeout = 2500
            con.requestMethod = "GET"
            val code = con.responseCode
            if (code == 200) {
                val body = con.inputStream.bufferedReader().use { it.readText() }
                val j = JSONObject(body)
                FocusState.focus = j.optBoolean("focus", false)
                FocusState.mode = j.optString("mode", "WORK")
                FocusState.remaining = j.optInt("remaining", 0)
                FocusState.dayActive = j.optBoolean("day_active", false)
                FocusState.connected = true
                FocusState.lastUpdate = System.currentTimeMillis()
            } else {
                FocusState.connected = false
            }
            con.disconnect()
        } catch (_: Exception) {
            FocusState.connected = false
        }
    }

    private fun mmss(sec: Int): String {
        val s = if (sec < 0) 0 else sec
        return "%02d:%02d".format(s / 60, s % 60)
    }

    private fun statusText(): String {
        if (!FocusState.connected) return "Brak polaczenia z kompem"
        if (!FocusState.dayActive) return "Dzien nieaktywny"
        return if (FocusState.focus)
            "DEEP FOCUS — praca ${mmss(FocusState.remaining)} (sociale zablokowane)"
        else
            "PRZERWA — czas sociali ${mmss(FocusState.remaining)}"
    }

    private fun updateNotification() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(1, buildNotification("Deep Focus Now", statusText()))
    }

    private fun buildNotification(title: String, text: String): Notification {
        val open = android.app.PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            android.app.PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, channelId)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_focus)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(open)
            .build()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(
                channelId, "Deep Focus", NotificationManager.IMPORTANCE_LOW
            )
            ch.description = "Licznik i stan Deep Focus"
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(ch)
        }
    }
}
