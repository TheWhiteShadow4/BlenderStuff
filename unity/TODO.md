# TODO

Baking 3 passes
Pass #0 Effektiv: 2 / 2; Objekt: Suzanne; Materialien: 2
        Socket: BaseMap in Mat_Suzanne1; UV: UVMap1 -> {'G', 'B', 'R'} in Baking-Target
        Socket: BaseMap in Mat_Suzanne2; UV: UVMap1 -> {'G', 'B', 'R'} in Baking-Target
Pass #1 Effektiv: 2 / 2; Objekt: Suzanne; Materialien: 2
        Socket: BumpMap in Mat_Suzanne1; UV: UVMap1 -> {'G', 'B', 'R'} in None
        Socket: BumpMap in Mat_Suzanne2; UV: UVMap1 -> {'G', 'B', 'R'} in None
Pass #2 Effektiv: 4 / 4; Objekt: Suzanne; Materialien: 2
        Socket: Smoothness in Mat_Suzanne1; UV: UVMap1 -> {'R'} in Baking-Masks
        Socket: Smoothness in Mat_Suzanne2; UV: UVMap1 -> {'R'} in Baking-Masks
        Socket: Metallic in Mat_Suzanne1; UV: UVMap1 -> {'G'} in Baking-Masks
        Socket: Metallic in Mat_Suzanne2; UV: UVMap1 -> {'G'} in Baking-Masks

Baker dafür auslegen, dass dieses Setup funktioniert. Dafür Muss das Bake Image-Node ein RGB Combine bekommen.

# Bugs
- [ ] Bake presets Button wird nicht deaktiviert, wenn keine Presets aktiv sind
- [x] Channel Auswahl in Single Channel Sockets ist mehrzeilig und leer.


- [x] C#-Skript im Unity-Projekt bei jeder Ausführung aktualisieren, um bei Add-on-Updates konsistent zu sein.
- [x] Color Space in erstellten Images berücksichtigen. sRGB und raw (non color data)
- [x] Blender Bake Optionen wie bleeding, clear Image
- [ ] Nodes besser ausrichten/neu anordnen


## Nice to Have

- [ ] Seperate Node nur einemal pro Image Node erstellen oder zumindest einklappen
- [ ] Pfad vom BlenderAssetProcessor konfigurierbar machen