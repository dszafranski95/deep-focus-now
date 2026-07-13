' Uruchamia Deep Focus Now (licznik pokazuje sie w rogu, bez okna konsoli).
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe"
If Not fso.FileExists(pyw) Then pyw = "pythonw.exe"
sh.Run """" & pyw & """ """ & here & "\deepfocus.py""", 0, False
