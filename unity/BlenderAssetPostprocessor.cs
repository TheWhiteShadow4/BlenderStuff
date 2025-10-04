using UnityEditor;
using UnityEngine;
using System.IO;
using System.Linq;
using System.Collections.Generic;

// Helper classes for deserializing the JSON
[System.Serializable]
public class MaterialProperty
{
    public string name;
    public string type;
    public float[] value; // For Color
    public float floatValue; // For a single Float
    public string path; // For Texture path
}

[System.Serializable]
public class MaterialData
{
    public string materialName;
    public string shaderName;
    public MaterialProperty[] properties;
}

[System.Serializable]
public class MaterialDataList
{
    public MaterialData[] materials;
}

public class BlenderAssetPostprocessor : AssetPostprocessor
{
    // Step 1: Prepare the FBX importer BEFORE it imports the model.
    void OnPreprocessModel()
    {
        string materialJsonPath = assetPath + ".imp.json";
        if (File.Exists(materialJsonPath))
        {
            if (assetImporter is ModelImporter modelImporter)
            {
                modelImporter.useFileScale = false;
                
                // We must use an import mode that creates the material slots so we can remap them later. 
                // 'None' will not work as it discards the material slot information from the FBX.
                // 'ImportViaMaterialDescription' is the modern approach that allows remapping.
                modelImporter.materialImportMode = ModelImporterMaterialImportMode.ImportViaMaterialDescription;
                modelImporter.materialLocation = ModelImporterMaterialLocation.External;

                // Configure material search to find our newly created materials by name, not texture.
                modelImporter.materialName = ModelImporterMaterialName.BasedOnMaterialName;
                modelImporter.materialSearch = ModelImporterMaterialSearch.RecursiveUp;
            }
        }
    }

    // This method is called after ALL assets have been imported.
    // This is our main entry point to avoid API restrictions.
    static void OnPostprocessAllAssets(string[] importedAssets, string[] deletedAssets, string[] movedAssets, string[] movedFromAssetPaths)
    {
        // Find all imported .mat.json files from our addon.
        var jsonFilesToProcess = new List<string>();
        foreach (string path in importedAssets)
        {
            if (path.EndsWith(".imp.json"))
            {
                jsonFilesToProcess.Add(path);
            }
        }

        if (jsonFilesToProcess.Count == 0) return;

        bool assetsChanged = false;

        foreach(string jsonPath in jsonFilesToProcess)
        {
            // The json file is named like 'path/to/model.fbx.imp.json'.
            // We need to get 'path/to/model.fbx' from that.
            string fbxPath = jsonPath.Substring(0, jsonPath.Length - ".imp.json".Length);
            
            // Check if the corresponding FBX file exists.
            if (!File.Exists(fbxPath)) continue;

            // Read material data list
            string jsonContent = File.ReadAllText(jsonPath);
            MaterialDataList materialList = JsonUtility.FromJson<MaterialDataList>(jsonContent);

            if (materialList == null || materialList.materials == null || materialList.materials.Length == 0)
            {
                continue;
            }

            string fbxDirectory = Path.GetDirectoryName(fbxPath);
            string materialsDirectoryPath = Path.Combine(fbxDirectory, "Materials");

            // Create the directory if it doesn't exist.
            if (!Directory.Exists(materialsDirectoryPath))
            {
                Directory.CreateDirectory(materialsDirectoryPath);
            }

            // Ensure the FBX importer is available for remapping later
            ModelImporter modelImporter = AssetImporter.GetAtPath(fbxPath) as ModelImporter;

            foreach (var materialData in materialList.materials)
            {
                string materialFileName = materialData.materialName + ".mat";
                string materialPath = Path.Combine(materialsDirectoryPath, materialFileName).Replace('\\', '/');

                Material material = AssetDatabase.LoadAssetAtPath<Material>(materialPath);
                bool isNewMaterial = material == null;

                if (isNewMaterial)
                {
                    // Check if shaderName is null (unsupported material from Blender)
                    if (string.IsNullOrEmpty(materialData.shaderName))
                    {
                        // Try to find existing material in project by name
                        string[] guids = AssetDatabase.FindAssets($"{materialData.materialName} t:Material");
                        if (guids.Length > 0)
                        {
                            string existingMaterialPath = AssetDatabase.GUIDToAssetPath(guids[0]);
                            material = AssetDatabase.LoadAssetAtPath<Material>(existingMaterialPath);
                            Debug.Log($"Blender Importer: Found existing material '{materialData.materialName}' at '{existingMaterialPath}' for unsupported shader.", material);
                        }
                        else
                        {
                            Debug.LogWarning($"Blender Importer: Material '{materialData.materialName}' uses unsupported shader and no existing material found. Skipping.", AssetDatabase.LoadAssetAtPath<Object>(jsonPath));
                            continue; // Skip this material
                        }
                    }
                    else
                    {
                        Debug.Log($"Blender Importer: Creating new material for {jsonPath}");
                        Shader shader = Shader.Find(materialData.shaderName);
                        if (shader == null) {
                            Debug.LogWarning($"Blender Importer: Shader '{materialData.shaderName}' not found. Skipping material '{materialData.materialName}'.", AssetDatabase.LoadAssetAtPath<Object>(jsonPath));
                            continue; // Skip to next material
                        }
                        material = new Material(shader);
                        AssetDatabase.CreateAsset(material, materialPath);
                    }
                }
                // Apply properties
                foreach (MaterialProperty prop in materialData.properties)
                {
                    string propertyName = prop.name;
                    // If the property doesn't exist, try adding a leading underscore, which is a common Unity convention.
                    if (!material.HasProperty(propertyName))
                    {
                        string underscoredName = "_" + propertyName;
                        if (material.HasProperty(underscoredName))
                        {
                            propertyName = underscoredName;
                        }
                        else
                        {
                            Debug.LogWarning($"Blender Importer: Property '{prop.name}' (or '{underscoredName}') not found on shader '{material.shader.name}'. Skipping property.", material);
                            continue; // Skip this property
                        }
                    }

                    // Set the property value using the potentially modified name.
                    if (prop.type == "Color") { material.SetColor(propertyName, new Color(prop.value[0], prop.value[1], prop.value[2], prop.value[3])); }
                    else if (prop.type == "Float") { material.SetFloat(propertyName, prop.floatValue); }
                    else if (prop.type == "Texture" && !string.IsNullOrEmpty(prop.path))
                    {
                        Texture2D tex = AssetDatabase.LoadAssetAtPath<Texture2D>(prop.path);
                        if (tex != null) { material.SetTexture(propertyName, tex); }
                        else { Debug.LogWarning($"Blender Importer: Could not load texture '{prop.path}'.", material); }
                    }
                }
                
                EditorUtility.SetDirty(material);
                assetsChanged = true;

                // Now that the material is created/updated, find the FBX ModelImporter and assign it.
                if (modelImporter != null)
                {
                    // Find the specific material identifier from the FBX that matches our material name
                    var sourceIdentifier = modelImporter.GetExternalObjectMap()
                                                         .Keys
                                                         .FirstOrDefault(id => id.type == typeof(Material) && id.name == materialData.materialName);

                    // If we found a matching material in the FBX, remap it.
                    if (sourceIdentifier.name != null)
                    {
                        modelImporter.AddRemap(sourceIdentifier, material);
                    }
                    
                    EditorUtility.SetDirty(modelImporter);
                    modelImporter.SaveAndReimport();
                }
            }

            // Clean up the processed json file
            AssetDatabase.DeleteAsset(jsonPath);
        }

        if (assetsChanged)
        {
            AssetDatabase.SaveAssets();
        }
    }
} 