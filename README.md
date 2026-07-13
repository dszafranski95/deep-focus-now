# Deep Focus Now 🎯

Praca w blokach pełnego skupienia z automatyczną blokadą social mediów i
komunikatorów na całym komputerze. Na koniec dnia **Mistral analizuje Twoją pracę
i wysyła raport na Telegram**.

## Zasady

- **Dozwolone zawsze:** Signal i YouTube. **Blokowane w trybie PRACA:** wszystkie
  social media (Reddit, X, LinkedIn, Instagram, TikTok, Facebook…) ORAZ komunikatory
  **Telegram i WhatsApp** — jako strony i jako aplikacje desktop.
- Cykl: PRACA 45 min → PRZERWA / „czas sociali" 15 min → PRACA → …
- **START DNIA** i **ZAKOŃCZ DZIEŃ** — raz dziennie (Ty naciskasz).
- Między nimi możesz dać **PAUZĘ**, ale **musisz podać powód** (np. wyjazd) — powód
  jest zapisywany w bazie i trafia do analizy. Bez powodu nie ma pauzy.
- **Auto-zamykanie aplikacji:** gdy w trybie PRACA wykryje uruchomiony Telegram,
  WhatsApp, Discord itd., **automatycznie je zabija** (co 3 s), informuje o tym i nie
  pozwala ich trzymać otwartych.
- **Wykrywanie bezczynności:** brak ruchu myszy/klawiatury > 5 min → komunikat
  „WRACAJ DO PRACY! wykrywam nieaktywność" (i ten czas nie jest liczony jako praca).
- **Restart aplikacji nie kasuje stanu dnia** — jest wznawiany. Jeśli apka była
  wyłączona dłużej niż ~1,5 min, przy wznowieniu musisz uzasadnić tę przerwę.
- **Historia w JSON** (`history.json`): każdy dzień + sumy tydzień/miesiąc/rok, obok
  bazy `deepfocus.db`. Raporty AI: dzień / tydzień / miesiąc / **rok**.
- Okno w rogu można **dowolnie powiększać/zmniejszać** (uchwyt ◢ w rogu, czcionki
  się skalują) i przeciągać. Klik w ikonę w zasobniku (tray) pokazuje/chowa okno.

## Raport AI na Telegram

Po **ZAKOŃCZ DZIEŃ** dane dnia (czas pracy, sociale, bloki, przerwy z powodami,
porównanie do poprzednich dni) idą do Mistrala, który pisze analizę i **puentę**
(dużo/mało pracy, jak wypadł dzień, rada na jutro). Raport przychodzi na Twój
Telegram jako blok **monospace**. Przyciski „Dzień / Tydzień AI / Miesiąc AI"
(oraz menu tray) generują raporty dla wybranego okresu.

Konfiguracja integracji jest w pliku `.env` (token bota Telegram, klucz Mistral,
model). Bot pisze tylko do użytkownika `szansky`.

## Uruchomienie

Dwuklik ikony **Deep Focus Now** na pulpicie, albo `wscript run_deepfocus.vbs`.
Naciskasz **START DNIA**, gdy zaczynasz. Na koniec **ZAKOŃCZ DZIEŃ** → raport.

## Dostosowanie

```powershell
python add_block.py tiktok.com            # dodaj stronę do blokady
python add_block.py --remove reddit.com   # przestań blokować
python add_block.py --work 50 --break 10  # zmień długości (minuty)
```
Aplikacje desktop do blokowania: `block_apps` w `config.json`. Dozwolone: `allow_domains`.

## Pliki

| Plik | Rola |
|------|------|
| `deepfocus.py` | aplikacja (tray, modal, cykl, blokada, pauzy z powodem, raporty) |
| `integrations.py` | Mistral (analiza) + Telegram (wysyłka raportu) |
| `.env` | klucze: Telegram, Mistral, model |
| `config.json` | listy blokad/dozwolonych, czasy, aplikacje |
| `deepfocus.db` | baza sqlite: `days`, `events` (pauzy/powody), `state` (wznawianie) |
| `add_block.py` | szybkie zmiany konfiguracji |
| `icon.ico` / `icon.png` | ikona pulpitu i zasobnika |
| `run_deepfocus.vbs` / `make_shortcut.vbs` | start bez konsoli / skrót na pulpicie |

## Bezpieczeństwo

`.env` i `telegram_chat.json` zawierają Twoje sekrety i identyfikator czatu —
trzymaj ten folder prywatnie. Jeśli token bota wyciekł, wygeneruj nowy u @BotFather
i podmień w `.env`.
