# -*- coding: utf-8 -*-
"""
Deep Focus Now — praca w blokach pełnego skupienia z blokadą social mediów.

- Ikona w zasobniku (tray) + skrót na pulpicie. Klik -> modal z licznikiem.
- START DNIA (raz dziennie) i ZAKOŃCZ DZIEŃ (raz dziennie -> raport AI na Telegram).
- Między nimi można dać PAUZĘ, ale trzeba PODAĆ POWÓD (zapisywany w bazie).
- Restart aplikacji NIE kasuje stanu dnia — jest wznawiany i logowany w bazie.
- W trybie PRACA blokuje social media i komunikatory (Telegram/WhatsApp) — strony
  i aplikacje. Dozwolone zawsze: Signal i YouTube.
- Okno można dowolnie powiększać/zmniejszać (skaluje czcionki).
- Dane w sqlite (deepfocus.db). Raport dnia/tygodnia/miesiąca analizuje Mistral
  i wysyła na Telegram (monospace).
"""

import os
import json
import time
import queue
import ctypes
import socket
import sqlite3
import threading
import datetime
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psutil
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image
import pystray

import integrations as ig

try:
    import uiautomation as auto
    auto.SetGlobalSearchTimeout(0.4)
    HAVE_UIA = True
except Exception:
    HAVE_UIA = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DB_PATH = os.path.join(BASE_DIR, "deepfocus.db")
ICON_PATH = os.path.join(BASE_DIR, "icon.png")
LOG_PATH = os.path.join(BASE_DIR, "deepfocus_log.txt")

POLL_SECONDS = 1.0
OVERLAY_SECONDS = 5
GAP_THRESHOLD = 90     # sekundy — powyzej tego przerwa w dzialaniu wymaga uzasadnienia
IDLE_LIMIT = 300       # sekundy bezczynnosci (5 min) -> nagabywanie do pracy
KILL_SCAN_EVERY = 3    # co ile sekund skanowac i zabijac zablokowane aplikacje
HISTORY_JSON = "history.json"

BG = "#0e1319"
CARD = "#141b24"
WORK_C = "#5ad1a0"
BREAK_C = "#ffb457"
PAUSE_C = "#8aa0b3"
TXT = "#ffffff"
SUB = "#8aa0b3"

BROWSER_PROCS = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
    "opera_gx.exe", "vivaldi.exe", "arc.exe", "chromium.exe", "librewolf.exe",
    "waterfox.exe", "yandex.exe",
}
ADDRESS_BAR_NAMES = [
    "Address and search bar", "Pasek adresu i wyszukiwania",
    "Adres i pasek wyszukiwania", "Search or enter address",
    "Address field", "Pasek adresu",
]

MODE_WORK = "WORK"
MODE_BREAK = "BREAK"
LAN_PORT = 8770          # port serwera stanu dla telefonu (ta sama siec WiFi)


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


def today_key():
    return datetime.date.today().isoformat()


