# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
import math
import os
import json
import shutil
from . import baker

class UNITY_OT_quick_export(bpy.types.Operator):
	"""Quick export selected object to Unity project"""
	bl_idname = "unity.quick_export"
	bl_label = "Quick Export"
	bl_options = {'REGISTER', 'UNDO'}

	def _correct_color(self, color, apply_gamma):
		"""Applies gamma correction to a color if the flag is set."""
		if not apply_gamma:
			return list(color)
		# Convert Linear to sRGB color space for Unity.
		return [
			pow(color[0], 1.0/2.2),
			pow(color[1], 1.0/2.2),
			pow(color[2], 1.0/2.2),
			color[3] # Alpha is linear
		]

	def _copy_texture_and_get_path(self, tex_node, unity_props, export_path):
		"""Copies a texture to the export directory and returns its relative path for Unity."""
		if not tex_node.image:
			self.report({'WARNING'}, f"Texture node '{tex_node.name}' has no image assigned.")
			return None
			
		# ------------------------------------------------------------
		# Duplicate-copy prevention via instance cache
		if not hasattr(self, "_texture_cache"):
			self._texture_cache = {}
		cached_path = self._texture_cache.get(tex_node.image.name)
		if cached_path:
			return cached_path

		# Zielverzeichnis vorbereiten
		texture_export_dir = os.path.join(export_path, "Textures")
		os.makedirs(texture_export_dir, exist_ok=True)

		# Prüfen, ob das Image intern ist (nicht auf der Festplatte gespeichert)
		is_internal = not tex_node.image.filepath or tex_node.image.filepath.startswith("//") or tex_node.image.packed_file

		try:
			if is_internal:
				# Für interne Bilder schreiben wir immer als PNG
				dest_path = os.path.join(texture_export_dir, tex_node.image.name + ".png")
				tex_node.image.filepath_raw = dest_path
				tex_node.image.file_format = 'PNG'
				tex_node.image.save()
			else:
				source_path = tex_node.image.filepath_from_user()
				if not os.path.exists(source_path):
					self.report({'WARNING'}, f"Texture file not found: {source_path}")
					return None
				# Behalte die Original-Endung
				dest_path = os.path.join(texture_export_dir, os.path.basename(source_path))
				# Wenn die Datei bereits am Ziel liegt, nicht erneut kopieren
				if os.path.abspath(source_path) != os.path.abspath(dest_path):
					try:
						shutil.copy(source_path, dest_path)
					except shutil.SameFileError:
						pass  # Quelle == Ziel, nichts zu tun
				else:
					# Datei liegt bereits am Zielort
					pass

			relative_texture_path = os.path.join(unity_props.export_path, "Textures", os.path.basename(dest_path))
			relative_texture_path = relative_texture_path.replace('\\', '/')
			# Cache merken
			self._texture_cache[tex_node.image.name] = relative_texture_path
			return relative_texture_path
		except Exception as e:
			self.report({'WARNING'}, f"Could not copy or save texture '{tex_node.image.name}': {e}")
			return None

	def _process_socket(self, socket, unity_props, export_path):
		"""Processes a single node socket and returns a dictionary for the JSON property, or None."""
		prop_name = socket.name
		
		if prop_name.endswith("_Alpha"):
			return None

		is_texture_convention = input_backeable(socket)
		is_color_convention = prop_name.lower().endswith("color")
		
		prop_entry = {"name": prop_name}

		# Case 1: Socket is connected to another node
		if socket.is_linked:
			from_node = socket.links[0].from_node

			if from_node.type == 'TEX_IMAGE':
				if is_color_convention:
					self.report({'ERROR'}, f"Input '{prop_name}' follows color convention but is connected to a texture.")
					return None
				
				tex_path = self._copy_texture_and_get_path(from_node, unity_props, export_path)
				if tex_path:
					prop_entry["type"] = "Texture"
					prop_entry["path"] = tex_path
				else:
					return None # Error was already reported by the helper

			elif from_node.type == 'RGB':
				if is_texture_convention:
					self.report({'ERROR'}, f"Input '{prop_name}' follows texture convention but is connected to an RGB Color node.")
					return None
				
				prop_entry["type"] = "Color"
				color = from_node.outputs['Color'].default_value
				prop_entry["value"] = self._correct_color(color, unity_props.apply_gamma_correction)

			elif from_node.type == 'VALUE':
				if is_texture_convention:
					self.report({'ERROR'}, f"Input '{prop_name}' follows texture convention but is connected to a Value node.")
					return None
				if is_color_convention:
					self.report({'ERROR'}, f"Input '{prop_name}' follows color convention but is connected to a Value node.")
					return None

				prop_entry["type"] = "Float"
				prop_entry["floatValue"] = from_node.outputs['Value'].default_value

			else:
				self.report({'INFO'}, f"Input '{prop_name}' is connected to an unsupported node type ('{from_node.type}'). It will be ignored.")
				return None
		
		# Case 2: Socket is not connected, use its default value
		else:
			if socket.type == 'RGBA':
				prop_entry["type"] = "Color"
				color = socket.default_value
				prop_entry["value"] = self._correct_color(color, unity_props.apply_gamma_correction)

			elif socket.type == 'VALUE':
				if is_color_convention:
					self.report({'ERROR'}, f"Input '{prop_name}' follows color convention but is a Float, not RGBA.")
					return None
				prop_entry["type"] = "Float"
				prop_entry["floatValue"] = socket.default_value
			
			else: # Other unlinked socket types we don't handle
				return None

		return prop_entry

	def _handle_material_export(self, context, obj, export_path, fbx_filepath):
		"""Exports ALL materials of the given object into a single *.imp.json file."""
		unity_props = context.scene.unity_tool_properties
		materials_data = []

		# Iterate over every material slot on the object
		for mat_slot in obj.material_slots:
			mat = mat_slot.material
			if not mat:
				continue

			# Find interface node inside this material
			output_node = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
			if not (output_node and output_node.inputs['Surface'].links):
				continue
			interface_node = output_node.inputs['Surface'].links[0].from_node
			if interface_node.type != 'GROUP':
				continue

			material_data = {
				"materialName": mat.name,
				"shaderName": interface_node.node_tree.name,
				"properties": []
			}

			for socket in interface_node.inputs:
				prop_entry = self._process_socket(socket, unity_props, export_path)
				if prop_entry:
					material_data["properties"].append(prop_entry)

			# Only add material if it actually has properties to export
			if material_data["properties"]:
				materials_data.append(material_data)

		# Nothing to export
		if not materials_data:
			return

		json_filepath = fbx_filepath + ".imp.json"
		try:
			with open(json_filepath, 'w') as f:
				json.dump({"materials": materials_data}, f, indent=4)
			self.report({'INFO'}, f"Exported material data for {len(materials_data)} materials.")
		except Exception as e:
			self.report({'WARNING'}, f"Could not write material json: {e}")

	@classmethod
	def poll(cls, context):
		return context.active_object is not None and context.active_object.type == 'MESH'

	def execute(self, context):
		scene = context.scene
		unity_props = scene.unity_tool_properties

		project_path = unity_props.engine_project_path
		from .properties import detect_game_engine
		engine = detect_game_engine(project_path)

		if engine is None:
			self.report({'ERROR'}, "Projektpfad scheint weder ein Unity- noch ein Godot-Projekt zu sein.")
			return {'CANCELLED'}

		# --- Import-Script Handling (Unity/Godot) -------------------
		addon_dir = os.path.dirname(os.path.realpath(__file__))
		try:
			if engine == 'UNITY':
				editor_script_dir = os.path.join(project_path, "Assets", "Editor")
				os.makedirs(editor_script_dir, exist_ok=True)
				src = os.path.join(addon_dir, "BlenderAssetPostprocessor.cs")
				dst = os.path.join(editor_script_dir, "BlenderAssetPostprocessor.cs")
				shutil.copy(src, dst)
			#elif engine == 'GODOT':
			#	gd_addon_dir = os.path.join(project_path, "addons", "blender_importer")
			#	os.makedirs(gd_addon_dir, exist_ok=True)
			#	for fname in ("blender_import.gd", "fbx_import.gd", "plugin.cfg"):
			#		src = os.path.join(addon_dir, "godot_plugin", fname)
			#		dst = os.path.join(gd_addon_dir, fname)
			#		shutil.copy(src, dst)
		except Exception as e:
			self.report({'ERROR'}, f"Could not copy import script(s): {e}")
			return {'CANCELLED'}

		# --- FBX Export ---
		export_path = os.path.join(unity_props.engine_project_path, unity_props.export_path)
		try:
			os.makedirs(export_path, exist_ok=True)
		except OSError as e:
			self.report({'ERROR'}, f"Could not create export directory: {e}")
			return {'CANCELLED'}

		active_obj = context.active_object
		filepath = os.path.join(export_path, f"{active_obj.name}.fbx")

		if engine == 'UNITY':
			bpy.ops.export_scene.fbx(
				filepath=filepath,
				use_selection=True,
				global_scale=0.01,
				axis_forward='Z',
				axis_up='Y',
			)
		elif engine == 'GODOT':
			bpy.ops.export_scene.fbx(
				filepath=filepath,
				use_selection=True,
				global_scale=1.0,
				axis_forward='-Z',
				axis_up='Y',
			)

		# --- Material Export ---
		# Cache für bereits exportierte Texturen leeren
		self._texture_cache = {}
		self._handle_material_export(context, active_obj, export_path, filepath)

		self.report({'INFO'}, f"Exported {active_obj.name} to {filepath}")
		return {'FINISHED'}

