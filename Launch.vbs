Set objShell = CreateObject("Shell.Application")
Set FSO = CreateObject("Scripting.FileSystemObject")

ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
Python = "C:\Users\lusif\AppData\Local\Programs\Python\Python314\python.exe"
LaunchScript = ScriptDir & "\TopMostShield.pyw"

' Launch as admin with hidden window - the script hides its own console
objShell.ShellExecute Python, """" & LaunchScript & """", ScriptDir, "runas", 0
