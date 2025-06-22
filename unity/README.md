# Blender to Unity: Material & Model Exporter

## Overview

This Blender addon streamlines the process of exporting models and their complex materials from Blender to Unity. It automates the export of FBX models and creates corresponding Unity materials based on a custom shader node interface in Blender, preserving material properties and texture assignments.

## Features

*   One-click export of the selected object to a specified Unity project folder.
*   Automatic creation and configuration of Unity materials (`.mat`) from Blender materials.
*   Preserves material properties like Colors, Floats, and Textures.
*   Copies and links textures automatically into a `Textures` subfolder.
*   Correctly handles color spaces (Linear vs. sRGB) with an optional gamma correction setting.
*   Enforces a clear set of conventions for shader node inputs to prevent common errors.
*   Supports direct value inputs using `RGB` and `Value` nodes in Blender's shader editor.

## Installation

1.  In Blender, go to `Edit` > `Preferences` > `Add-ons`.
2.  Click `Install...` and navigate to the `.zip` file of this addon, or to the `__init__.py` inside the `unity` folder.
3.  Find "Unity Tools" in the list and enable it by checking the box.
4.  The necessary Unity script (`BlenderAssetPostprocessor.cs`) will be automatically copied to your Unity project's `Assets/Editor` folder upon first export.

## Usage

### 1. Configuration in Blender

*   In the 3D Viewport, open the sidebar (N-key) and find the **Unity** tab.
*   **Unity Project:** Set the path to the root folder of your Unity project. The addon will detect the version.
*   **Export Path:** Define the path within your Unity project's `Assets` folder where the assets should be exported (e.g., `Models/MyCharacter`).
*   **Apply Gamma Correction:** Enable this to automatically convert colors to match Unity's linear color space. This usually results in a better visual match. Disable it if you prefer to handle color spaces manually.

### 2. Shader Node Setup (Crucial!)

The addon works by reading the inputs of a **Node Group** that is connected to the `Surface` input of the `Material Output` node. This node group acts as the interface to your Unity shader.

1.  Create your material logic as you normally would.
2.  Select all the nodes that define your material's look, **except** the `Material Output` node.
3.  Group them by pressing `Ctrl+G`. You are now inside the node group.
4.  Connect the final shader output of your logic to the `Group Output` node.
5.  Open the sidebar (N-key) within the shader editor and go to the `Group` tab.
6.  Here, you define the **Inputs** for your node group. These inputs will become the properties of your Unity material.
7.  **Name your inputs according to the conventions below.** For example, an input for the main color could be named `Base Color`, and an input for a texture could be `Albedo Map`.

### 3. Exporting

1.  Select the mesh object you want to export in the 3D Viewport.
2.  Go to the "Unity" tab in the sidebar.
3.  Click **"Quick Export"**.

## Unity Workflow

The addon's Unity script will automatically:
1.  Detect the new `.fbx` and its accompanying `.b2u.json` file.
2.  Create a `Materials` subfolder next to your exported model.
3.  Create a new Unity Material (`.mat`) inside this folder, based on the data from the JSON file.
4.  Assign this new material to the imported model.
5.  Delete the temporary `.b2u.json` file.

## Shader Input Conventions

To ensure the exporter works correctly, you **must** follow these naming conventions for your Node Group inputs:

*   **`_Alpha` Suffix:** Any input name ending in `_Alpha` (e.g., `Emission_Alpha`) will be completely ignored by the exporter. This is useful for helper inputs in Blender that shouldn't be properties in Unity.
*   **`Map` or `Tex` Suffix:** Any input name ending in `Map` or `Tex` (e.g., `Normal Map`, `Detail Tex`) **must** be connected to an `Image Texture` node. If it's not, the exporter will report an error.
*   **`Color` Suffix:** Any input name ending in `Color` (e.g., `Base Color`, `Rim Color`) **must not** be connected to a texture. It should be driven by its default value or an `RGB` node.
*   **`Value` Node:** You can connect a `Value` node to a `Float` input to drive it.
*   **`RGB` Node:** You can connect an `RGB` node to a `Color` input to drive it. 