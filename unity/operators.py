# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
import math
import os
import json
import shutil
from . import baker
from . import constants
from .rotation_fix_settings import RotationFixSettings

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
			pow(color[0], 1.0/constants.GAMMA_CORRECTION_FACTOR),
			pow(color[1], 1.0/constants.GAMMA_CORRECTION_FACTOR),
			pow(color[2], 1.0/constants.GAMMA_CORRECTION_FACTOR),
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

			relative_texture_path = os.path.join(unity_props.export_path, constants.TEXTURE_EXPORT_DIR, os.path.basename(dest_path))
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
				self.report({'ERROR'}, f"Input '{prop_name}' follows texture convention but is connected to an RGB Color node.")
				return None
			elif from_node.type == 'VALUE':
				self.report({'ERROR'}, f"Input '{prop_name}' follows texture convention but is connected to a Value node.")
				return None
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

			# Skip materials without proper node setup
			if not mat.node_tree or not mat.node_tree.nodes:
				self.report({'INFO'}, f"Material '{mat.name}' has no node tree, skipping")
				continue

			# Find interface node inside this material
			output_node = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
			if not (output_node and output_node.inputs['Surface'].links):
				self.report({'INFO'}, f"Material '{mat.name}' has no valid output connection, skipping")
				continue
			
			interface_node = output_node.inputs['Surface'].links[0].from_node

			# Check if this is a supported shader node (with node_tree attribute)
			if not hasattr(interface_node, 'node_tree') or not interface_node.node_tree:
				self.report({'INFO'}, f"Material '{mat.name}' uses unsupported node type '{interface_node.type}', exporting material reference only")
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
					prop_entry = self._process_socket(socket, unity_props, export_path)
					if prop_entry:
						material_data["properties"].append(prop_entry)
			except Exception as e:
				self.report({'WARNING'}, f"Error processing material '{mat.name}': {e}. Material reference exported.")

			# Add material data (even if properties list is empty, so Unity knows the material name)
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
				global_scale=constants.UNITY_FBX_SCALE,
				axis_forward=constants.UNITY_AXIS_FORWARD,
				axis_up=constants.UNITY_AXIS_UP,
			)
		elif engine == 'GODOT':
			bpy.ops.export_scene.fbx(
				filepath=filepath,
				use_selection=True,
				global_scale=constants.GODOT_FBX_SCALE,
				axis_forward=constants.GODOT_AXIS_FORWARD,
				axis_up=constants.GODOT_AXIS_UP,
			)

		# --- Material Export ---
		# Cache für bereits exportierte Texturen leeren
		self._texture_cache = {}
		self._handle_material_export(context, active_obj, export_path, filepath)

		self.report({'INFO'}, f"Exported {active_obj.name} to {filepath}")
		return {'FINISHED'}

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
        if any(abs(angle) > constants.ROTATION_TOLERANCE for angle in active_obj.rotation_euler):
            self.report({'WARNING'}, "Operation nur für Objekte ohne Rotation möglich.")
            return {'CANCELLED'}

        # Use simple, specific settings manager for rotation fix
        with RotationFixSettings(context):
            # 1. Object mode, 3d cursor to selection.
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.view3d.snap_cursor_to_selected()

            # 2. Editmode alles auswählen und 90° drehung auf der X-Achse
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.transform.rotate(value=math.radians(90), orient_axis='X', orient_type='CURSOR')
            
            # 3. Object mode und drehung -90° auf der X-Achse.
            bpy.ops.object.mode_set(mode='OBJECT')
            active_obj.rotation_euler.x += math.radians(90)

        # Settings are automatically restored
        self.report({'INFO'}, "Rotation fix applied")
        return {'FINISHED'}

