package com.deepfocus.now

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    private lateinit var status: TextView
    private val handler = Handler(Looper.getMainLooper())

    private val uiLoop = object : Runnable {
        override fun run() {
            status.text = statusText()
            handler.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val prefs = getSharedPreferences("cfg", Context.MODE_PRIVATE)
        val hostEt = findViewById<EditText>(R.id.host)
        val portEt = findViewById<EditText>(R.id.port)
        status = findViewById(R.id.status)

        hostEt.setText(prefs.getString("host", ""))
        portEt.setText(prefs.getInt("port", 8770).toString())

        findViewById<Button>(R.id.save).setOnClickListener {
            val host = hostEt.text.toString().trim()
            val port = portEt.text.toString().trim().toIntOrNull() ?: 8770
            prefs.edit().putString("host", host).putInt("port", port).apply()
            Toast.makeText(this, "Zapisano: $host:$port", Toast.LENGTH_SHORT).show()
            startFocusService()
        }

        findViewById<Button>(R.id.startBtn).setOnClickListener { startFocusService() }

        findViewById<Button>(R.id.accBtn).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            Toast.makeText(this, "Wlacz: Deep Focus Now", Toast.LENGTH_LONG).show()
        }

        findViewById<Button>(R.id.notifBtn).setOnClickListener {
            val i = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
            i.putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
            startActivity(i)
        }

        maybeRequestNotifications()
        startFocusService()
    }

    override fun onResume() {
        super.onResume()
        handler.post(uiLoop)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(uiLoop)
    }

    private fun startFocusService() {
        val i = Intent(this, FocusService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(i)
        } else {
            startService(i)
        }
    }

    private fun maybeRequestNotifications() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 100)
        }
    }

    private fun mmss(sec: Int): String {
        val s = if (sec < 0) 0 else sec
        return "%02d:%02d".format(s / 60, s % 60)
    }

    private fun statusText(): String {
        if (!FocusState.connected) return "● Brak polaczenia z kompem\nSprawdz IP i te sama siec WiFi."
        if (!FocusState.dayActive) return "● Polaczono. Dzien nieaktywny na kompie."
        return if (FocusState.focus)
            "🎯 DEEP FOCUS — PRACA\n${mmss(FocusState.remaining)} do przerwy\nSociale zablokowane."
        else
            "☕ PRZERWA — CZAS SOCIALI\n${mmss(FocusState.remaining)} do konca przerwy"
    }
}