def fmt_hms(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min"
    return f"{s} s"


def fmt_clock(seconds):
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Baza danych
# ---------------------------------------------------------------------------
class DB:
    def __init__(self, path):
        self.path = path
        self._exec("""CREATE TABLE IF NOT EXISTS days(
            date TEXT PRIMARY KEY, focus_seconds INTEGER DEFAULT 0,
            social_seconds INTEGER DEFAULT 0, blocks INTEGER DEFAULT 0,
            day_started TEXT, last_update TEXT)""")
        self._exec("""CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, date TEXT,
            type TEXT, reason TEXT, seconds INTEGER DEFAULT 0)""")
        self._exec("""CREATE TABLE IF NOT EXISTS state(
            date TEXT PRIMARY KEY, day_active INTEGER, paused INTEGER,
            day_ended INTEGER, mode TEXT, remaining INTEGER,
            day_start TEXT, last_update REAL)""")

    def _exec(self, sql, params=(), fetch=None):
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            cur = conn.execute(sql, params)
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            conn.commit()
        finally:
            conn.close()

    def get_day(self, date):
        r = self._exec("SELECT focus_seconds,social_seconds,blocks FROM days WHERE date=?",
                       (date,), fetch="one")
        return r or (0, 0, 0)

    def upsert_day(self, date, focus, social, blocks, started):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self._exec("""INSERT INTO days(date,focus_seconds,social_seconds,blocks,day_started,last_update)
                      VALUES(?,?,?,?,?,?)
                      ON CONFLICT(date) DO UPDATE SET focus_seconds=excluded.focus_seconds,
                        social_seconds=excluded.social_seconds, blocks=excluded.blocks,
                        last_update=excluded.last_update""",
                   (date, focus, social, blocks, started, now))

    def range_days(self, start, end):
        return self._exec("""SELECT date,focus_seconds,social_seconds,blocks FROM days
                             WHERE date>=? AND date<=? ORDER BY date""",
                          (start.isoformat(), end.isoformat()), fetch="all")

    def add_event(self, etype, reason="", seconds=0):
        self._exec("INSERT INTO events(ts,date,type,reason,seconds) VALUES(?,?,?,?,?)",
                   (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    today_key(), etype, reason, seconds))

    def range_events(self, start, end):
        return self._exec("""SELECT ts,date,type,reason,seconds FROM events
                             WHERE date>=? AND date<=? ORDER BY ts""",
                          (start.isoformat(), end.isoformat()), fetch="all")

    def save_state(self, s):
        self._exec("""INSERT INTO state(date,day_active,paused,day_ended,mode,remaining,day_start,last_update)
                      VALUES(?,?,?,?,?,?,?,?)
                      ON CONFLICT(date) DO UPDATE SET day_active=excluded.day_active,
                        paused=excluded.paused, day_ended=excluded.day_ended, mode=excluded.mode,
                        remaining=excluded.remaining, day_start=excluded.day_start,
                        last_update=excluded.last_update""",
                   (s["date"], s["day_active"], s["paused"], s["day_ended"], s["mode"],
                    s["remaining"], s["day_start"], s["last_update"]))

    def load_state(self, date):
        r = self._exec("""SELECT day_active,paused,day_ended,mode,remaining,day_start,last_update
                          FROM state WHERE date=?""", (date,), fetch="one")
        if not r:
            return None
        return {"day_active": r[0], "paused": r[1], "day_ended": r[2], "mode": r[3],
                "remaining": r[4], "day_start": r[5], "last_update": r[6]}


# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------
class Config:
    def __init__(self):
        d = {}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception as e:
            log(f"BLAD config.json: {e}")
        self.work_min = int(d.get("work_minutes", 45))
        self.break_min = int(d.get("break_minutes", 15))
        self.block = {x.strip().lower().lstrip(".") for x in d.get("block_domains", []) if x.strip()}
        self.allow = {x.strip().lower().lstrip(".") for x in d.get("allow_domains", []) if x.strip()}
        self.block_apps = {x.strip().lower() for x in d.get("block_apps", []) if x.strip()}
        self.kw = [k.strip().lower() for k in d.get("block_keywords", []) if k.strip()]


# ---------------------------------------------------------------------------
# Wykrywanie
# ---------------------------------------------------------------------------
def host_from(url):
    if not url:
        return ""
    u = url if "://" in url else "http://" + url
    try:
        h = urlparse(u).netloc.lower()
    except Exception:
        return ""
    if h.startswith("www."):
        h = h[4:]
    return h.split(":")[0]


def domain_in(host, dom_set):
    if not host or not dom_set:
        return None
    labels = host.split(".")
    for i in range(len(labels) - 1):
        cand = ".".join(labels[i:])
        if cand in dom_set:
            return cand
    return None


def get_foreground():
    if not HAVE_UIA:
        return None
    try:
        ctrl = auto.GetForegroundControl()
        if not ctrl:
            return None
        top = ctrl.GetTopLevelControl() or ctrl
        try:
            pname = psutil.Process(top.ProcessId).name().lower()
        except Exception:
            pname = ""
        info = {"proc": pname, "top": top, "url": "", "title": top.Name or ""}
        if pname in BROWSER_PROCS:
            try:
                for nm in ADDRESS_BAR_NAMES:
                    cand = top.EditControl(searchDepth=12, Name=nm)
                    if cand.Exists(0.2, 0.05):
                        info["url"] = (cand.GetValuePattern().Value or "").strip()
                        break
            except Exception:
                pass
        return info
    except Exception:
        return None


def is_social(cfg, url, title):
    host = host_from(url)
    if domain_in(host, cfg.allow):
        return None
    hit = domain_in(host, cfg.block)
    if hit:
        return hit
    text = f"{url} {title}".lower()
    for k in cfg.kw:
        if k in text:
            return k
    return None


def close_tab(top):
    try:
        top.SetActive(); time.sleep(0.05)
        top.SendKeys("{Ctrl}w", waitTime=0)
    except Exception as e:
        log(f"Nie zamknieto karty: {e}")


def minimize_window(top):
    try:
        top.GetWindowPattern().SetWindowVisualState(auto.WindowVisualState.Minimized)
    except Exception as e:
        log(f"Nie zminimalizowano: {e}")


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds():
    """Ile sekund minelo od ostatniej aktywnosci myszy/klawiatury."""
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0.0, millis / 1000.0)
    except Exception:
        pass
    return 0.0


