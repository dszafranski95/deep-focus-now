# Deep Focus Now — aplikacja na telefon (Android)

Towarzysz apki na kompie. Gdy na kompie trwa **Deep Focus (praca)**, telefon:
- pokazuje **ten sam licznik** (zsynchronizowany z kompem, powiadomienie na stałe),
- **wyrzuca Cię z zablokowanych aplikacji** (Instagram, TikTok, WhatsApp, Telegram,
  Facebook, Messenger, X, Reddit, Snapchat, LinkedIn, Discord…) i pokazuje „wróć do pracy".
- **YouTube i Signal są dozwolone** (jak na kompie).

Działa w **tej samej sieci WiFi** co komp.

## Instalacja (bez Android Studio)

1. Na komputerze uruchom apkę Deep Focus Now (`run_deepfocus.vbs`). W logu
   (`deepfocus_log.txt`) zobaczysz linię: `Serwer stanu LAN: http://192.168.x.x:8770/status`
   — zapamiętaj to IP i port.
2. Na telefonie wejdź na stronę **Releases** repozytorium:
   `https://github.com/dszafranski95/deep-focus-now/releases` i pobierz plik
   **deep-focus-now.apk** (z wydania „apk-latest").
3. Otwórz pobrany plik, zezwól na „instalację z nieznanych źródeł", zainstaluj.
4. Otwórz aplikację, wpisz **IP kompa** i **port** (8770), naciśnij „Zapisz i połącz".
5. Naciśnij „Otwórz ustawienia Dostępności" i włącz **Deep Focus Now** (to pozwala
   zamykać rozpraszające apki). Zezwól też na powiadomienia.

Gotowe. Gdy na kompie zaczniesz dzień i trwa PRACA — telefon blokuje apki i pokazuje
licznik. W przerwie odblokowuje.

## Zmiana listy blokowanych aplikacji

Edytuj `app/src/main/java/com/deepfocus/now/FocusState.kt` (zbiór `BLOCKED`, nazwy
pakietów) i wypchnij zmianę — GitHub zbuduje nowy APK.

## Budowanie APK

Robi się automatycznie na GitHub Actions po każdym pushu do `android/**`
(workflow `.github/workflows/android.yml`). APK ląduje w Releases („apk-latest")
oraz jako artefakt builda.

## Ograniczenia (uczciwie)

- Android nie pozwala „na twardo" zabić apki bez roota — usługa Dostępności **wyrzuca
  Cię do ekranu głównego** za każdym razem, gdy otworzysz zablokowaną apkę (skutecznie
  uniemożliwia korzystanie).
- Blokada dotyczy aplikacji. Blokada stron w przeglądarce telefonu to osobny temat
  (VPN) — można dodać później.
- Działa w tej samej sieci WiFi co komp (wersja domowa).
