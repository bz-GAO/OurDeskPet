Option Explicit

Dim shell, fso, root, pythonw, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")

If Not fso.FileExists(pythonw) Then
  Call MsgBox("RinaTomo is not installed. Run scripts\Setup-RinaTomo.ps1 first.", 16, "RinaTomo")
  WScript.Quit 2
End If

shell.CurrentDirectory = root
shell.Environment("Process")("PYTHONPATH") = fso.BuildPath(root, "src") & ";" & shell.Environment("Process")("PYTHONPATH")
shell.Environment("Process")("PYTHONDONTWRITEBYTECODE") = "1"
command = Chr(34) & pythonw & Chr(34) & " -m rinatomo ui"
shell.Run command, 1, False