def kill_blocked_apps(block_apps):
    """Zabija procesy zablokowanych aplikacji (Telegram, WhatsApp, Discord...).
    Dopasowanie po FRAGMENCIE nazwy (np. 'whatsapp' lapie WhatsApp.Root.exe).
    Zwraca liste zabitych nazw. Signal (dozwolony) nie jest na liscie."""
    killed = []
    if not block_apps:
        return killed
    stems = [s.lower().replace(".exe", "") for s in block_apps]
    for p in psutil.process_iter(["name", "pid"]):
        try:
            name = (p.info["name"] or "").lower()
            if not name or not any(stem in name for stem in stems):
                continue
            pid = p.info["pid"]
            try:
                p.kill()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                # aplikacje ze Store czasem wymagaja twardego taskkill z drzewem procesow
                os.system(f'taskkill /F /T /PID {pid} >nul 2>&1')
            killed.append(p.info["name"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            continue
    return killed


def monitor_loop(app):
    def body():
        last = {"key": "", "t": 0.0}
        last_scan = 0.0
        killed_notified = {}
        while not app.stop_ev.is_set():
            try:
                if app.mode == MODE_WORK and app.counting():
                    now = time.time()
                    # 1) zabij zablokowane aplikacje (Telegram, WhatsApp, Discord...)
                    if now - last_scan >= KILL_SCAN_EVERY:
                        last_scan = now
                        for name in kill_blocked_apps(app.cfg.block_apps):
                            log(f"ZABITO aplikacje [{name}]")
                            if now - killed_notified.get(name, 0) > 8:
                                killed_notified[name] = now
                                app.event_q.put(("killed", name))
                    # 2) przegladarka na social media -> zamknij karte
                    info = get_foreground()
                    if info and info["proc"] in BROWSER_PROCS:
                        hit = is_social(app.cfg, info["url"], info["title"])
                        if hit:
                            key = info["url"] or hit
                            if not (key == last["key"] and now - last["t"] < 4):
                                last = {"key": key, "t": now}
                                log(f"BLOK social [{hit}]")
                                close_tab(info["top"])
                                app.event_q.put(("block", hit))
            except Exception as e:
                log(f"Blad monitora: {e}")
            app.stop_ev.wait(POLL_SECONDS)

    if HAVE_UIA:
        with auto.UIAutomationInitializerInThread(debug=False):
            body()
    else:
        body()


# ---------------------------------------------------------------------------
# Serwer stanu w sieci LAN (dla aplikacji na telefonie)
# ---------------------------------------------------------------------------
class _StatusHandler(BaseHTTPRequestHandler):
    app = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/status"):
            try:
                self.app.last_phone_poll = time.time()
                self.app.phone_ip = self.client_address[0]
            except Exception:
                pass
            try:
                data = json.dumps(self.app.status_dict()).encode("utf-8")
            except Exception:
                data = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()


def start_status_server(app, port=LAN_PORT):
    _StatusHandler.app = app
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), _StatusHandler)
    except OSError as e:
        log(f"Serwer LAN nie wystartowal ({e})")
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"Serwer stanu LAN: http://{local_ip()}:{port}/status")
    return srv


