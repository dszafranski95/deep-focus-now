package com.deepfocus.now

import android.accessibilityservice.AccessibilityService
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.widget.Toast

/**
 * Usluga Dostepnosci: gdy komp jest w trybie PRACA (FocusState.focus),
 * a na wierzchu pojawi sie zablokowana aplikacja -> wyrzuca do ekranu glownego
 * (efektywnie ja zamyka) i informuje "wroc do pracy".
 */
class BlockerAccessibilityService : AccessibilityService() {

    private val handler = Handler(Looper.getMainLooper())
    private var lastKickPkg: String? = null
    private var lastKickTime: Long = 0

    private val periodic = object : Runnable {
        override fun run() {
            try {
                val pkg = rootInActiveWindow?.packageName?.toString()
                enforce(pkg)
            } catch (_: Exception) {
            }
            handler.postDelayed(this, 1500)
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        handler.postDelayed(periodic, 1500)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            enforce(event.packageName?.toString())
        }
    }

    private fun enforce(pkg: String?) {
        if (pkg == null) return
        if (pkg == packageName) return
        if (!FocusState.focus) return
        if (!FocusState.BLOCKED.contains(pkg)) return

        performGlobalAction(GLOBAL_ACTION_HOME)

        val now = System.currentTimeMillis()
        if (pkg != lastKickPkg || now - lastKickTime > 3000) {
            lastKickPkg = pkg
            lastKickTime = now
            Toast.makeText(
                this,
                "Deep Focus — wroc do pracy. Ta aplikacja jest zablokowana.",
                Toast.LENGTH_SHORT
            ).show()
        }
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }
}
