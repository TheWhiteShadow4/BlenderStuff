# TODO

- [x] C#-Skript im Unity-Projekt bei jeder Ausführung aktualisieren, um bei Add-on-Updates konsistent zu sein.
- [ ] Pfad vom BlenderAssetProcessor konfigurierbar machen 

# Nice To Have

- [ ] On-Load-Problem: Automatische Validierung beim Start von Blender/Laden einer Datei. (Problem war, dass die Unity-Properties (`unity_tool_properties`) zum Zeitpunkt des `load_post`-Handlers noch nicht zuverlässig ausgelesen werden konnten). 