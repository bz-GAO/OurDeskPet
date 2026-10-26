Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root
If Not fs.FileExists(root & "\.venv\Scripts\pythonw.exe") Then
  MsgBox "RinaYaki is not installed. Run scripts\Setup-RinaYaki.ps1 first.", 16, "RinaYaki"
  WScript.Quit 2
End If
shell.Environment("Process")("PYTHONPATH") = fs.BuildPath(root, "src") & ";" & shell.Environment("Process")("PYTHONPATH")
shell.Environment("Process")("PYTHONDONTWRITEBYTECODE") = "1"
shell.Run Chr(34) & root & "\.venv\Scripts\pythonw.exe" & Chr(34) & " " & Chr(34) & root & "\scripts\yaki_ui.py" & Chr(34), 0, False