class UNITY_OT_merge_objects(bpy.types.Operator):
    """Merge objects from selected collection"""
    bl_idname = "unity.merge_objects"
    bl_label = "Merge Collection Objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def _safe_name_check(self, name, data_collection):
        """Sichere Überprüfung ob ein Name in einer Blender-Datensammlung existiert"""
        try:
            return name in data_collection
        except (UnicodeError, KeyError):
            # Bei Unicode-Problemen durch alle Namen iterieren
            for existing_name in data_collection.keys():
                if existing_name == name:
                    return True
            return False
    
    def _get_mono_bone_name(self, obj):
        """Ermittelt den Bone-Namen für ein Mono Animation Object, falls vorhanden"""
        # 1. Prüfe ob Objekt einen Bone als Parent hat
        if obj.parent and obj.parent.type == 'ARMATURE' and obj.parent_bone:
            return obj.parent_bone
        
        # 2. Prüfe Armature Modifier mit vertex group
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.vertex_group:
                return modifier.vertex_group
        
        return None
    
    def _is_mono_animation_object(self, obj):
        """Prüft ob ein Objekt ein Mono Animation Object ist"""
        if obj.type != 'MESH':
            return False
        
        return self._get_mono_bone_name(obj) is not None
    
    def _process_mono_animation_object(self, obj):
        """Verarbeitet ein Mono Animation Object"""
        bone_name = self._get_mono_bone_name(obj)
        if not bone_name:
            return
        
        # 1. Objekt-Daten vereinzeln (make single-user)
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        
        # 2. Vertex-Gruppe für den Bone erstellen falls nicht vorhanden
        if bone_name not in obj.vertex_groups:
            vertex_group = obj.vertex_groups.new(name=bone_name)
        else:
            vertex_group = obj.vertex_groups[bone_name]
        
        # 3. Alle Vertices zu 100% dieser Vertex-Gruppe zuweisen
        # Alle Vertices des Mesh ermitteln
        vertex_indices = [v.index for v in obj.data.vertices]
        
        if vertex_indices:
            # Vertices zur Gruppe hinzufügen (überschreibt bestehende Gewichtung für diese Gruppe)
            vertex_group.add(vertex_indices, 1.0, 'REPLACE')
    
    # Property für die Collection-Auswahl
    collection_name: bpy.props.StringProperty(
        name="Collection",
        description="Collection to merge objects from"
    )
    
    # Liste aller verfügbaren Collections als Enum
    def get_collections_enum(self, context):
        active_obj = context.active_object
        if not active_obj:
            return [('NONE', "No active object", "")]
        
        # Finde alle Collections die das aktive Objekt enthalten
        collections = []
        collection_index = 0
        
        for collection in bpy.data.collections:
            # Sicher prüfen ob das Objekt in der Collection ist
            try:
                if active_obj.name in collection.objects:
                    # ASCII-safe identifier verwenden, aber originalen Namen für Anzeige
                    safe_id = f"COLLECTION_{collection_index}"
                    collections.append((safe_id, collection.name, f"Merge objects from {collection.name}"))
                    collection_index += 1
            except (UnicodeError, KeyError):
                # Bei Unicode-Problemen manuell durch Objekte iterieren
                for obj in collection.objects:
                    if obj == active_obj:
                        safe_id = f"COLLECTION_{collection_index}"
                        collections.append((safe_id, collection.name, f"Merge objects from {collection.name}"))
                        collection_index += 1
                        break
        
        if not collections:
            return [('NONE', "No collections found", "")]
            
        return collections
    
    selected_collection: bpy.props.EnumProperty(
        name="Select Collection",
        description="Choose which collection to merge",
        items=get_collections_enum
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None
    
    def invoke(self, context, event):
        # Popup Dialog für Collection-Auswahl anzeigen
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "selected_collection")
    
    def execute(self, context):
        active_obj = context.active_object
        
        if self.selected_collection == 'NONE':
            self.report({'ERROR'}, "Kein gültiges Objekt oder keine Collections gefunden")
            return {'CANCELLED'}
        
        # 1. Gewählte Collection anhand der ID finden
        source_collection = None
        collection_index = 0
        
        # Collection anhand des safe_id zurückfinden
        for collection in bpy.data.collections:
            try:
                if active_obj.name in collection.objects:
                    safe_id = f"COLLECTION_{collection_index}"
                    if safe_id == self.selected_collection:
                        source_collection = collection
                        break
                    collection_index += 1
            except (UnicodeError, KeyError):
                for obj in collection.objects:
                    if obj == active_obj:
                        safe_id = f"COLLECTION_{collection_index}"
                        if safe_id == self.selected_collection:
                            source_collection = collection
                            break
                        collection_index += 1
                        break
        
        if not source_collection:
            self.report({'ERROR'}, f"Collection nicht gefunden")
            return {'CANCELLED'}
        
        # 2. Neue Collection erstellen mit Namen + "_Merged"
        merged_collection_name = f"{source_collection.name}_Merged"
        
        # Falls bereits eine Collection mit dem Namen existiert, wiederverwenden
        if self._safe_name_check(merged_collection_name, bpy.data.collections):
            merged_collection = bpy.data.collections[merged_collection_name]
            
            # Alle bestehenden Objekte aus der Collection entfernen
            objects_to_remove = list(merged_collection.objects)
            for obj in objects_to_remove:
                merged_collection.objects.unlink(obj)
                # Objekt komplett aus der Szene löschen falls es in keiner anderen Collection ist
                if not any(obj.name in col.objects for col in bpy.data.collections if col != merged_collection):
                    bpy.data.objects.remove(obj)
        else:
            # Neue Collection erstellen
            merged_collection = bpy.data.collections.new(merged_collection_name)
            context.scene.collection.children.link(merged_collection)
        
        # 3. Alle Objekte aus der Source Collection kopieren
        objects_to_process = []
        for obj in source_collection.objects:
            # Objekt duplizieren
            new_obj = obj.copy()
            if obj.data:
                new_obj.data = obj.data.copy()
            
            # Zur neuen Collection hinzufügen
            merged_collection.objects.link(new_obj)
            objects_to_process.append(new_obj)
        
        # 4. Modifier anwenden (von oben nach unten, außer Armature)
        modifier_applied_count = 0
        for obj in objects_to_process:
            if obj.type == 'MESH' and obj.modifiers:
                # Objekt aktivieren für Modifier-Operationen
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                
                # Modifier von oben nach unten durchgehen, nur sichtbare anwenden
                modifiers_to_apply = []
                modifiers_to_remove = []
                for modifier in obj.modifiers:
                    if modifier.type != 'ARMATURE':
                        if modifier.show_viewport:
                            # Sichtbare Modifier werden angewendet
                            modifiers_to_apply.append(modifier.name)
                        else:
                            # Unsichtbare Modifier werden verworfen
                            modifiers_to_remove.append(modifier.name)
                
                # Modifier anwenden
                for mod_name in modifiers_to_apply:
                    try:
                        bpy.ops.object.modifier_apply(modifier=mod_name)
                        modifier_applied_count += 1
                    except Exception as e:
                        self.report({'WARNING'}, f"Konnte Modifier '{mod_name}' auf {obj.name} nicht anwenden: {e}")
                
                # Unsichtbare Modifier entfernen
                for mod_name in modifiers_to_remove:
                    try:
                        bpy.ops.object.modifier_remove(modifier=mod_name)
                    except Exception as e:
                        self.report({'WARNING'}, f"Konnte Modifier '{mod_name}' auf {obj.name} nicht entfernen: {e}")
        
        # 5. Alle Nicht-Meshes zu Meshes konvertieren
        converted_count = 0
        for obj in objects_to_process:
            if obj.type != 'MESH':
                # Objekt selektieren für die Konvertierung
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                
                try:
                    # Je nach Objekttyp konvertieren
                    if obj.type in ['CURVE', 'SURFACE', 'META', 'FONT']:
                        bpy.ops.object.convert(target='MESH')
                        converted_count += 1
                    elif obj.type == 'GPENCIL':
                        # Grease Pencil zu Mesh konvertieren ist komplexer
                        bpy.ops.gpencil.convert(type='CURVE')
                        bpy.ops.object.convert(target='MESH')
                        converted_count += 1
                    # Andere Typen wie EMPTY, LIGHT, CAMERA etc. bleiben unverändert
                except Exception as e:
                    self.report({'WARNING'}, f"Konnte {obj.name} ({obj.type}) nicht konvertieren: {e}")
        
        # 6. Mono Animation Objects verarbeiten (falls aktiviert)
        unity_props = context.scene.unity_tool_properties
        mono_objects_processed = 0
        
        if unity_props.isolate_mono_animation_objects:
            for obj in objects_to_process:
                if self._is_mono_animation_object(obj):
                    try:
                        self._process_mono_animation_object(obj)
                        mono_objects_processed += 1
                    except Exception as e:
                        self.report({'WARNING'}, f"Konnte Mono Animation Object {obj.name} nicht verarbeiten: {e}")
        
        # 7. Alle Mesh-Objekte zu einem einzigen Objekt mergen
        mesh_objects = [obj for obj in merged_collection.objects if obj.type == 'MESH']
        
        if len(mesh_objects) > 1:
            # Alle Mesh-Objekte selektieren
            bpy.ops.object.select_all(action='DESELECT')
            for obj in mesh_objects:
                obj.select_set(True)
            
            # Das erste Mesh-Objekt als aktives setzen
            if mesh_objects:
                bpy.context.view_layer.objects.active = mesh_objects[0]
                
                try:
                    # Alle selektierten Objekte zu einem vereinigen
                    bpy.ops.object.join()
                    merged_obj = bpy.context.active_object
                    
                    # Namen des ursprünglichen Collections verwenden falls verfügbar
                    desired_name = source_collection.name
                    if not self._safe_name_check(desired_name, bpy.data.objects):
                        merged_obj.name = desired_name
                        # Auch das Mesh umbenennen falls der Name verfügbar ist
                        if merged_obj.data and not self._safe_name_check(desired_name, bpy.data.meshes):
                            merged_obj.data.name = desired_name
                        else:
                            merged_obj.data.name = f"{desired_name}_Mesh"
                    else:
                        merged_obj.name = f"{desired_name}_Merged"
                        if merged_obj.data:
                            merged_obj.data.name = f"{desired_name}_Merged_Mesh"
                    
                    self.report({'INFO'}, f"Collection '{merged_collection_name}' erstellt. {len(objects_to_process)} Objekte zu einem Mesh gemerged. {mono_objects_processed} Mono Animation Objects verarbeitet, {modifier_applied_count} Modifier angewendet, {converted_count} Objekte zu Mesh konvertiert.")
                except Exception as e:
                    self.report({'ERROR'}, f"Fehler beim Mergen der Objekte: {e}")
                    return {'CANCELLED'}
        elif len(mesh_objects) == 1:
            # Nur ein Mesh-Objekt vorhanden, umbenennen
            single_obj = mesh_objects[0]
            desired_name = source_collection.name
            if not self._safe_name_check(desired_name, bpy.data.objects):
                single_obj.name = desired_name
                # Auch das Mesh umbenennen falls der Name verfügbar ist
                if single_obj.data and not self._safe_name_check(desired_name, bpy.data.meshes):
                    single_obj.data.name = desired_name
                else:
                    single_obj.data.name = f"{desired_name}_Mesh"
            else:
                single_obj.name = f"{desired_name}_Merged"
                if single_obj.data:
                    single_obj.data.name = f"{desired_name}_Merged_Mesh"
            
            self.report({'INFO'}, f"Collection '{merged_collection_name}' erstellt mit einem Objekt. {mono_objects_processed} Mono Animation Objects verarbeitet, {modifier_applied_count} Modifier angewendet, {converted_count} Objekte zu Mesh konvertiert.")
        else:
            # Keine Mesh-Objekte vorhanden
            self.report({'WARNING'}, f"Collection '{merged_collection_name}' erstellt, aber keine Mesh-Objekte zum Mergen gefunden.")
        
        # Aktives Objekt zurücksetzen
        bpy.context.view_layer.objects.active = active_obj
        
        return {'FINISHED'}

# ---------------------------------------------------------------

def register():
    bpy.utils.register_class(UNITY_OT_quick_export)
    bpy.utils.register_class(UNITY_OT_apply_rotation_fix)
    bpy.utils.register_class(UNITY_OT_merge_objects)

def unregister():
    bpy.utils.unregister_class(UNITY_OT_apply_rotation_fix)
    bpy.utils.unregister_class(UNITY_OT_quick_export)
    bpy.utils.unregister_class(UNITY_OT_merge_objects)

if __name__ == "__main__":
    register() 