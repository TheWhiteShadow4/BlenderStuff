# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
import math
import os
import json
import shutil
from . import baker
from . import constants
from . import material_export
from . import hair_particle_converter
from .rotation_fix_settings import RotationFixSettings

class UNITY_OT_quick_export(bpy.types.Operator):
	"""Quick export selected object to Unity project"""
	bl_idname = "unity.quick_export"
	bl_label = "Quick Export"
	bl_options = {'REGISTER', 'UNDO'}

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
		material_export.export_materials(context, active_obj, export_path, filepath, self)

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
        merged_collection = None
        collection_was_created = False
        hair_objects_created = []  # Initialisieren für Cleanup im Fehlerfall
        
        try:
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
                collection_was_created = True
            
            # BUGFIX: Collection in Layer Collection aktivieren
            # Finde die Layer Collection für diese Collection
            def find_layer_collection(layer_collection, name):
                if layer_collection.collection.name == name:
                    return layer_collection
                for child in layer_collection.children:
                    result = find_layer_collection(child, name)
                    if result:
                        return result
                return None
            
            layer_collection = find_layer_collection(context.view_layer.layer_collection, merged_collection_name)
            if layer_collection:
                # Collection aktivieren (sichtbar machen)
                layer_collection.exclude = False
            else:
                raise RuntimeError(f"Layer Collection '{merged_collection_name}' konnte nicht gefunden werden")
            
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
            
            # 4. Hair-Partikel konvertieren (nach dem Kopieren)
            # Die konvertierten Objekte werden direkt in der merged_collection erstellt
            hair_converter = hair_particle_converter.HairParticleConverter(self.report)
            
            for obj in list(objects_to_process):  # list() weil wir während der Iteration hinzufügen
                if hair_converter.has_hair_particles(obj):
                    try:
                        converted_objects = hair_converter.convert_hair_particles(context, obj)
                        # Konvertierte Objekte zur merged_collection hinzufügen
                        for hair_obj in converted_objects:
                            if not hair_obj:
                                continue
                            
                            # Objekt aus allen anderen Collections entfernen
                            for col in hair_obj.users_collection:
                                col.objects.unlink(hair_obj)
                            
                            # Zur merged_collection hinzufügen
                            if hair_obj.name not in merged_collection.objects:
                                merged_collection.objects.link(hair_obj)
                                objects_to_process.append(hair_obj)
                        
                        hair_objects_created.extend(converted_objects)
                        self.report({'INFO'}, f"Hair-Partikel von '{obj.name}' konvertiert: {len(converted_objects)} Objekte erstellt")
                    except Exception as e:
                        self.report({'WARNING'}, f"Fehler beim Konvertieren der Hair-Partikel von '{obj.name}': {e}")
            
            # 5. Modifier anwenden (von oben nach unten, außer Armature)
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
            
            # 6. Alle Nicht-Meshes zu Meshes konvertieren
            converted_count = 0
            for obj in objects_to_process:
                if obj.type != 'MESH':
                    # Objekt selektieren für die Konvertierung
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.select_all(action='DESELECT')
                    obj.select_set(True)
                    
                    # Objekttyp merken für spätere Behandlung
                    original_type = obj.type
                    
                    try:
                        # Je nach Objekttyp konvertieren
                        if obj.type in ['CURVE', 'SURFACE', 'META', 'FONT']:
                            bpy.ops.object.convert(target='MESH')
                            converted_count += 1
                            
                            # Smooth Shading für konvertierte Curves (z.B. Hair-Partikel)
                            if original_type == 'CURVE' and bpy.context.active_object and bpy.context.active_object.type == 'MESH':
                                bpy.ops.object.shade_smooth()
                        elif obj.type == 'GPENCIL':
                            # Grease Pencil zu Mesh konvertieren ist komplexer
                            bpy.ops.gpencil.convert(type='CURVE')
                            bpy.ops.object.convert(target='MESH')
                            converted_count += 1
                        # Andere Typen wie EMPTY, LIGHT, CAMERA etc. bleiben unverändert
                    except Exception as e:
                        self.report({'WARNING'}, f"Konnte {obj.name} ({obj.type}) nicht konvertieren: {e}")
            
            # 7. Mono Animation Objects verarbeiten (falls aktiviert)
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
            
            # 8. Alle Mesh-Objekte zu einem einzigen Objekt mergen
            mesh_objects = [obj for obj in merged_collection.objects if obj.type == 'MESH']
            
            if len(mesh_objects) > 1:
                # Alle Mesh-Objekte selektieren
                bpy.ops.object.select_all(action='DESELECT')
                for obj in mesh_objects:
                    obj.select_set(True)
                
                # Das erste Mesh-Objekt als aktives setzen
                if mesh_objects:
                    bpy.context.view_layer.objects.active = mesh_objects[0]
                    
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
            
        except Exception as e:
            # BUGFIX: Bei Fehler die Ziel-Collection aufräumen
            self.report({'ERROR'}, f"Fehler beim Mergen der Collection: {e}")
            
            # Alle Objekte aus der merged collection entfernen und löschen
            # (inkl. konvertierte Hair-Objekte, die bereits in der Collection sind)
            if merged_collection:
                objects_to_cleanup = list(merged_collection.objects)
                for obj in objects_to_cleanup:
                    try:
                        merged_collection.objects.unlink(obj)
                        bpy.data.objects.remove(obj, do_unlink=True)
                    except Exception as cleanup_error:
                        self.report({'WARNING'}, f"Konnte Objekt {obj.name} nicht aufräumen: {cleanup_error}")
                
                # Collection selbst löschen, falls sie neu erstellt wurde
                if collection_was_created:
                    try:
                        context.scene.collection.children.unlink(merged_collection)
                        bpy.data.collections.remove(merged_collection)
                    except Exception as cleanup_error:
                        self.report({'WARNING'}, f"Konnte Collection nicht entfernen: {cleanup_error}")
            
            return {'CANCELLED'}
        
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