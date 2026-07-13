Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
desktop = sh.SpecialFolders("Desktop")
Set lnk = sh.CreateShortcut(desktop & "\Deep Focus Now.lnk")
lnk.TargetPath = here & "\run_deepfocus.vbs"
lnk.WorkingDirectory = here
lnk.IconLocation = here & "\icon.ico"
lnk.Description = "Deep Focus Now - bloki pracy z blokada social mediow"
lnk.Save
WScript.Echo "Skrot utworzony: " & desktop & "\Deep Focus Now.lnk"
