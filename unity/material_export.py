# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
"""Material export functions for Unity/Godot."""

import os
import json
import shutil
from . import constants


def correct_color(color, apply_gamma):
	"""Applies gamma correction to a color if the flag is set."""
	if not apply_gamma:
		return list(color)
	# Convert Linear to sRGB color space for Unity.
	return [
		pow(color[0], 1.0/constants.GAMMA_CORRECTION_FACTOR),
		pow(color[1], 1.0/constants.GAMMA_CORRECTION_FACTOR),
		pow(color[2], 1.0/constants.GAMMA_CORRECTION_FACTOR),
		color[3] # Alpha is linear
	]


def copy_texture_and_get_path(tex_node, unity_props, export_path, operator, texture_cache):
	"""Copies a texture to the export directory and returns its relative path for Unity."""
	if not tex_node.image:
		operator.report({'WARNING'}, f"Texture node '{tex_node.name}' has no image assigned.")
		return None
		
	# Duplicate-copy prevention via instance cache
	cached_path = texture_cache.get(tex_node.image.name)
	if cached_path:
		return cached_path

	# Zielverzeichnis vorbereiten
	texture_export_dir = os.path.join(export_path, constants.TEXTURE_EXPORT_DIR)
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
				operator.report({'WARNING'}, f"Texture file not found: {source_path}")
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

		relative_texture_path = os.path.join(unity_props.export_path, constants.TEXTURE_EXPORT_DIR, os.path.basename(dest_path))
		relative_texture_path = relative_texture_path.replace('\\', '/')
		# Cache merken
		texture_cache[tex_node.image.name] = relative_texture_path
		return relative_texture_path
	except Exception as e:
		operator.report({'WARNING'}, f"Could not copy or save texture '{tex_node.image.name}': {e}")
		return None


def process_socket(socket, unity_props, export_path, operator, texture_cache):
	"""Processes a single node socket and returns a dictionary for the JSON property, or None."""
	prop_name = socket.name
	
	if prop_name.endswith("_Alpha"):
		return None

	is_color_convention = prop_name.lower().endswith("color")
	
	prop_entry = {"name": prop_name}

	# Case 1: Socket is connected to another node
	if socket.is_linked:
		from_node = socket.links[0].from_node

		if from_node.type == 'TEX_IMAGE':
			if is_color_convention:
				operator.report({'ERROR'}, f"Input '{prop_name}' follows color convention but is connected to a texture.")
				return None
			
			tex_path = copy_texture_and_get_path(from_node, unity_props, export_path, operator, texture_cache)
			if tex_path:
				prop_entry["type"] = "Texture"
				prop_entry["path"] = tex_path
			else:
				return None # Error was already reported by the helper

		elif from_node.type == 'RGB':
			operator.report({'ERROR'}, f"Input '{prop_name}' follows texture convention but is connected to an RGB Color node.")
			return None
		elif from_node.type == 'VALUE':
			operator.report({'ERROR'}, f"Input '{prop_name}' follows texture convention but is connected to a Value node.")
			return None
		else:
			operator.report({'INFO'}, f"Input '{prop_name}' is connected to an unsupported node type ('{from_node.type}'). It will be ignored.")
			return None
	
	# Case 2: Socket is not connected, use its default value
	else:
		if socket.type == 'RGBA':
			prop_entry["type"] = "Color"
			color = socket.default_value
			prop_entry["value"] = correct_color(color, unity_props.apply_gamma_correction)

		elif socket.type == 'VALUE':
			if is_color_convention:
				operator.report({'ERROR'}, f"Input '{prop_name}' follows color convention but is a Float, not RGBA.")
				return None
			prop_entry["type"] = "Float"
			prop_entry["floatValue"] = socket.default_value
		
		else: # Other unlinked socket types we don't handle
			return None

	return prop_entry


def export_materials(context, obj, export_path, fbx_filepath, operator):
	"""Exports ALL materials of the given object into a single *.imp.json file."""
	unity_props = context.scene.unity_tool_properties
	materials_data = []
	texture_cache = {}

	# Iterate over every material slot on the object
	for mat_slot in obj.material_slots:
		mat = mat_slot.material
		if not mat:
			continue

		# Skip materials without proper node setup
		if not mat.node_tree or not mat.node_tree.nodes:
			operator.report({'INFO'}, f"Material '{mat.name}' has no node tree, skipping")
			continue

		# Find interface node inside this material
		output_node = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
		if not (output_node and output_node.inputs['Surface'].links):
			operator.report({'INFO'}, f"Material '{mat.name}' has no valid output connection, skipping")
			continue
		
		interface_node = output_node.inputs['Surface'].links[0].from_node

		# Check if this is a supported shader node (with node_tree attribute)
		if not hasattr(interface_node, 'node_tree') or not interface_node.node_tree:
			operator.report({'INFO'}, f"Material '{mat.name}' uses unsupported node type '{interface_node.type}', exporting material reference only")
			# Export minimal material data so Unity can try to find it by name
			materials_data.append({
				"materialName": mat.name,
				"shaderName": None,  # Unity importer will search for existing material
				"properties": []
			})
			continue

		material_data = {
			"materialName": mat.name,
			"shaderName": interface_node.node_tree.name,
			"properties": []
		}

		try:
			for socket in interface_node.inputs:
				prop_entry = process_socket(socket, unity_props, export_path, operator, texture_cache)
				if prop_entry:
					material_data["properties"].append(prop_entry)
		except Exception as e:
			operator.report({'WARNING'}, f"Error processing material '{mat.name}': {e}. Material reference exported.")

		# Add material data (even if properties list is empty, so Unity knows the material name)
		materials_data.append(material_data)

	# Nothing to export
	if not materials_data:
		return

	json_filepath = fbx_filepath + ".imp.json"
	try:
		with open(json_filepath, 'w') as f:
			json.dump({"materials": materials_data}, f, indent=4)
		operator.report({'INFO'}, f"Exported material data for {len(materials_data)} materials.")
	except Exception as e:
		operator.report({'WARNING'}, f"Could not write material json: {e}")

