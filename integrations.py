# -*- coding: utf-8 -*-
"""
Integracje Deep Focus Now: Mistral (analiza) + Telegram (wysylka raportu).
Konfiguracja z pliku .env obok tego skryptu.
"""
import os
import json
import html
import datetime
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE, ".env")
CHAT_CACHE = os.path.join(BASE, "telegram_chat.json")


def load_env():
    env = {}
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


ENV = load_env()


def _http(url, data=None, timeout=60):
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


# ---------------------------------------------------------------------------
# Mistral
# ---------------------------------------------------------------------------
def mistral_chat(prompt, system=None, model=None, max_tokens=900, timeout=90):
    base = ENV.get("MISTRAL_BASE_URL", "https://api.mistral.ai/v1").rstrip("/")
    key = ENV.get("MISTRAL_API_KEY", "")
    model = model or ENV.get("MISTRAL_MODEL_SMART", "mistral-small-latest")
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps({"model": model, "messages": msgs, "max_tokens": max_tokens,
                         "temperature": 0.4}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8", "ignore"))
    return d["choices"][0]["message"]["content"].strip()


def mistral_dev(prompt, system=None, max_tokens=1200, timeout=120):
    """Generowanie przez model dev (kod / zadania w aplikacji)."""
    return mistral_chat(prompt, system=system,
                        model=ENV.get("MISTRAL_MODEL_DEV", "devstral-medium-latest"),
                        max_tokens=max_tokens, timeout=timeout)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
def _token():
    return ENV.get("TELEGRAM_API", "")


def resolve_chat_id():
    """Zwraca chat_id dla ALLOWED_USERNAME. Cache w telegram_chat.json."""
    try:
        with open(CHAT_CACHE, "r", encoding="utf-8") as f:
            cid = json.load(f).get("chat_id")
            if cid:
                return cid
    except Exception:
        pass
    allowed = ENV.get("ALLOWED_USERNAME", "").lstrip("@").lower()
    try:
        d = _http(f"https://api.telegram.org/bot{_token()}/getUpdates")
    except Exception:
        return None
    if not d.get("ok"):
        return None
    for u in d.get("result", []):
        msg = u.get("message") or u.get("edited_message") or {}
        frm = msg.get("from", {})
        if (frm.get("username") or "").lower() == allowed:
            cid = msg.get("chat", {}).get("id")
            if cid:
                try:
                    with open(CHAT_CACHE, "w", encoding="utf-8") as f:
                        json.dump({"chat_id": cid, "username": allowed}, f)
                except Exception:
                    pass
                return cid
    return None


def telegram_send_mono(text, title=None):
    """Wysyla wiadomosc monospace (blok <pre>) do uzytkownika szansky."""
    cid = resolve_chat_id()
    if not cid:
        return False, "Brak chat_id - napisz /start do bota z konta szansky."
    body = html.escape(text)
    payload = f"<pre>{body}</pre>"
    if title:
        payload = f"<b>{html.escape(title)}</b>\n" + payload
    try:
        d = _http(f"https://api.telegram.org/bot{_token()}/sendMessage",
                  {"chat_id": cid, "text": payload, "parse_mode": "HTML",
                   "disable_web_page_preview": True})
        return bool(d.get("ok")), ("wyslano" if d.get("ok") else str(d))
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Budowa promptu i raportu
# ---------------------------------------------------------------------------
def fmt_hm(sec):
    sec = int(sec); h, m = divmod(sec // 60, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def build_report(scope, stats):
    """stats: dict z danymi. Zwraca (tytul, tekst_raportu) - analiza z Mistrala."""
    system = (
        "Jestes trenerem produktywnosci. Analizujesz dane pracy w pelnym skupieniu "
        "(deep focus) uzytkownika. Piszesz po polsku, zwiezle, konkretnie i motywujaco, "
        "bez lania wody. Zwracasz sam tekst raportu (bez markdown), gotowy do pokazania "
        "w bloku monospace. Uzyj krotkich linii (max ~52 znaki), naglowkow wielkimi "
        "literami i myslnikow. Na koncu daj PUENTE: czy pracowal duzo czy malo i jedna "
        "rade na jutro."
    )
    prompt = (
        f"Zakres raportu: {scope}.\n"
        f"Dane (JSON):\n{json.dumps(stats, ensure_ascii=False, indent=2)}\n\n"
        "Napisz analize: ile realnie pracowal w skupieniu, jak wypada na tle poprzednich "
        "dni/okresow, skomentuj przerwy i ich powody (czy uzasadnione), oceń dyscypline. "
        "Dodaj porownanie liczbowe. Zakoncz sekcja PUENTA."
    )
    model = ENV.get("MISTRAL_MODEL_SMART", "mistral-small-latest")
    text = mistral_chat(prompt, system=system, model=model, max_tokens=900)
    titles = {"day": "Raport dnia — Deep Focus", "week": "Raport tygodnia — Deep Focus",
              "month": "Raport miesiaca — Deep Focus", "year": "Raport roku — Deep Focus"}
    return titles.get(scope, "Raport — Deep Focus"), text


if __name__ == "__main__":
    # szybki test
    print("chat_id:", resolve_chat_id())
    ok, info = telegram_send_mono("Deep Focus Now — test polaczenia.\nDziala.", title="Test")
    print("telegram:", ok, info)
