# 🔧 Refactoring Plan - Unity Tools Blender Addon

**Erstellt:** 2025-10-25  
**Addon Version:** 1.1  
**Blender Version:** 4.4+

---

## 📋 Inhaltsverzeichnis

1. [Executive Summary](#executive-summary)
2. [Code-Analyse](#code-analyse)
3. [Identifizierte Probleme](#identifizierte-probleme)
4. [Refactoring Plan](#refactoring-plan)
5. [Priorisierung](#priorisierung)
6. [Aufwandsschätzung](#aufwandsschätzung)
7. [Risiken & Mitigation](#risiken--mitigation)

---

## 🎯 Executive Summary

Das Unity Tools Addon hat eine solide Grundstruktur, leidet aber unter:
- **Hoher Funktionskomplexität** (einige Funktionen >300 Zeilen)
- **Inkonsistenter Namenskonvention** (Deutsch/Englisch Mix)
- **Fehlender Fehlerbehandlung** (generische Exceptions)
- **Mangelnder Testbarkeit** (monolithische Funktionen)

**Empfehlung:** Schrittweises Refactoring über 4 Phasen (~40-50 Stunden)

---

## 🔍 Code-Analyse

### 1. Genereller Aufbau & Architektur

#### ✅ Stärken
- Klare Trennung zwischen UI (`ui/`), Operators, Properties und Utilities
- Modulare Struktur mit spezialisierten Dateien
- Saubere Registrierungs-/Deregistrierungslogik in `__init__.py`
- Gute Verwendung von Context Managern (`RotationFixSettings`)

#### ❌ Schwächen
- **Deutsche Variablennamen im Code**: Sollten auf Englisch sein (Code auf Englisch, Kommentare auf Deutsch)
- **Fehlende zentrale Konstanten**: Viele Magic Numbers und hardcodierte Strings
- **Kein zentrales Error Handling**: Jeder Operator macht sein eigenes Reporting
- **Keine Logging-Strategie**: Mix aus `print()` und `self.report()`

---

### 2. Strukturanalyse der Hauptmodule

#### `operators.py` (641 Zeilen) - 🔴 KRITISCH

**Probleme:**
```python
# Monster-Methode: 273 Zeilen
UNITY_OT_quick_export.execute()          # Zeilen 207-273, CC ~15

# Zu komplex: 314 Zeilen
UNITY_OT_merge_objects                   # Zeilen 312-626, CC ~25

# Deep Nesting (bis zu 6 Ebenen)
_process_socket()                        # Zeilen 83-137
```

**Metriken:**
- Gesamtlänge: 641 Zeilen
- Anzahl Klassen: 3
- Durchschnittliche Methodenlänge: ~80 Zeilen
- Zyklomatische Komplexität: 15-25 (Ziel: <10)

---

#### `baker.py` & `bake_utils.py`

**✅ Stärken:**
- Gute Separation of Concerns
- Generator für State-Management
- Klare Datenstrukturen (`BakeData`, `BakePass`)

**❌ Schwächen:**
- Tight Coupling zwischen `Baker` und `MaterialMetadata`
- Try-Except ohne spezifische Exception-Types
- Riesige `validate()` Methode (108 Zeilen)

```python
# Beispiel: Zu breites Exception Handling
except Exception as e:  # ❌ Zu generisch
    print(traceback.format_exc())
```

---

#### `panel_baking.py` (983 Zeilen) - 🔴 KRITISCH

**Probleme:**
- Fast 1000 Zeilen in einer Datei
- `UNITY_OT_bake_batch`: 250+ Zeilen
- UI-Logik vermischt mit Business-Logik
- `draw_bake_settings_ui()`: 90 Zeilen Helper-Funktion

**Aufteilung notwendig!**

---

#### `cloth_rigger.py` (281 Zeilen)

**✅ Positiv:**
- Gut strukturierte Helper-Funktionen
- Klares Prioritätssystem

**⚠️ Verbesserungspotential:**
- `execute()` Methode: 220 Zeilen
- Könnte in kleinere, testbare Funktionen aufgeteilt werden

---

### 3. Semantik & Code Quality

#### Deutsche Variablennamen im Code

```python
# ❌ Inkonsistent - Variablen sollten englisch sein
def _handle_material_export(self, context, obj, export_path, fbx_filepath):
    """Exportiert alle Materialien eines Objekts in eine .imp.json Datei."""
    # Zielverzeichnis vorbereiten
    texture_export_dir = os.path.join(export_path, "Textures")
    
    # Prüfen, ob das Image intern ist
    is_internal = not tex_node.image.filepath
```

#### Magic Numbers

```python
# ❌ Unerklärte Konstanten
bone.tail = pos - normal * 0.2                                    # Warum 0.2?
v_offset = (len(self.bake_data.passes) / 2 - bake_pass.index) * 250  # Warum 250?
image_node.location.x -= 300                                      # Warum 300?
```

#### Hartcodierte Strings

```python
# ❌ Mehrfach verwendet, sollten Konstanten sein
"__DummyImage"
"Assets/FBX"
"cloth_bone_"
"cloth_vgroup_"
```

---

### 4. Funktionskomplexität (Cyclomatic Complexity)

| Funktion | Zeilen | CC | Status |
|----------|--------|-----|--------|
| `UNITY_OT_quick_export.execute()` | 66 | ~15 | 🔴 Hoch |
| `UNITY_OT_merge_objects.execute()` | 198 | ~25 | 🔴 Sehr hoch |
| `UNITY_OT_bake_batch.bake_batch()` | 86 | ~20 | 🔴 Hoch |
| `BakeData.validate()` | 61 | ~18 | 🔴 Hoch |
| `Baker.bake_pass()` | 30 | ~8 | 🟡 Mittel |
| `draw_bake_settings_ui()` | 90 | ~12 | 🟡 Mittel |

**Legende:**  
- 🟢 CC < 10: Gut  
- 🟡 CC 10-15: Akzeptabel  
- 🔴 CC > 15: Refactoring dringend nötig

---

### 5. Abhängigkeiten & Coupling

```
operators.py
  ├─→ baker.py
  ├─→ rotation_fix_settings.py
  └─→ properties.py
  
baker.py
  ├─→ bake_utils.py
  └─→ bpy (Blender API)
  
panel_baking.py
  ├─→ baker.py
  ├─→ bake_utils.py
  └─→ bpy
  
cleanup_operators.py
  └─→ object_cleanups.py
```

**⚠️ Risiko:** Potenzielle zirkuläre Imports zwischen `operators.py` und `baker.py`

---

### 6. Error Handling & Robustheit

#### ❌ Probleme

**1. Generische Exceptions**
```python
try:
    # Complex operation
except Exception as e:  # ❌ Zu breit!
    self.report({'WARNING'}, f"Error: {e}")
```

**2. Inkonsistentes Error-Reporting**
```python
# Korrekt:
self.report({'ERROR'}, "Invalid path")

# ❌ Falsch (funktioniert nicht):
print({'ERROR'}, "Something went wrong")
```

**3. Fehlende Input-Validierung**
```python
# Kein Check ob path existiert
export_path = os.path.join(unity_props.engine_project_path, unity_props.export_path)
os.makedirs(export_path, exist_ok=True)  # Kann crashen
```

---

## 🚨 Identifizierte Probleme

### Kritisch (P0)
1. ❌ **Code-Duplizierung**: Material-Export-Logik in mehreren Operatoren
2. ❌ **Monolithische Funktionen**: >200 Zeilen, nicht testbar
3. ❌ **Fehlende Error-Strategie**: Keine konsistente Fehlerbehandlung

### Hoch (P1)
4. ⚠️ **Deutsche Variablennamen**: Code sollte englisch sein (Kommentare/Meldungen deutsch)
5. ⚠️ **Magic Numbers**: Keine Erklärung für Konstanten
6. ⚠️ **Fehlende Logging**: Mix aus print() und report()

### Mittel (P2)
7. 💡 **UI-Dateigröße**: panel_baking.py mit 983 Zeilen
8. 💡 **Fehlende Tests**: Keine Unit-Tests vorhanden
9. 💡 **Dokumentation**: Unvollständige Docstrings

---

## 🔧 Refactoring Plan

### **PHASE 1: FOUNDATION** (Basis-Verbesserungen)

#### 1.1 Typos korrigieren ⏱️ 30 Min | 🟢 Niedrig

**Ziel:** Offensichtliche Tippfehler im Code beheben

**Aufgaben:**
- [ ] `difuse_pipeline` → `diffuse_pipeline` (baker.py, Zeile 11)
- [ ] Weitere Typos bei Code-Review identifizieren und korrigieren

**Beispiel:**
```python
# ❌ Vorher:
self.difuse_pipeline = False

# ✅ Nachher:
self.diffuse_pipeline = False
```

**Betroffene Dateien:** `baker.py`, weitere bei Bedarf

**Hinweis:** Die Namenskonvention ist bereits gut - Code auf Englisch, Kommentare auf Deutsch

---

#### 1.2 Konstanten extrahieren ⏱️ 30 Min | 🟢 Niedrig

**Ziel:** Nur zentrale, mehrfach verwendete Konstanten extrahieren. Datei-spezifische Magic Numbers lokal dokumentieren.

**Erstelle:** `constants.py` (minimal)

```python
# constants.py
"""Zentrale Konstanten für Unity Tools Addon."""

# ===== File Paths (mehrfach verwendet) =====
DUMMY_IMAGE_NAME = "__DummyImage"  # Verwendet in baker.py und bake_utils.py
DEFAULT_EXPORT_PATH = "Assets/FBX"
TEXTURE_EXPORT_DIR = "Textures"

# ===== Export Settings (mehrfach verwendet) =====
UNITY_FBX_SCALE = 0.01
UNITY_AXIS_FORWARD = 'Z'
UNITY_AXIS_UP = 'Y'
GODOT_FBX_SCALE = 1.0
GODOT_AXIS_FORWARD = '-Z'
GODOT_AXIS_UP = 'Y'

# ===== Tolerances =====
ROTATION_TOLERANCE = 0.0001
GAMMA_CORRECTION_FACTOR = 2.2
```

**Lokale Magic Numbers dokumentieren** (am Anfang jeder Datei):

```python
# baker.py - oben nach Imports
# Magic Numbers für Node-Layout
_NODE_OFFSET_VERTICAL = 250    # Vertikaler Abstand zwischen Bake-Pass-Nodes
_NODE_OFFSET_HORIZONTAL = 300  # Horizontaler Abstand vom Socket

# cloth_rigger.py - oben nach Imports
_BONE_TAIL_OFFSET = 0.2  # Länge des Bone-Tail relativ zur Normalen
```

**Update Usage:**
```python
# Zentrale Konstanten:
from . import constants
image = bpy.data.images.new(name=constants.DUMMY_IMAGE_NAME, width=1, height=1)

# Lokale Konstanten:
v_offset = (len(self.bake_data.passes) / 2 - bake_pass.index) * _NODE_OFFSET_VERTICAL
```

**Begründung:** Nur wirklich zentrale Werte extrahieren. Lokale Magic Numbers bleiben in der Datei, werden aber dokumentiert

---

### **PHASE 2: STRUCTURAL REFACTORING** (Architektur)

#### 2.1 Material-Export-Logik extrahieren ⏱️ 2h | 🟢 Niedrig

**Problem:** `UNITY_OT_quick_export.execute()` macht zu viele Dinge (Material-Export, Textur-Handling, FBX-Export)

**Lösung:** Funktionen extrahieren statt komplexer Service-Klassen

**Erstelle:** `material_export.py` (einfache Funktionen)

```python
"""Funktionen für Material- und Textur-Export nach Unity."""

import os
import json
import shutil
from typing import Optional, Dict

def export_materials(obj, export_path, fbx_filepath, unity_props, operator):
        """
        Exportiert alle Materialien eines Objekts in eine .imp.json Datei.
        
    Args:
        obj: Blender Object
        export_path: Basis-Export-Verzeichnis
        fbx_filepath: Pfad zur FBX-Datei
        unity_props: Unity-Tool Properties
        operator: Operator-Instanz für self.report()
        """
        materials_data = []
    texture_cache = {}
        
        for mat_slot in obj.material_slots:
            if not mat_slot.material:
                continue
            
        mat_data = _process_material(
            mat_slot.material, 
            export_path, 
            unity_props, 
            texture_cache, 
            operator
        )
            if mat_data:
                materials_data.append(mat_data)
        
        if not materials_data:
        return
    
    # JSON schreiben
        json_filepath = fbx_filepath + ".imp.json"
        try:
            with open(json_filepath, 'w') as f:
            json.dump({"materials": materials_data}, f, indent=4)
        operator.report({'INFO'}, f"Exported material data for {len(materials_data)} materials.")
        except Exception as e:
        operator.report({'WARNING'}, f"Could not write material json: {e}")


def _process_material(material, export_path, unity_props, texture_cache, operator):
    """Verarbeitet ein einzelnes Material."""
    # ... vorhandene Logik aus _handle_material_export() ...
    pass


def copy_texture(tex_node, export_path, unity_props, cache):
    """
    Kopiert eine Textur ins Export-Verzeichnis mit Caching.
        
        Args:
        tex_node: Textur-Node mit Bild
        export_path: Zielverzeichnis
        unity_props: Unity Properties
        cache: Dict für bereits kopierte Texturen
            
        Returns:
        Relativer Pfad oder None bei Fehler
        """
        if not tex_node.image:
            return None
        
        # Cache prüfen
    if tex_node.image.name in cache:
        return cache[tex_node.image.name]
    
    # ... vorhandene Logik aus _copy_texture_and_get_path() ...
    
    cache[tex_node.image.name] = relative_path
    return relative_path
```

**Refactorierter Operator:**
```python
# operators.py (bleibt eine Datei!)
from . import material_export

class UNITY_OT_quick_export(bpy.types.Operator):
    """Quick export selected object to Unity project"""
    bl_idname = "unity.quick_export"
    bl_label = "Quick Export"
    
    def execute(self, context):
        # ... FBX Export ...
        
        # Material-Export (jetzt sauber getrennt)
        material_export.export_materials(
            active_obj, 
            export_path, 
            filepath, 
            unity_props, 
            self
        )
        
            return {'FINISHED'}
```

**Benefits:**
- Einfache Funktionen statt komplexer Klassen
- Testbar (Funktionen können mit Mock-Daten aufgerufen werden)
- Wiederverwendbar
- Keine zusätzliche Verzeichnis-Struktur nötig

---

#### 2.2 `panel_baking.py` aufteilen ⏱️ 2h | 🟡 Mittel

**Problem:** 983 Zeilen - schwer zu navigieren

**Lösung:** In 3 logische Dateien aufteilen (nicht 6!)

**Neue Struktur:**
```
ui/
  ├── panel_baking_properties.py  (~300 Zeilen)
  │   - MaterialBakeBase
  │   - MaterialBakeOverride  
  │   - BakePreset
  │   - ObjectBakeSettings
  │   - ImageBakeSettings
  │   - Helper-Funktionen (get_bakeable_sockets, etc.)
  │
  ├── panel_baking_operators.py   (~400 Zeilen)
  │   - UNITY_OT_bake_batch
  │   - UNITY_OT_add_bake_preset
  │   - UNITY_OT_remove_bake_preset
  │   - UNITY_OT_move_preset_up/down
  │   - UNITY_OT_toggle_bake_channel
  │   - UNITY_OT_confirm_bake
  │
  └── panel_baking.py              (~280 Zeilen)
      - UNITY_PT_baking_panel
      - UNITY_PT_image_bake_settings_panel
      - UNITY_UL_bake_presets
      - draw_bake_settings_ui() (UI Helper)
      - Imports von _properties und _operators
```

**Update `panel_baking.py`:**
```python
"""Baking UI Panel."""

import bpy
from . import panel_baking_properties as props
from . import panel_baking_operators as ops

# Import der Klassen für Registrierung
from .panel_baking_properties import (
    MaterialBakeBase, MaterialBakeOverride, BakePreset, 
    ObjectBakeSettings, ImageBakeSettings
)
from .panel_baking_operators import (
    UNITY_OT_bake_batch, UNITY_OT_add_bake_preset, 
    # ... weitere Operatoren
)

# UI Code bleibt hier
class UNITY_PT_baking_panel(bpy.types.Panel):
    # ... Panel-Code ...
    pass

def draw_bake_settings_ui(layout, context, override_settings, preset_settings):
    # ... UI Helper ...
        pass
```

**Begründung:** 
- 3 Dateien statt 6 (einfacher zu navigieren)
- Logische Gruppierung: Properties, Operatoren, UI
- Keine komplexe Package-Struktur nötig

---

### **PHASE 3: CODE QUALITY** (Robustheit & Wartbarkeit)

#### 3.1 Minimales Error Handling ⏱️ 1h | 🟢 Niedrig

**Ziel:** Einfache, klare Exception-Hierarchie ohne Over-Engineering

**Erstelle:** `exceptions.py` (minimal)

```python
"""Custom Exceptions für Unity Tools Addon."""

class AddonError(Exception):
    """Basis-Exception für Unity Tools Addon."""
    pass


class ValidationError(AddonError):
    """Wird geworfen wenn Validierung fehlschlägt (Projekt, Material, Bake-Daten)."""
    pass


class ExportError(AddonError):
    """Wird geworfen wenn Export fehlschlägt (FBX, Material, Textur)."""
    pass
```

**Das war's!** 3 Exceptions statt 7. Mehr braucht es nicht.

**Usage in Operatoren:**
```python
from .exceptions import ValidationError, ExportError

class UNITY_OT_quick_export(bpy.types.Operator):
    def execute(self, context):
        try:
            # Validierung
            if not self._validate_project(unity_props):
                raise ValidationError("Ungültiger Unity-Projektpfad")
            
            # Export
            self._export_fbx(context)
            self._export_materials(context)
            
            self.report({'INFO'}, f"{obj.name} erfolgreich exportiert")
            return {'FINISHED'}
            
        except (ValidationError, ExportError) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Unerwarteter Fehler: {e}")
            print(f"Exception in quick_export: {e}")  # Für Debugging
            return {'CANCELLED'}
```

**Begründung:** Einfach, klar, kein Overhead. `self.report()` ist bereits perfekt für Blender-Operatoren

---

#### 3.2 Debug-Verbesserungen ⏱️ 1-2h | 🟢 Niedrig

**Ziel:** Fehlermeldungen verbessern und sinnvolle Debug-Informationen ausgeben (kein Logging-Framework!)

**Aufgaben:**

1. **Fehlermeldungen aussagekräftiger machen:**

```python
# ❌ Vorher (baker.py, Zeile 47):
except Exception as e:
    print(traceback.format_exc())
    print({'ERROR'}, f"{e}")  # print() statt self.report()!
    return {'CANCELLED'}

# ✅ Nachher:
except Exception as e:
    print(f"[Baker] Fehler beim Baking: {e}")
    print(traceback.format_exc())
    return {'CANCELLED'}
```

2. **Wichtige Daten mit ausgeben:**

```python
# ❌ Vorher:
self.report({'WARNING'}, f"Could not copy texture: {e}")

# ✅ Nachher:
self.report({'WARNING'}, f"Textur '{tex_node.image.name}' konnte nicht kopiert werden: {e}")
print(f"[Texture Export] Fehler bei {tex_node.image.name}: Quellpfad={source_path}, Ziel={dest_path}")
```

3. **Konsistente Debug-Präfixe:**

```python
# Für alle print()-Statements Präfixe verwenden
print(f"[Baker] Bake Pass {bake_pass.index}")
print(f"[MaterialExport] Exportiere {len(materials_data)} Materialien")
print(f"[Validation] Prüfe UV Map {setting.uv_map_name}")
```

4. **Falsche `print()` Statements korrigieren:**

```python
# ❌ Falsch (mehrfach im Code):
print({'INFO'}, f"Some message")  # print() mit Blender-Operator-Syntax

# ✅ Richtig:
print(f"[Module] Some message")  # Für Console
# ODER in Operatoren:
self.report({'INFO'}, "Some message")  # Für User-Feedback
```

**Checklist:**
- [ ] Alle `print({'ERROR'}, ...)` zu `print(f"[Module] ...")` oder `self.report()` ändern
- [ ] Fehlermeldungen mit Kontext-Daten anreichern (Namen, Pfade, Indizes)
- [ ] Präfixe für Module hinzufügen (`[Baker]`, `[Export]`, etc.)
- [ ] Exception-Messages verbessern mit konkreten Werten

**Begründung:** `print()` funktioniert perfekt für Blender-Console. Ein Logging-Framework wäre Overhead ohne Nutzen

---

#### 3.3 Validierungs-Funktionen ⏱️ 1-2h | 🟢 Niedrig

**Ziel:** Einfache Validierungs-Funktionen (keine Klassen-Hierarchie!)

**Erstelle:** `validation.py` (EINE Datei)

```python
"""Validierungs-Funktionen für Unity Tools Addon."""

import os
from .exceptions import ValidationError


    def validate_unity_project(path: str) -> bool:
        """
        Validiert Unity-Projektpfad.
            
        Raises:
        ValidationError: Wenn Pfad ungültig
        """
        if not path:
        raise ValidationError("Projektpfad ist leer")
        
        if not os.path.exists(path):
        raise ValidationError(f"Pfad existiert nicht: {path}")
        
        if not os.path.isdir(path):
        raise ValidationError(f"Pfad ist kein Verzeichnis: {path}")
        
        # Unity-Struktur prüfen
        assets_path = os.path.join(path, "Assets")
        settings_path = os.path.join(path, "ProjectSettings")
        
        if not os.path.isdir(assets_path):
        raise ValidationError(f"Assets-Ordner nicht gefunden in: {path}")
        
        if not os.path.isdir(settings_path):
        raise ValidationError(f"ProjectSettings-Ordner nicht gefunden in: {path}")
        
        return True
    

    def validate_godot_project(path: str) -> bool:
        """
        Validiert Godot-Projektpfad.
            
        Raises:
        ValidationError: Wenn Pfad ungültig
        """
        if not path:
        raise ValidationError("Projektpfad ist leer")
        
        if not os.path.exists(path):
        raise ValidationError(f"Pfad existiert nicht: {path}")
        
        project_file = os.path.join(path, "project.godot")
        if not os.path.isfile(project_file):
        raise ValidationError(f"project.godot nicht gefunden in: {path}")
        
        return True
    

    def detect_engine(path: str) -> str:
        """
        Erkennt welche Game-Engine das Projekt verwendet.
            
        Returns:
        'UNITY' oder 'GODOT'
            
        Raises:
        ValidationError: Wenn keine Engine erkannt wurde
        """
        try:
        validate_unity_project(path)
            return 'UNITY'
    except ValidationError:
            pass
        
        try:
        validate_godot_project(path)
            return 'GODOT'
    except ValidationError:
        pass
    
    raise ValidationError(f"Pfad ist weder Unity- noch Godot-Projekt: {path}")


def validate_material(material) -> bool:
        """
        Validiert dass ein Material exportiert werden kann.
            
        Raises:
        ValidationError: Wenn Material ungültig
        """
        if not material:
        raise ValidationError("Material ist None")
        
        if not material.use_nodes:
        raise ValidationError(f"Material '{material.name}' verwendet keine Nodes")
    
    if not material.node_tree or not material.node_tree.nodes:
        raise ValidationError(f"Material '{material.name}' hat keinen Node-Tree")
    
    # Output-Node prüfen
        output_node = next(
            (n for n in material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), 
            None
        )
        
        if not output_node:
        raise ValidationError(f"Material '{material.name}' hat keinen Output-Node")
        
        if not output_node.inputs['Surface'].links:
        raise ValidationError(f"Material '{material.name}' Output ist nicht verbunden")
        
        return True
```

**Usage:**
```python
# In Operatoren:
from . import validation

class UNITY_OT_quick_export(bpy.types.Operator):
    def execute(self, context):
        try:
            # Projekt validieren
            path = context.scene.unity_tool_properties.engine_project_path
            engine = validation.detect_engine(path)
            
            # Materialien validieren
            for mat_slot in context.active_object.material_slots:
                validation.validate_material(mat_slot.material)
            
            # Mit Export fortfahren...
            
        except ValidationError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
```

**Begründung:** Einfache Funktionen sind testbar, lesbar und haben keinen Klassen-Overhead

---

### **PHASE 4: TESTING & DOCUMENTATION** (Qualitätssicherung)

#### 4.1 Tests für Validierung ⏱️ 2-3h | 🟢 Niedrig

**Ziel:** Nur Blender-unabhängige Funktionen testen (Validierung, Utilities)

**Realität:** Operator-Tests brauchen Blender-Context → Nicht praktikabel für Unit Tests

**Erstelle:** `tests/test_validation.py`

```python
"""Tests für Validierungs-Funktionen."""

import pytest
import os
import tempfile
from pathlib import Path
from validation import (
    validate_unity_project,
    validate_godot_project,
    detect_engine,
    ValidationError
)


def test_validate_unity_project_valid(tmp_path):
    """Test gültiges Unity-Projekt."""
    project = tmp_path / "TestProject"
    project.mkdir()
    (project / "Assets").mkdir()
    (project / "ProjectSettings").mkdir()
    
    assert validate_unity_project(str(project)) == True


def test_validate_unity_project_missing_assets(tmp_path):
    """Test fehlgeschlagene Validierung ohne Assets."""
    project = tmp_path / "Invalid"
    project.mkdir()
    (project / "ProjectSettings").mkdir()
    
    with pytest.raises(ValidationError, match="Assets-Ordner nicht gefunden"):
        validate_unity_project(str(project))


def test_detect_engine_unity(tmp_path):
    """Test Engine-Erkennung für Unity."""
    project = tmp_path / "UnityProject"
    project.mkdir()
    (project / "Assets").mkdir()
    (project / "ProjectSettings").mkdir()
    
    assert detect_engine(str(project)) == 'UNITY'


def test_detect_engine_godot(tmp_path):
    """Test Engine-Erkennung für Godot."""
    project = tmp_path / "GodotProject"
    project.mkdir()
    (project / "project.godot").write_text("")
    
    assert detect_engine(str(project)) == 'GODOT'
```

**Run:**
```bash
pip install pytest
pytest tests/test_validation.py -v
```

**Begründung:** Fokus auf testbare, Blender-unabhängige Funktionen. Operator-Tests sind zu aufwändig

---

#### 4.2 Docstrings verbessern ⏱️ 2h | 🟢 Niedrig

**Ziel:** Docstrings für öffentliche Funktionen/Klassen, kein volles Sphinx-Setup nötig

**Fokus auf:**
- Operatoren (`UNITY_OT_*`)
- Validierungs-Funktionen
- Export-Funktionen

**Beispiel - Gute Docstrings:**
```python
def export_materials(obj, export_path, fbx_filepath, unity_props, operator):
    """
    Exportiert alle Materialien eines Objekts in eine .imp.json Datei.
    
    Erstellt eine JSON-Datei neben dem FBX-Export mit Material-Definitionen,
    Shader-Referenzen und Textur-Pfaden für Unity's BlenderAssetPostprocessor.
    
    Args:
        obj: Blender-Objekt dessen Materialien exportiert werden
        export_path: Basis-Verzeichnis für Export
        fbx_filepath: Pfad zur exportierten FBX-Datei
        unity_props: Unity Tool Properties aus der Szene
        operator: Operator-Instanz für self.report()
    
    Note:
        Materialien ohne gültiges Node-Setup werden nur als Referenz exportiert.
        Texturen werden automatisch gecached um doppelte Kopien zu vermeiden.
    """
    pass


def validate_unity_project(path: str) -> bool:
    """
    Validiert ob ein Pfad ein gültiges Unity-Projekt ist.
    
    Prüft auf das Vorhandensein von:
    - Assets/ Verzeichnis
    - ProjectSettings/ Verzeichnis
        
        Args:
        path: Zu validierender Projektpfad
        
        Returns:
        True wenn gültiges Unity-Projekt
        
        Raises:
        ValidationError: Wenn Pfad ungültig oder keine Unity-Struktur
        """
        pass


class UNITY_OT_quick_export(bpy.types.Operator):
    """
    Schneller Export des ausgewählten Objekts ins Unity/Godot-Projekt.
    
    Exportiert:
    - FBX-Datei mit korrekten Achsen/Scale
    - Material-Daten als .imp.json (Unity)
    - Texturen ins Textures/ Unterverzeichnis
    
    Die Engine wird automatisch erkannt (Unity/Godot).
    """
    bl_idname = "unity.quick_export"
    bl_label = "Quick Export"
    bl_options = {'REGISTER', 'UNDO'}
```

**Checklist:**
- [ ] Alle `UNITY_OT_*` Operatoren dokumentieren
- [ ] Validierungs-Funktionen dokumentieren
- [ ] Export-Funktionen dokumentieren
- [ ] Komplexe Helper-Funktionen dokumentieren

**Begründung:** Gute Docstrings sind wertvoller als ein aufwändiges Sphinx-Setup

---

## 🎯 Priorisierung

### **🔴 Priorität 1 (Sofort, ~3.5-4h) - Foundation First**
1. ✅ Phase 1.1: Typos korrigieren (30 Min)
2. ✅ Phase 1.2: Zentrale Konstanten extrahieren (30 Min)
3. ✅ Phase 3.1: Minimales Error Handling (30 Min) 🎯 **FOUNDATION**
4. ✅ Phase 3.3: Validierungs-Funktionen (1h) 🎯 **FOUNDATION**
5. ✅ Phase 2.1: Material-Export extrahieren (1.5h) → Nutzt Exceptions & Validation!
6. ✅ Phase 3.2: Debug-Verbesserungen (30 Min)

**Total: ~3.5-4 Stunden** | Foundation zuerst, dann Features → Keine Doppelarbeit!

---

### **🟠 Priorität 2 (Nächste Iteration, ~3-4h)**
7. ✅ Phase 2.2: `panel_baking.py` aufteilen (2h)
8. ✅ Phase 4.2: Docstrings verbessern (1-2h)

**Total: ~3-4 Stunden** | Dokumentation zum Schluss, wenn alles steht

---

### **🟡 Priorität 3 (Nice-to-have, ~2-3h)**
9. Phase 4.1: Tests für Validierung (2-3h)

**Total: ~2-3 Stunden** | Qualitätssicherung

---

### **❌ Nicht durchführen (Over-Engineering)**
- ~~`operators.py` aufsplitten~~ → Ist schon übersichtlich
- ~~`merge_objects` refactoren~~ → Gut lesbar wie es ist
- ~~Logging Framework~~ → `print()` reicht
- ~~Service-Klassen mit DI~~ → Zu komplex für die Größe

---

## 📊 Aufwandsschätzung (Revidiert & Optimiert)

| Phase | Aufgaben | Stunden (Alt) | Stunden (Neu) | Änderung |
|-------|----------|---------------|---------------|----------|
| **Phase 1** | Foundation | 3-4h | 1h | ✅ -66% |
| **Phase 2** | Structural | 16-20h | 3.5h | ✅ -82% |
| **Phase 3** | Quality | 7-10h | 2.5h | ✅ -75% |
| **Phase 4** | Testing/Docs | 12-15h | 3-4h | ✅ -73% |
| **TOTAL** | - | **38-49h** | **10-12h** | ✅ **-76%** |

**Zusätzlicher Bonus durch optimierte Reihenfolge:**
- 🎯 Keine Doppelarbeit (Material-Export nutzt direkt neue Exceptions)
- 🎯 Jeder Schritt baut auf dem vorherigen auf
- 🎯 Foundation First = Weniger Refactoring-Aufwand später

---

## ⚠️ Risiken & Mitigation

### **Risiko 1: Breaking Changes bei Datei-Aufteilung**
**Beschreibung:** `panel_baking.py` aufteilen könnte Imports brechen

**Mitigation:**
- Schrittweises Vorgehen, nach jedem Schritt testen
- In `panel_baking.py` re-exports anlegen für Kompatibilität
- Gründliches Manual Testing im Blender

---

### **Risiko 2: Performance bei Validierung**
**Beschreibung:** Zusätzliche Validierungs-Calls könnten langsamer sein

**Mitigation:**
- Validierung nur bei User-Input, nicht bei internen Aufrufen
- Ergebnisse cachen wo sinnvoll
- Performance vor/nach messen

---

## ✅ Nächste Schritte (Optimierte Reihenfolge)

### **Priorität 1 Session (~3.5-4h)**

**Foundation First → Dann Features**

1. ✅ **Backup erstellen**
   ```bash
   git add .
   git commit -m "Backup vor Refactoring"
   git tag backup-pre-refactoring
   git checkout -b refactoring/pragmatic
   ```

2. ✅ **Typos korrigieren** (30 Min)
   - `difuse_pipeline` → `diffuse_pipeline` (baker.py, Zeile 11)
   - Weitere Typos beheben
   - **Commit:** `refactor: fix typos`

3. ✅ **Zentrale Konstanten** (30 Min)
   - `constants.py` erstellen (~10 Zeilen)
   - Nur wirklich zentrale Konstanten: DUMMY_IMAGE_NAME, FBX_SCALE, etc.
   - Lokale Magic Numbers dokumentieren (am Dateianfang)
   - **Commit:** `refactor: add central constants`

4. ✅ **exceptions.py minimal** (30 Min) 🎯 **FOUNDATION**
   - 3 Exception-Klassen: `AddonError`, `ValidationError`, `ExportError`
   - Nur ~15 Zeilen Code
   - **Commit:** `feat: add minimal exception classes`

5. ✅ **validation.py Funktionen** (1h) 🎯 **FOUNDATION**
   - `validate_unity_project()`, `validate_godot_project()`, `detect_engine()`
   - `validate_material()`
   - Nutzt bereits die neuen Exceptions!
   - **Commit:** `feat: add validation functions`

6. ✅ **Material-Export extrahieren** (1.5h)
   - `material_export.py` erstellen
   - Funktionen aus `operators.py` verschieben
   - **Nutzt jetzt direkt:** `ValidationError`, `ExportError`, `validate_material()`
   - Operator aktualisieren
   - **Commit:** `refactor: extract material_export functions`

7. ✅ **Debug verbessern** (30 Min)
   - Alle `print({'ERROR'}, ...)` korrigieren
   - Präfixe hinzufügen: `[Baker]`, `[Export]`, `[Validation]`
   - Fehlermeldungen mit Kontext-Daten anreichern
   - **Commit:** `refactor: improve debug messages`

**Test im Blender → Push**

---

### **Priorität 2 Session (~3-4h)**

8. ✅ **panel_baking.py aufteilen** (2h)
   - In 3 Dateien aufteilen: `_properties`, `_operators`, Haupt-Panel
   - **Commit:** `refactor: split panel_baking into 3 files`

9. ✅ **Docstrings verbessern** (1-2h)
   - Alle Operatoren dokumentieren
   - Export- und Validierungs-Funktionen
   - **Commit:** `docs: improve docstrings for public API`

**Test im Blender → Push → Merge**

---

### **Review-Checkpoints**
Nach jeder Session:
- [ ] Im Blender alle Features testen
- [ ] Performance-Check (fühlt sich alles gleich schnell an?)
- [ ] Git Commit
- [ ] Pause machen 😊

---

## 📝 Git Workflow (Optimiert für lineare Abarbeitung)

```bash
# Branch erstellen
git checkout -b refactoring

# Priorität 1 Session - Foundation First
git commit -m "refactor: fix typos (difuse → diffuse)"
git commit -m "refactor: add central constants"
git commit -m "feat: add minimal exception classes"           # 🎯 Foundation
git commit -m "feat: add validation functions"                # 🎯 Foundation
git commit -m "refactor: extract material_export functions"  # Nutzt Foundation!
git commit -m "refactor: improve debug messages"
git push origin refactoring

# Test im Blender → Alles OK? Weiter mit Priorität 2

# Priorität 2 Session
git commit -m "refactor: split panel_baking into 3 files"
git commit -m "docs: improve docstrings for public API"
git push origin refactoring

# Test im Blender → Alles OK? Mergen!
git checkout main
git merge refactoring
```

**Vorteil:** Jeder Commit baut auf dem vorherigen auf, keine Doppelarbeit!

---

---

## 💡 Schlusswort

### **Die wichtigste Erkenntnis**

**Weniger ist mehr.** Ein Blender-Addon mit 2000 Zeilen braucht keine Enterprise-Architektur.

Der ursprüngliche Plan (38-49h) war **zu akademisch**. Dieses Refactoring ist jetzt **pragmatisch** (10-12h) und **optimal sortiert**:

✅ **Was wir machen:**
- **Foundation First:** Exceptions & Validation zuerst
- Funktionen extrahieren → Testbarkeit ↑
- Zentrale Konstanten → Wartbarkeit ↑
- Debug verbessern → Fehlersuche ↓
- Validierung → Robustheit ↑

🎯 **Warum die neue Reihenfolge besser ist:**
- Material-Export nutzt DIREKT die neuen Exceptions/Validation
- Keine Doppelarbeit, kein nachträgliches Umschreiben
- Linearer Flow: Klein → Groß, Foundation → Features

❌ **Was wir NICHT machen:**
- Service-Klassen mit DI
- Logging-Frameworks
- 6-Dateien-Strukturen
- Klassen wo Funktionen reichen

### **Für die Zukunft**

Wenn das Addon auf 5000+ Zeilen wächst, **dann** könnte man über:
- Komplexere Strukturen nachdenken
- Mehr Tests schreiben
- Dokumentations-Framework aufsetzen

Aber jetzt? **Keep it simple.**

---

## 📚 Ressourcen

- [Blender Python API](https://docs.blender.org/api/current/)
- [Python Best Practices](https://docs.python-guide.org/)
- [YAGNI Principle](https://en.wikipedia.org/wiki/You_aren%27t_gonna_need_it)

---

**Dokument-Version:** 2.0 (Pragmatisch)  
**Letztes Update:** 2025-10-25  
**Maintainer:** TheWhiteShadow
