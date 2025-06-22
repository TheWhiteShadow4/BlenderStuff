# Design-Konzept: Intelligente Material-Pipeline

## 1. Problembeschreibung

Der Transfer von Materialien von Blender nach Unity ist verlustbehaftet und restriktiv. Der Standard-FBX-Export kann die Komplexität von Blenders Shader-Nodes nicht abbilden. Dies führt zu einem von zwei unerwünschten Workflows:
- **Problem A (Standard-Ansatz):** Der Künstler ist auf die PBR-Standard-Slots (Base Color, Metallic, etc.) beschränkt. Alle benutzerdefinierten Shader-Effekte oder prozeduralen Logiken in Blender gehen verloren.
- **Problem B (Manueller Ansatz):** Der Künstler muss jedes Material in Unity manuell nachbauen, was zeitaufwändig, fehleranfällig und nicht nachhaltig ist. Änderungen am Modell in Blender erfordern erneute manuelle Arbeit in Unity.

## 2. Vision & Ziel

Unser Ziel ist ein nahtloser, verlustfreier Workflow, der es einem Künstler oder Shader-Designer ermöglicht, die volle kreative Kontrolle zu behalten. Blender bleibt die "Single Source of Truth" für die *Daten* eines Materials, während Unity die Hoheit über die *Darstellung* (den Shader) behält.

**Der ideale Workflow:** Ein Künstler klickt auf "Quick Export" in Blender. Einen Moment später existiert in Unity ein perfekt konfiguriertes Material, das auf einen **benutzerdefinierten Unity-Shader** zugeschnitten ist, ohne einen einzigen manuellen Schritt in Unity.

## 3. Kernkonzept: "Convention over Configuration"

Wir erzwingen keine Konvertierung, sondern schaffen eine flexible **Daten-Pipeline**. Die Brücke zwischen Blender und Unity wird durch eine klar definierte Konvention (Schnittstelle) geschlagen.

- **Blender: Die "Interface" Node-Gruppe**
  - In Blender erstellen wir eine spezielle Node-Gruppe, die als "Unity Shader Interface" dient.
  - Die **Eingänge** dieser Node-Gruppe werden exakt so benannt wie die **Properties** des Ziel-Shaders in Unity (z.B. ein Eingang `_WindStrength` in Blender entspricht der Property `_WindStrength` im Unity-Shader).
  - Der Künstler kann beliebig komplexe Node-Trees in Blender erstellen, um die finalen Werte für diese Eingänge zu berechnen.

- **Die Brücke: Das JSON-Datenpaket**
  - Beim Export liest unser Add-on nur die Werte an den Eingängen der "Interface" Node-Gruppe aus.
  - Es generiert eine `.json`-Datei (z.B. `MyObject.fbx.mat.json`), die den Namen des Ziel-Shaders in Unity und eine Liste aller Properties (Name, Typ, Wert) enthält.

- **Unity: Der intelligente Asset-Postprocessor**
  - Ein `AssetPostprocessor`-Skript in Unity erkennt, wenn eine `.json`-Datei importiert wird.
  - Es liest die JSON-Datei, erstellt ein neues Unity-Material, weist ihm den spezifizierten (benutzerdefinierten) Shader zu und befüllt alle Shader-Properties mit den Werten aus der JSON.
  - Anschließend weist es dieses neue Material dem importierten Modell zu und löscht die nun überflüssige JSON-Datei.

## 4. Implementierungsplan (Meilensteine)

Wir werden dieses Feature schrittweise umsetzen:

- **Meilenstein 1: Proof of Concept (PoC)**
  - **Ziel:** Übertragung einfacher Werte (Float, Color).
  - **Blender**: Der Export-Operator extrahiert einen `Float`- und einen `Color`-Wert aus einer fest benannten Node-Gruppe und schreibt sie in die JSON.
  - **Unity**: Der Postprozessor erstellt ein Material mit einem fest codierten Standard-Shader und setzt die entsprechenden Eigenschaften.
  - **Ergebnis:** Wir beweisen, dass die grundlegende Daten-Pipeline funktioniert.

- **Meilenstein 2: Textur-Unterstützung & Shader-Auswahl**
  - **Ziel:** Texturen und benutzerdefinierte Shader handhaben.
  - **Blender**: Erweitern des Exports, um angeschlossene `Image Texture`-Nodes zu erkennen und deren Pfade zu exportieren. Der Name des Ziel-Shaders wird ebenfalls in die JSON geschrieben.
  - **Unity**: Erweitern des Postprozessors, um Texturen zu laden und sie dem Material zuzuweisen. Er liest den Shader-Namen aus der JSON und verwendet `Shader.Find()`.

- **Meilenstein 3: Benutzerfreundlichkeit (UX)**
  - **Ziel:** Den Prozess für den Künstler vereinfachen.
  - **Blender**: Erstellen eines neuen Buttons/Operators im Add-on, der automatisch eine leere "Unity Shader Interface"-Node-Gruppe mit einem Standard-Set an Eingängen im aktiven Material erstellt.

- **Meilenstein 4: Erweiterte Features**
  - **Ziel:** Mehr Datentypen unterstützen, mehrere Materialien.
  - **Blender/Unity**: Unterstützung für weitere Typen wie Vektoren (`Vector3`) oder Integer. Implementierung der Logik für Objekte, die mehrere Materialien verwenden. 