# ---------------------------------------------------------------------------
# Aplikacja
# ---------------------------------------------------------------------------
class DeepFocusApp:
    def __init__(self):
        self.cfg = Config()
        self.db = DB(DB_PATH)
        self.mode = MODE_WORK
        self.remaining = self.cfg.work_min * 60
        self.day_active = False
        self.paused = False
        self.day_ended = False
        self.day_start = None
        self.pending_gap = None      # (from_ts, to_ts) do uzasadnienia
        self.focus_seconds = 0
        self.social_seconds = 0
        self.blocks = 0
        self.idle_seconds_today = 0
        self.idle_active = False
        self.idle_start = None
        self.last_nag = 0.0
        self.tick_count = 0
        self.stop_ev = threading.Event()
        self.event_q = queue.Queue()
        self.block_overlay = None
        self.last_phone_poll = 0.0    # kiedy telefon ostatnio pytal o stan
        self.phone_ip = ""
        self.pc_ip = local_ip()       # IP kompa do wpisania w telefonie

        f, s, b = self.db.get_day(today_key())
        self.focus_seconds, self.social_seconds, self.blocks = f, s, b
        self._restore_state()
        self.state_date = today_key()   # dzien kalendarzowy, do ktorego nalezy stan w pamieci

        self._build_ui()
        self._build_tray()
        self.db.add_event("relaunch", reason="uruchomienie aplikacji")
        log("=== Deep Focus Now start ===")

    def counting(self):
        return self.day_active and not self.paused and not self.day_ended

    # ---------------- przywrocenie stanu ----------------
    def _restore_state(self):
        st = self.db.load_state(today_key())
        if not st:
            return
        self.mode = st["mode"] or MODE_WORK
        self.remaining = int(st["remaining"] or self.cfg.work_min * 60)
        self.day_start = st["day_start"]
        self.day_ended = bool(st["day_ended"])
        if st["day_active"] and not self.day_ended:
            self.day_active = True
            # aplikacja byla wylaczona -> traktuj jako przerwe do uzasadnienia
            gap = time.time() - (st["last_update"] or time.time())
            if not st["paused"] and gap > GAP_THRESHOLD:
                self.paused = True
                self.pending_gap = (st["last_update"], time.time())
                log(f"Wznowienie dnia po przerwie {int(gap)}s — wymagane uzasadnienie")
            else:
                self.paused = bool(st["paused"])
        elif self.day_ended:
            self.day_active = True  # dzien byl, ale zakonczony

    # ---------------- UI ----------------
    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("Deep Focus Now")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.97)
        except Exception:
            pass
        self.BW, self.BH = 340, 300           # bazowy rozmiar
        self.W, self.H = self.BW, self.BH
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"{self.W}x{self.H}+{sw - self.W - 24}+30")

        # czcionki (skalowalne)
        self.f_title = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self.f_mode = tkfont.Font(family="Segoe UI", size=13, weight="bold")
        self.f_time = tkfont.Font(family="Consolas", size=44, weight="bold")
        self.f_stat = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_btn = tkfont.Font(family="Segoe UI", size=11, weight="bold")

        self.card = tk.Frame(self.root, bg=CARD, highlightthickness=2,
                             highlightbackground=WORK_C, highlightcolor=WORK_C)
        self.card.pack(fill="both", expand=True)

        bar = tk.Frame(self.card, bg=CARD)
        bar.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(bar, text="◎ Deep Focus Now", bg=CARD, fg=SUB, font=self.f_title).pack(side="left")
        hide = tk.Label(bar, text="—", bg=CARD, fg=SUB, font=self.f_title, cursor="hand2")
        hide.pack(side="right")
        hide.bind("<Button-1>", lambda e: self.hide_window())

        self.mode_lbl = tk.Label(self.card, text="GOTOWY DO PRACY", bg=CARD, fg=WORK_C, font=self.f_mode)
        self.mode_lbl.pack(pady=(10, 0))
        self.time_lbl = tk.Label(self.card, text=fmt_clock(self.cfg.work_min * 60),
                                 bg=CARD, fg=TXT, font=self.f_time)
        self.time_lbl.pack()
        self.bar_canvas = tk.Canvas(self.card, height=6, bg="#202934", highlightthickness=0)
        self.bar_canvas.pack(fill="x", padx=20, pady=(2, 8))

        stats = tk.Frame(self.card, bg=CARD)
        stats.pack()
        self.focus_lbl = tk.Label(stats, text="Praca: 0 min", bg=CARD, fg=WORK_C, font=self.f_stat)
        self.focus_lbl.grid(row=0, column=0, padx=10)
        self.social_lbl = tk.Label(stats, text="Sociale: 0 min", bg=CARD, fg=BREAK_C, font=self.f_stat)
        self.social_lbl.grid(row=0, column=1, padx=10)

        self.phone_lbl = tk.Label(self.card, text="", bg=CARD, fg=SUB,
                                  font=("Segoe UI", 9), justify="center")
        self.phone_lbl.pack(pady=(6, 0))

        self.btns = tk.Frame(self.card, bg=CARD)
        self.btns.pack(pady=(10, 4))
        self.start_btn = tk.Button(self.btns, text="▶  START DNIA", command=self.start_day,
                                   bg=WORK_C, fg="#08130d", relief="flat", font=self.f_btn,
                                   padx=16, pady=6, activebackground="#74e3b6", cursor="hand2")
        self.pause_btn = tk.Button(self.btns, text="⏸ PAUZA", command=self.pause_day,
                                   bg="#26313d", fg="#cfe3f2", relief="flat", font=self.f_btn,
                                   padx=12, pady=5, activebackground="#33414f", cursor="hand2")
        self.resume_btn = tk.Button(self.btns, text="▶ PONÓW", command=self.resume_day,
                                    bg=WORK_C, fg="#08130d", relief="flat", font=self.f_btn,
                                    padx=12, pady=5, activebackground="#74e3b6", cursor="hand2")
        self.stop_btn = tk.Button(self.btns, text="■ ZAKOŃCZ DZIEŃ", command=self.stop_day,
                                  bg="#3a1f24", fg="#ff9a9a", relief="flat", font=self.f_btn,
                                  padx=12, pady=5, activebackground="#57282f", cursor="hand2")

        rep = tk.Frame(self.card, bg=CARD)
        rep.pack()
        for txt, sc in (("Dzień", "day"), ("Tydzień", "week"), ("Miesiąc", "month"), ("Rok", "year")):
            tk.Button(rep, text=txt, command=lambda s=sc: self.ai_report(s),
                      bg=CARD, fg=SUB, relief="flat", font=("Segoe UI", 8),
                      activebackground=CARD, cursor="hand2").pack(side="left", padx=5)

        # uchwyt zmiany rozmiaru (prawy dolny rog)
        grip = tk.Label(self.card, text="◢", bg=CARD, fg=SUB, cursor="bottom_right_corner")
        grip.place(relx=1.0, rely=1.0, anchor="se")
        grip.bind("<Button-1>", self._resize_start)
        grip.bind("<B1-Motion>", self._resize_move)

        for wgt in (self.card, self.mode_lbl, self.time_lbl):
            wgt.bind("<Button-1>", self._drag_start)
            wgt.bind("<B1-Motion>", self._drag_move)

        self.root.bind("<Configure>", self._on_configure)
        self._render_state()

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root, e.y_root
        self._ox, self._oy = self.root.winfo_x(), self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{self._ox + (e.x_root - self._dx)}+{self._oy + (e.y_root - self._dy)}")

    def _resize_start(self, e):
        self._rx, self._ry = e.x_root, e.y_root
        self._rw, self._rh = self.root.winfo_width(), self.root.winfo_height()

    def _resize_move(self, e):
        w = max(240, self._rw + (e.x_root - self._rx))
        h = max(210, self._rh + (e.y_root - self._ry))
        self.root.geometry(f"{w}x{h}")

    def _on_configure(self, e):
        if e.widget is not self.root:
            return
        scale = min(e.width / self.BW, e.height / self.BH)
        scale = max(0.7, min(scale, 3.2))
        self.f_time.configure(size=int(44 * scale))
        self.f_mode.configure(size=int(13 * scale))
        self.f_stat.configure(size=int(10 * scale))
        self.f_btn.configure(size=int(11 * scale))
        self.f_title.configure(size=int(9 * scale))
        self._refresh_labels()

    def _accent(self):
        if self.paused:
            return PAUSE_C
        return WORK_C if self.mode == MODE_WORK else BREAK_C

    def _render_state(self):
        for b in (self.start_btn, self.pause_btn, self.resume_btn, self.stop_btn):
            b.pack_forget()
        if self.day_ended:
            self.mode_lbl.config(text="DZIEŃ ZAKOŃCZONY", fg=SUB)
            self.card.config(highlightbackground=SUB, highlightcolor=SUB)
        elif not self.day_active:
            self.start_btn.pack()
            self.mode_lbl.config(text="GOTOWY DO PRACY", fg=WORK_C)
            self.card.config(highlightbackground=WORK_C, highlightcolor=WORK_C)
        else:
            if self.paused:
                self.resume_btn.pack(side="left", padx=4)
                self.mode_lbl.config(text="PAUZA", fg=PAUSE_C)
            else:
                self.pause_btn.pack(side="left", padx=4)
                self.mode_lbl.config(
                    text="DEEP FOCUS — PRACA" if self.mode == MODE_WORK else "PRZERWA — CZAS SOCIALI",
                    fg=self._accent())
            self.stop_btn.pack(side="left", padx=4)
            self.card.config(highlightbackground=self._accent(), highlightcolor=self._accent())
        self._refresh_labels()

    def _refresh_labels(self):
        self.time_lbl.config(text=fmt_clock(self.remaining))
        self.focus_lbl.config(text=f"Praca: {fmt_hms(self.focus_seconds)}")
        self.social_lbl.config(text=f"Sociale: {fmt_hms(self.social_seconds)}")
        total = (self.cfg.work_min if self.mode == MODE_WORK else self.cfg.break_min) * 60
        frac = 1 - (self.remaining / total) if total else 0
        self.bar_canvas.delete("all")
        w = self.bar_canvas.winfo_width() or (self.W - 40)
        self.bar_canvas.create_rectangle(0, 0, w, 6, fill="#202934", outline="")
        self.bar_canvas.create_rectangle(0, 0, int(w * max(0, min(frac, 1))), 6,
                                         fill=self._accent(), outline="")

    # ---------------- tray ----------------
    def _build_tray(self):
        try:
            image = Image.open(ICON_PATH)
        except Exception:
            image = Image.new("RGB", (64, 64), (16, 21, 28))
        menu = pystray.Menu(
            pystray.MenuItem("Pokaż okno", lambda: self.root.after(0, self.show_window), default=True),
            pystray.MenuItem("Start dnia", lambda: self.root.after(0, self.start_day)),
            pystray.MenuItem("Pauza", lambda: self.root.after(0, self.pause_day)),
            pystray.MenuItem("Ponów", lambda: self.root.after(0, self.resume_day)),
            pystray.MenuItem("Zakończ dzień", lambda: self.root.after(0, self.stop_day)),
            pystray.MenuItem("Raport dnia (AI)", lambda: self.root.after(0, lambda: self.ai_report("day"))),
            pystray.MenuItem("Zamknij program", lambda: self.root.after(0, self.quit)),
        )
        self.tray = pystray.Icon("deepfocus", image, "Deep Focus Now", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def show_window(self):
        self.root.deiconify(); self.root.attributes("-topmost", True); self.root.lift()

    def hide_window(self):
        self.root.withdraw()

    # ---------------- dialog powodu ----------------
    def ask_reason(self, title, prompt):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        ww, wh = 460, 190
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        win.geometry(f"{ww}x{wh}+{(sw-ww)//2}+{(sh-wh)//2}")
        tk.Label(win, text=title, bg=BG, fg=BREAK_C, font=("Segoe UI", 14, "bold")).pack(pady=(16, 2))
        tk.Label(win, text=prompt, bg=BG, fg=SUB, font=("Segoe UI", 10), wraplength=420).pack()
        var = tk.StringVar()
        ent = tk.Entry(win, textvariable=var, bg=CARD, fg=TXT, insertbackground=TXT,
                       relief="flat", font=("Segoe UI", 12), width=40)
        ent.pack(pady=12, ipady=5)
        ent.focus_set()
        result = {"val": None}

        def ok(_=None):
            v = var.get().strip()
            if not v:
                ent.config(bg="#3a1f24"); return
            result["val"] = v
            win.destroy()

        ent.bind("<Return>", ok)
        tk.Button(win, text="Zatwierdź", command=ok, bg=WORK_C, fg="#08130d", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=14, pady=5, cursor="hand2").pack()
        win.grab_set()
        self.root.wait_window(win)
        return result["val"]

    # ---------------- logika dnia ----------------
    def start_day(self):
        if self.day_ended:
            self._toast("Dzień już zakończony — start możliwy raz dziennie.")
            return
        if self.day_active:
            self.show_window(); return
        self.day_active = True
        self.paused = False
        self.mode = MODE_WORK
        self.remaining = self.cfg.work_min * 60
        self.day_start = datetime.datetime.now().isoformat(timespec="seconds")
        self.db.add_event("start", reason="start dnia pracy")
        log("START dnia")
        self._notify("DEEP FOCUS", f"Zaczynasz. {self.cfg.work_min} min pełnego skupienia.", WORK_C)
        self._render_state(); self._persist()

    def pause_day(self):
        if not self.counting():
            return
        reason = self.ask_reason("Dlaczego pauza?",
                                 "Musisz uzasadnić przerwę (np. wyjazd, telefon). Bez powodu nie ma pauzy.")
        if not reason:
            return
        self.paused = True
        self.db.add_event("pause", reason=reason)
        log(f"PAUZA — {reason}")
        self._render_state(); self._persist()

    def resume_day(self):
        if not self.day_active or self.day_ended or not self.paused:
            return
        if self.pending_gap:
            frm, to = self.pending_gap
            gap = int((to or time.time()) - (frm or to))
            reason = self.ask_reason("Aplikacja była wyłączona",
                                     f"Przerwa ok. {fmt_hms(gap)}. Podaj powód, aby wznowić dzień.")
            if not reason:
                return
            self.db.add_event("gap", reason=reason, seconds=gap)
            self.pending_gap = None
            log(f"GAP {gap}s — {reason}")
        else:
            self.db.add_event("resume", reason="wznowienie pracy")
        self.paused = False
        log("PONÓW")
        self._render_state(); self._persist()

    def stop_day(self):
        if not self.day_active or self.day_ended:
            self.ai_report("day"); return
        self.day_ended = True
        self.paused = False
        self.db.add_event("stop", reason="zakonczenie dnia pracy")
        self._persist()
        log(f"ZAKOŃCZ dnia — praca {fmt_hms(self.focus_seconds)}, bloki {self.blocks}")
        self._render_state()
        self._notify("DZIEŃ ZAKOŃCZONY", "Generuję raport i wysyłam na Telegram…", SUB)
        self.ai_report("day", auto=True)

    def _check_new_day(self):
        """Wykrywa realnie nowy dzien kalendarzowy i pozwala zaczac go od nowa.
        Wczorajsze dane sa juz zapisane w bazie pod swoja data."""
        tk = today_key()
        if tk == self.state_date:
            return
        log(f"NOWY DZIEN kalendarzowy: {tk} (poprzedni: {self.state_date})")
        self.state_date = tk
        # zeruj dzienne liczniki na nowy dzien
        self.focus_seconds = 0
        self.social_seconds = 0
        self.blocks = 0
        self.idle_seconds_today = 0
        self.idle_active = False
        self.db.add_event("new_day", reason="nowy dzien kalendarzowy")
        if self.day_ended or not self.day_active:
            # wczorajszy dzien zakonczony/niezaczety -> odblokuj nowy START
            self.day_active = False
            self.day_ended = False
            self.paused = False
            self.pending_gap = None
            self.mode = MODE_WORK
            self.remaining = self.cfg.work_min * 60
            self._notify("NOWY DZIEŃ", "Możesz zacząć nowy dzień pracy — naciśnij START DNIA.", WORK_C)
        self._persist()
        self._render_state()

    def tick(self):
        self._check_new_day()
        if self.counting():
            if self.mode == MODE_WORK:
                self._handle_idle()
                if not self.idle_active:
                    self.focus_seconds += 1   # liczymy tylko realna prace (nie bezczynnosc)
                else:
                    self.idle_seconds_today += 1
            else:
                self.social_seconds += 1
            self.remaining -= 1
            if self.remaining <= 0:
                self._switch_mode()
            self.tick_count += 1
            if self.tick_count % 5 == 0:
                self._persist()
        self._refresh_labels()
        self._refresh_phone()
        self.root.after(1000, self.tick)

    def _refresh_phone(self):
        connected = (time.time() - self.last_phone_poll) < 15
        if connected:
            self.phone_lbl.config(
                text=f"📱 Telefon: POŁĄCZONY  ●  ({self.phone_ip})", fg=WORK_C)
        else:
            self.phone_lbl.config(
                text=f"📱 Telefon: brak  ○  wpisz w apce:  {self.pc_ip}:{LAN_PORT}", fg=SUB)

    def _handle_idle(self):
        idle = idle_seconds()
        now = time.time()
        if idle >= IDLE_LIMIT:
            if not self.idle_active:
                self.idle_active = True
                self.idle_start = now - idle
                self.db.add_event("idle", reason="wykryto bezczynnosc")
                log(f"BEZCZYNNOSC wykryta ({int(idle)}s)")
            # nagabywanie co IDLE_LIMIT sekund
            if now - self.last_nag > IDLE_LIMIT:
                self.last_nag = now
                mins = int(idle // 60)
                self._notify("WRACAJ DO PRACY!",
                             f"Wykrywam nieaktywność {mins} min. Czas leci — wróć do deep focus.",
                             BREAK_C)
        else:
            if self.idle_active:
                self.idle_active = False
                log("Powrot z bezczynnosci")

    def _switch_mode(self):
        if self.mode == MODE_WORK:
            self.blocks += 1
            self.mode = MODE_BREAK
            self.remaining = self.cfg.break_min * 60
            self._notify("CZAS PRACY SIĘ SKOŃCZYŁ",
                         f"Zaczynasz CZAS SOCIALI — {self.cfg.break_min} min przerwy.", BREAK_C)
        else:
            self.mode = MODE_WORK
            self.remaining = self.cfg.work_min * 60
            self._notify("KONIEC PRZERWY",
                         f"Wracasz do pracy — {self.cfg.work_min} min. Sociale zablokowane.", WORK_C)
        self._render_state(); self._persist()

    # ---------------- powiadomienia / overlay ----------------
    def _toast(self, text):
        self._notify("Deep Focus", text, SUB)

    def _notify(self, title, subtitle, color):
        try:
            self.root.bell()
        except Exception:
            pass
        w = tk.Toplevel(self.root)
        w.overrideredirect(True); w.attributes("-topmost", True)
        try:
            w.attributes("-alpha", 0.98)
        except Exception:
            pass
        ww, wh = 560, 200
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w.geometry(f"{ww}x{wh}+{(sw-ww)//2}+{(sh-wh)//3}")
        w.configure(bg=color)
        inner = tk.Frame(w, bg=color); inner.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(inner, text=title, bg=color, fg="#0b0f14", font=("Segoe UI", 25, "bold"),
                 wraplength=520, justify="center").pack(pady=(0, 8))
        tk.Label(inner, text=subtitle, bg=color, fg="#0b0f14", font=("Segoe UI", 13),
                 wraplength=520, justify="center").pack()
        w.after(3800, w.destroy)

    def show_block(self, matched):
        try:
            if self.block_overlay and tk.Toplevel.winfo_exists(self.block_overlay):
                self.block_overlay.destroy()
        except Exception:
            pass
        w = tk.Toplevel(self.root)
        self.block_overlay = w
        w.attributes("-fullscreen", True); w.attributes("-topmost", True)
        w.configure(bg="#0f2436")
        fr = tk.Frame(w, bg="#0f2436"); fr.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(fr, text="🎯", font=("Segoe UI Emoji", 84), bg="#0f2436", fg="#fff").pack()
        tk.Label(fr, text="DEEP FOCUS", font=("Segoe UI", 50, "bold"), bg="#0f2436", fg=WORK_C).pack()
        tk.Label(fr, text="Social media zablokowane. Wróć do pracy.", font=("Segoe UI", 22),
                 bg="#0f2436", fg="#cfe3f2").pack(pady=(12, 4))
        tk.Label(fr, text=f"Do przerwy: {fmt_clock(self.remaining)}   ·   zablokowano: {matched}",
                 font=("Consolas", 14), bg="#0f2436", fg="#7fa8c4").pack(pady=(6, 0))
        w.bind("<Escape>", lambda e: w.destroy())
        w.after(OVERLAY_SECONDS * 1000, w.destroy)
        try:
            w.focus_force()
        except Exception:
            pass

    def pump(self):
        try:
            while True:
                kind, payload = self.event_q.get_nowait()
                if kind == "block":
                    self.show_block(payload)
                elif kind == "toast":
                    self._toast(payload)
                elif kind == "killed":
                    self._notify("APLIKACJA ZAMKNIĘTA",
                                 f"„{payload}” jest zablokowana w Deep Focus. Wróć do pracy.", WORK_C)
        except queue.Empty:
            pass
        self.root.after(200, self.pump)

    # ---------------- zapis / raporty ----------------
    def _persist(self):
        started = self.day_start.split("T")[1] if self.day_start and "T" in self.day_start else ""
        self.db.upsert_day(today_key(), int(self.focus_seconds), int(self.social_seconds),
                           int(self.blocks), started)
        self.db.save_state({
            "date": today_key(), "day_active": int(self.day_active), "paused": int(self.paused),
            "day_ended": int(self.day_ended), "mode": self.mode, "remaining": int(self.remaining),
            "day_start": self.day_start or "", "last_update": time.time(),
        })
        if self.tick_count % 30 == 0 or self.day_ended:
            self.export_json()

    def export_json(self):
        """Zapisuje historie do history.json: dni + sumy tydzien/miesiac/rok."""
        try:
            today = datetime.date.today()
            year_start = today.replace(month=1, day=1)
            rows = self.db.range_days(year_start, today)
            days = {r[0]: {"praca_s": r[1], "sociale_s": r[2], "bloki": r[3],
                           "praca": fmt_hms(r[1])} for r in rows}

            def total(start):
                return sum(r[1] for r in rows if r[0] >= start.isoformat())
            wk = today - datetime.timedelta(days=today.weekday())
            data = {
                "aktualizacja": datetime.datetime.now().isoformat(timespec="seconds"),
                "dzis": {"data": today.isoformat(), "praca_s": int(self.focus_seconds),
                         "sociale_s": int(self.social_seconds), "bezczynnosc_s": int(self.idle_seconds_today),
                         "bloki": int(self.blocks), "praca": fmt_hms(self.focus_seconds)},
                "sumy": {"tydzien": fmt_hms(total(wk)),
                         "miesiac": fmt_hms(total(today.replace(day=1))),
                         "rok": fmt_hms(total(year_start))},
                "dni": days,
            }
            with open(os.path.join(BASE_DIR, HISTORY_JSON), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log(f"Blad export_json: {e}")

    def _build_stats(self, scope):
        today = datetime.date.today()
        if scope == "week":
            start = today - datetime.timedelta(days=today.weekday())
        elif scope == "month":
            start = today.replace(day=1)
        elif scope == "year":
            start = today.replace(month=1, day=1)
        else:
            start = today
        days = self.db.range_days(start, today)
        evs = self.db.range_events(start, today)
        pauzy = [{"godzina": e[0][11:16], "typ": e[2], "powod": e[3],
                  "ile": fmt_hms(e[4]) if e[4] else ""}
                 for e in evs if e[2] in ("pause", "gap")]
        per_day = [{"data": d[0], "praca": fmt_hms(d[1]), "sociale": fmt_hms(d[2]), "bloki": d[3]}
                   for d in days]
        tot_f = sum(d[1] for d in days)
        tot_s = sum(d[2] for d in days)
        tot_b = sum(d[3] for d in days)
        # poprzedni okres dla porownania (dla dnia: 7 dni wstecz)
        prev_start = start - (today - start) - datetime.timedelta(days=1)
        if scope == "day":
            prev_start = today - datetime.timedelta(days=7)
        prev = self.db.range_days(prev_start, start - datetime.timedelta(days=1))
        idle_evs = [e for e in evs if e[2] == "idle"]
        return {
            "zakres": scope,
            "okres": f"{start.isoformat()}..{today.isoformat()}",
            "suma_praca": fmt_hms(tot_f), "suma_sociale": fmt_hms(tot_s),
            "ukonczone_bloki": tot_b,
            "bezczynnosc_dzis": fmt_hms(self.idle_seconds_today),
            "liczba_wykrytych_bezczynnosci": len(idle_evs),
            "dni": per_day,
            "przerwy_z_powodami": pauzy,
            "poprzedni_okres": [{"data": d[0], "praca": fmt_hms(d[1])} for d in prev],
        }

    def ai_report(self, scope, auto=False):
        stats = self._build_stats(scope)
        self._toast("Analizuję dzień i wysyłam raport na Telegram…" if scope == "day"
                    else f"Generuję raport ({scope}) i wysyłam na Telegram…")

        def work():
            try:
                title, text = ig.build_report(scope, stats)
                ok, info = ig.telegram_send_mono(text, title=title)
                msg = "Raport AI wysłany na Telegram ✓" if ok else f"Nie wysłano: {info}"
                log(f"Raport {scope}: {msg}")
            except Exception as e:
                msg = f"Błąd raportu AI: {e}"
                log(msg)
            self.event_q.put(("toast", msg))

        threading.Thread(target=work, daemon=True).start()

    def quit(self):
        self.stop_ev.set()
        self._persist()
        try:
            self.tray.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def status_dict(self):
        active = self.day_active and not self.day_ended
        focus_mode = bool(active and not self.paused and self.mode == MODE_WORK)
        return {
            "app": "deep-focus-now", "version": 1,
            "day_active": bool(active), "day_ended": bool(self.day_ended),
            "paused": bool(self.paused), "mode": self.mode,
            "focus": focus_mode,                # czy telefon ma blokowac
            "remaining": int(self.remaining),
            "work_min": self.cfg.work_min, "break_min": self.cfg.break_min,
            "focus_seconds": int(self.focus_seconds),
            "social_seconds": int(self.social_seconds),
            "date": today_key(), "ts": time.time(),
        }

    def run(self):
        self.status_srv = start_status_server(self)
        threading.Thread(target=monitor_loop, args=(self,), daemon=True).start()
        self.root.after(1000, self.tick)
        self.root.after(200, self.pump)
        self.root.after(120, self._refresh_labels)
        if self.pending_gap:
            self.root.after(600, self.show_window)
        try:
            self.root.mainloop()
        finally:
            self.stop_ev.set()
            self._persist()
            log("=== Deep Focus Now stop ===")


def main():
    DeepFocusApp().run()


if __name__ == "__main__":
    main()
