# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
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

