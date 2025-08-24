# Blender Game-Engine Utilities

## Overview

This Blender addon streamlines the process of baking gameready textures and exporting models and their complex materials from Blender to Gameengines like Unity.

![Game Tools UI with Bake Button](UI-Unity-Tools.jpg)

## Features

*	Material based texture batch baking with complex yet easy to use setting options.
*   One-click export of objects to Unity with automatic creation of Unity PBR materials.
*   Correctly handles color spaces (Linear vs. sRGB) with an optional gamma correction setting.
*   Enforces a clear set of conventions for shader node inputs to prevent common errors (see below).

## Installation

1.  Create a zip form the content in the `unity` folder of this addon.
2.  In Blender, go to `Edit` > `Preferences` > `Add-ons`.
3.  Click `Install...` and navigate to the `.zip` file.
4.  Find "Game Tools" in the list and enable it by checking the box.
5.  The necessary Unity script (`BlenderAssetPostprocessor.cs`) will be automatically copied to your Unity project's `Assets/Editor` folder upon first export.

## FBX Export to Unity

*   In the 3D Viewport, open the sidebar (N-key) and find the **Game Tools** tab.
*   **Unity Project:** Set the path to the root folder of your Unity project. The addon will detect the version.
*   **Export Path:** Define the path within your Project's `Assets` folder where the assets should be exported (e.g., `Models/MyCharacter`).
*   **Apply Gamma Correction:** Enable this to automatically convert colors to match Unity's linear color space. I Prefer to switch to raw colors in blender to match the look in unity more.

### 3. Exporting

1.  Select the mesh object you want to export in the 3D Viewport.
2.  Go to the "Game Tools" tab in the sidebar.
3.  Click **"Quick Export"**.

## Unity Workflow

The addon's Unity script will automatically:
1.  Detect the new `.fbx` and its accompanying `.imp.json` file.
2.  Create a `Materials` subfolder next to your exported model.
3.  Create a new Unity Material (`.mat`) inside this folder, based on the data from the JSON file.
4.  Assign this new material to the imported model.
5.  Delete the temporary `.imp.json` file.

## Advanced Texture Baking

This addon features a powerful and flexible texture baking system. It's designed to automate the process of converting complex procedural materials or node setups into a set of PBR textures, ready for use in Unity.

The baking tools are located in the **Properties Panel** under the **Material Properties** tab.

![Baking Presets UI](UI-Baking-Presets.jpg)

### Key Concepts

*   **Bake Presets:** All settings are organized into presets. You can create multiple presets per object, each defining a complete baking job (e.g., one for "Metal/Roughness" and another for "Special Effects"). Presets are stored with the object.
*   **Global Settings & Overrides:** Each preset has global settings for resolution, UV map, target bake inputs, etc. For maximum flexibility, you can override these settings on a per-material basis. This allows you to bake a metallic map for one material and an emission map for another within the same bake pass.
*   **Two-Step Baking Process:** To provide full transparency and solve complex cases (like different margin requirements), baking is a two-step process:
    1.  **Analysis:** Clicking "Bake Materials" first analyzes all presets and materials. It calculates the required bake passes and shows a summary in a confirmation dialog.
    2.  **Execution:** The actual, resource-intensive baking only starts after you confirm the dialog.

### Baking Workflow

1.  **Select your object.**
2.  Go to the **Material Properties** tab in the Properties Panel. You will find the **Baking Presets** panel.
3.  **Create a Preset:** Click the `+` button to add a new bake preset.
4.  **Configure Global Settings:**
    *   **Target Input:** Select the shader input from your node group that you want to bake (e.g., "Metallic", "Roughness"). This is the "source" for the bake.
    *   **UV Map:** Choose the UV map to bake to.
    *   **Bake Mode:**
        *   **New:** Creates a new image texture. You must specify the resolution and color space.
        *   **Existing:** Bakes into an existing image texture you select.
    *   **Channels:** For color or vector inputs, you can specify which channels (R, G, B) to write to. For float/scalar inputs, you specify a single target channel.
5.  **(Optional) Configure Material Overrides:**
    *   Select a material in the material slots. The panel will update to show the settings for that material.
    *   Enable **"Override Global Settings"** to unlock material-specific controls. You can now change the `Target Input`, `Bake Mode`, etc., just for this material.
    *   Enable **"Override Margin"** to set a custom bake margin (bleeding) for this specific material. The baker will automatically use the highest required margin for each bake pass.
6.  **Start the Bake:**
    *   In the main **Game Tools** tab in the 3D Viewport's sidebar (N-key), click **"Bake Materials"**.
    *   A confirmation dialog will appear, summarizing all the planned bake passes, the materials involved, and the target images.
    *   Review the passes and click **"OK"** to start the final bake.

### Image-Specific Settings

In the **Properties Panel**, with the **Image Editor** open, you'll find a **Unity Bake Settings** panel. This allows you to set bake options per-image:
*   **Override:** You must enable this to use the settings below.
*   **Clear Image:** If enabled, the image will be cleared to transparent black before the bake. This is useful to avoid artifacts from previous bakes, and overrides Blender's global "Clear" setting. 