def input_backeable(socket):
	return True #socket.name.lower().endswith("map") or socket.name.lower().endswith("tex")

class UNITY_OT_apply_rotation_fix(bpy.types.Operator):
    """Apply rotation fix for Unity export"""
    bl_idname = "unity.apply_rotation_fix"
    bl_label = "Apply Rotation Fix"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        active_obj = context.active_object

        # Check if the object has any rotation
        if any(abs(angle) > 0.0001 for angle in active_obj.rotation_euler):
            self.report({'WARNING'}, "Operation nur für Objekte ohne Rotation möglich.")
            return {'CANCELLED'}

        original_cursor_location = context.scene.cursor.location.copy()

        # 1. Object mode, 3d cursor to selection.
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.view3d.snap_cursor_to_selected()

        # 2. Editmode alles auswählen und 90° drehung auf der X-Achse
        original_pivot = context.scene.tool_settings.transform_pivot_point
        context.scene.tool_settings.transform_pivot_point = 'CURSOR'

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.transform.rotate(value=math.radians(90), orient_axis='X', orient_type='CURSOR')

        context.scene.tool_settings.transform_pivot_point = original_pivot
        
        # 3. Object mode und drehung -90° auf der X-Achse.
        bpy.ops.object.mode_set(mode='OBJECT')
        active_obj.rotation_euler.x += math.radians(90)

        # Restore cursor
        context.scene.cursor.location = original_cursor_location
        
        self.report({'INFO'}, "Rotation fix applied")
        return {'FINISHED'}

# ---------------------------------------------------------------

def register():
    bpy.utils.register_class(UNITY_OT_quick_export)
    bpy.utils.register_class(UNITY_OT_apply_rotation_fix)

def unregister():
    bpy.utils.unregister_class(UNITY_OT_apply_rotation_fix)
    bpy.utils.unregister_class(UNITY_OT_quick_export)

if __name__ == "__main__":
    register() 