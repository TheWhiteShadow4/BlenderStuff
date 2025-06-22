# pyright: reportInvalidTypeForm=false
import bpy
import os


def is_valid_unity_project(path):
    if not path or not os.path.isdir(path):
        return False
    
    assets_path = os.path.join(path, "Assets")
    project_settings_path = os.path.join(path, "ProjectSettings")

    return os.path.isdir(assets_path) and os.path.isdir(project_settings_path)


def update_unity_path(self, context):
    self.is_path_valid = is_valid_unity_project(self.unity_project_path)
    self.unity_version = ""
    if self.is_path_valid:
        try:
            version_file_path = os.path.join(self.unity_project_path, "ProjectSettings", "ProjectVersion.txt")
            if os.path.exists(version_file_path):
                with open(version_file_path, 'r') as f:
                    # The version is on the first line, like "m_EditorVersion: 2022.3.10f1"
                    line = f.readline()
                    version = line.split(':')[1].strip()
                    self.unity_version = version
                    
                    default_unity_path = f"C:\\Program Files\\Unity\\Hub\\Editor\\{version}\\Editor\\Unity.exe"

                    if os.path.exists(default_unity_path):
                        self.unity_executable_path = default_unity_path
        except Exception:
            # If anything goes wrong, just do nothing. User can set it manually.
            pass


class UnityAddonProperties(bpy.types.PropertyGroup):
    unity_project_path: bpy.props.StringProperty(
        name="Unity Project Path",
        description="Path to the root of the Unity project",
        subtype='DIR_PATH',
        default="",
        update=update_unity_path
    )

    is_path_valid: bpy.props.BoolProperty(
        name="Is Path Valid",
        description="True if the path is a valid Unity project",
        default=False
    )

    unity_version: bpy.props.StringProperty(
        name="Unity Version",
        description="Detected Unity version of the project",
        default=""
    )

    export_path: bpy.props.StringProperty(
        name="Export Path",
        description="Path to export Blender objects to. Relative to the Unity project root.",
        default="Assets/FBX"
    )

    unity_executable_path: bpy.props.StringProperty(
        name="Unity Executable Path",
        description="Path to the Unity executable (Unity.exe)",
        subtype='FILE_PATH',
        default=""
    )

    apply_gamma_correction: bpy.props.BoolProperty(
        name="Apply Gamma Correction",
        description="Convert colors from Linear to sRGB space on export to match Blender's viewport color.",
        default=True
    )

def register():
    bpy.utils.register_class(UnityAddonProperties)
    bpy.types.Scene.unity_tool_properties = bpy.props.PointerProperty(type=UnityAddonProperties)

def unregister():
    del bpy.types.Scene.unity_tool_properties
    bpy.utils.unregister_class(UnityAddonProperties) 