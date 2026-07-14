@echo off
REM Otwiera zapore Windows dla polaczenia z telefonem (port 8770, siec lokalna).
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Prosze o uprawnienia administratora...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
echo Dodaje regule zapory dla Deep Focus Now (port 8770)...
netsh advfirewall firewall delete rule name="Deep Focus Now LAN 8770" >nul 2>&1
netsh advfirewall firewall add rule name="Deep Focus Now LAN 8770" dir=in action=allow protocol=TCP localport=8770 profile=private,domain
echo.
echo GOTOWE. Telefon w tej samej sieci WiFi powinien sie teraz polaczyc.
echo Mozesz zamknac to okno.
pause
