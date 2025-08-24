# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
import os
import re

def detect_game_engine(path):
	"""Gibt 'UNITY', 'GODOT' oder None zurück."""
	if is_valid_unity_project(path):
		return 'UNITY'
	if is_valid_godot_project(path):
		return 'GODOT'
	return None

def is_valid_unity_project(path):
    if not path or not os.path.isdir(path):
        return False
    
    assets_path = os.path.join(path, "Assets")
    project_settings_path = os.path.join(path, "ProjectSettings")

    return os.path.isdir(assets_path) and os.path.isdir(project_settings_path)

def is_valid_godot_project(path):
	"""Einfache Heuristik: Eine Godot-Projectdatei liegt im Root."""
	if not path or not os.path.isdir(path):
		return False
	return os.path.isfile(os.path.join(path, "project.godot"))


def update_project_path(self, context):
	engine = detect_game_engine(self.engine_project_path)
	print(f"Engine: {engine}")
	self.is_path_valid = engine is not None
	self.engine_version = ""
	if engine == 'UNITY':
		try:
			version_file_path = os.path.join(self.engine_project_path, "ProjectSettings", "ProjectVersion.txt")
			if os.path.exists(version_file_path):
				with open(version_file_path, 'r') as f:
					# The version is on the first line, like "m_EditorVersion: 2022.3.10f1"
					line = f.readline()
					version = line.split(':')[1].strip()
					self.engine_version = f"Unity {version}"
					if self.export_path == "" or not self.export_path.startswith("Assets/"):
						self.export_path = "Assets/FBX"
		except Exception:
			# If anything goes wrong, just do nothing. User can set it manually.
			pass
	elif engine == 'GODOT':
		try:
			project_file = os.path.join(self.engine_project_path, "project.godot")
			if os.path.exists(project_file):
				with open(project_file, 'r', encoding='utf-8') as f:
					for line in f:
						if line.strip().startswith("config/features"):
							# Beispiel: config/features=PackedStringArray("4.3", "GL Compatibility")
							match = re.search(r'"(\d+\.\d+)"', line)
							if match:
								version = match.group(1)
								self.engine_version = f"Godot {version}"
							break
				if self.export_path == "" or self.export_path.startswith("Assets/"):
					self.export_path = "FBX"
		except Exception:
			# If anything goes wrong, just do nothing. User can set it manually.
			pass

class UnityToolProperties(bpy.types.PropertyGroup):
    engine_project_path: bpy.props.StringProperty(
        name="Project Path",
        description="Path to the root of the Project",
        subtype='DIR_PATH',
        default="",
        update=update_project_path
    )

    is_path_valid: bpy.props.BoolProperty(
        name="Is Path Valid",
        description="True if the path is a valid project",
        default=False
    )

    engine_version: bpy.props.StringProperty(
        name="Game Engine",
        description="Detected Game Engine and Version of the project",
        default=""
    )

    export_path: bpy.props.StringProperty(
        name="Export Path",
        description="Path to export Blender objects to. Relative to the project root.",
        default="Assets/FBX"
    )

    apply_gamma_correction: bpy.props.BoolProperty(
        name="Apply Gamma Correction",
        description="Convert colors from Linear to sRGB space on export to match Blender's viewport color.",
        default=False
    )

class UnityClothRigProperties(bpy.types.PropertyGroup):
    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ('VERTICES', "Vertices", "Create bones on vertices"),
            ('FACES', "Faces", "Create bones on face centers")
        ],
        default='VERTICES'
    )
    nth: bpy.props.IntProperty(
        name="Every n-th Element",
        description="Create a bone for every n-th element",
        default=1,
        min=1
    )
    copy_rotation: bpy.props.BoolProperty(
        name="Copy Rotation",
        description="Also add a Copy Rotation constraint to the bones",
        default=False
    )
    vertex_group: bpy.props.StringProperty(
        name="Vertex Group",
        description="Use this vertex group to limit bone placement. Leave empty to use selection or all elements.",
        default=""
    )
    target_armature: bpy.props.PointerProperty(
        name="Target Armature",
        description="Add bones to this existing armature. Leave empty to create a new one or use selected armature.",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE'
    )
    clean_weights: bpy.props.BoolProperty(
        name="Clean Weights",
        description="Remove vertices from all existing deform vertex groups before assigning to new bones. Only applies when using existing armature.",
        default=True
    )

classes = [
    UnityToolProperties,
    UnityClothRigProperties
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.unity_tool_properties = bpy.props.PointerProperty(type=UnityToolProperties)
    bpy.types.Scene.unity_cloth_rig_properties = bpy.props.PointerProperty(type=UnityClothRigProperties)

def unregister():
    del bpy.types.Scene.unity_tool_properties
    del bpy.types.Scene.unity_cloth_rig_properties
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls) 