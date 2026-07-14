package com.deepfocus.now

/** Wspoldzielony stan pobierany z kompa (serwer LAN /status). */
object FocusState {
    @Volatile var focus: Boolean = false      // czy trwa PRACA (blokuj apki)
    @Volatile var mode: String = "WORK"
    @Volatile var remaining: Int = 0
    @Volatile var dayActive: Boolean = false
    @Volatile var connected: Boolean = false
    @Volatile var lastUpdate: Long = 0L

    /** Paczki aplikacji do zablokowania w trybie PRACA. YouTube i Signal sa dozwolone. */
    val BLOCKED: Set<String> = setOf(
        "com.instagram.android",
        "com.zhiliaoapp.musically",        // TikTok
        "com.ss.android.ugc.trill",        // TikTok (inny region)
        "com.facebook.katana",             // Facebook
        "com.facebook.lite",
        "com.facebook.orca",               // Messenger
        "com.twitter.android",             // X / Twitter
        "com.reddit.frontpage",            // Reddit
        "com.snapchat.android",            // Snapchat
        "com.whatsapp",                    // WhatsApp
        "com.whatsapp.w4b",
        "org.telegram.messenger",          // Telegram
        "org.telegram.messenger.web",
        "com.linkedin.android",            // LinkedIn
        "com.discord",                     // Discord
        "com.pinterest",                   // Pinterest
        "com.google.android.apps.tachyon"  // (przyklad) - edytuj wg potrzeb
    )
}
