# pyright: reportInvalidTypeForm=false
import bpy
import math
import os
import json
import shutil

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
            
        source_path = tex_node.image.filepath_from_user()
        if not os.path.exists(source_path):
            self.report({'WARNING'}, f"Texture file not found: {source_path}")
            return None

        try:
            texture_export_dir = os.path.join(export_path, "Textures")
            os.makedirs(texture_export_dir, exist_ok=True)
            
            dest_path = os.path.join(texture_export_dir, os.path.basename(source_path))
            shutil.copy(source_path, dest_path)
            
            relative_texture_path = os.path.join(unity_props.export_path, "Textures", os.path.basename(source_path))
            return relative_texture_path.replace('\\', '/')
        except Exception as e:
            self.report({'WARNING'}, f"Could not copy texture '{source_path}': {e}")
            return None

    def _process_socket(self, socket, unity_props, export_path):
        """Processes a single node socket and returns a dictionary for the JSON property, or None."""
        prop_name = socket.name
        
        if prop_name.endswith("_Alpha"):
            return None

        is_texture_convention = prop_name.lower().endswith("map") or prop_name.lower().endswith("tex")
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
            if is_texture_convention:
                self.report({'ERROR'}, f"Input '{prop_name}' follows texture convention but is not connected to an Image Texture node.")
                return None

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
        """Finds the active material, processes its properties, and writes the .b2u.json file."""
        if not obj.active_material:
            return

        mat = obj.active_material
        unity_props = context.scene.unity_tool_properties
        
        output_node = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if not (output_node and output_node.inputs['Surface'].links):
            return
            
        interface_node = output_node.inputs['Surface'].links[0].from_node
        if interface_node.type != 'GROUP':
            return

        material_data = {
            "materialName": mat.name,
            "shaderName": interface_node.node_tree.name,
            "properties": []
        }

        for socket in interface_node.inputs:
            prop_entry = self._process_socket(socket, unity_props, export_path)
            if prop_entry:
                material_data["properties"].append(prop_entry)

        if not material_data["properties"]:
            return

        json_filepath = fbx_filepath + ".b2u.json"
        try:
            with open(json_filepath, 'w') as f:
                json.dump(material_data, f, indent=4)
            self.report({'INFO'}, f"Exported material data for shader '{material_data['shaderName']}'")
        except Exception as e:
            self.report({'WARNING'}, f"Could not write material json: {e}")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and get_interface_node(obj)

    def execute(self, context):
        scene = context.scene
        unity_props = scene.unity_tool_properties

        if not unity_props.is_path_valid:
            self.report({'ERROR'}, "Unity project path is not valid.")
            return {'CANCELLED'}

        # --- C# Script Handling ---
        try:
            editor_script_dir = os.path.join(unity_props.unity_project_path, "Assets", "Editor")
            os.makedirs(editor_script_dir, exist_ok=True)
            editor_script_path = os.path.join(editor_script_dir, "BlenderAssetPostprocessor.cs")
            addon_dir = os.path.dirname(os.path.realpath(__file__))
            template_path = os.path.join(addon_dir, "BlenderAssetPostprocessor.cs")
            with open(template_path, 'r') as template_file:
                content = template_file.read()
            with open(editor_script_path, "w") as f:
                f.write(content)
        except Exception as e:
            self.report({'ERROR'}, f"Could not create or update editor script: {e}")
            return {'CANCELLED'}

        # --- FBX Export ---
        export_path = os.path.join(unity_props.unity_project_path, unity_props.export_path)
        try:
            os.makedirs(export_path, exist_ok=True)
        except OSError as e:
            self.report({'ERROR'}, f"Could not create export directory: {e}")
            return {'CANCELLED'}

        active_obj = context.active_object
        filepath = os.path.join(export_path, f"{active_obj.name}.fbx")

        bpy.ops.export_scene.fbx(
            filepath=filepath,
            use_selection=True,
            global_scale=0.01,
            axis_forward='-Z',
            axis_up='Y',
        )

        # --- Material Export ---
        self._handle_material_export(context, active_obj, export_path, filepath)

        self.report({'INFO'}, f"Exported {active_obj.name} to {filepath}")
        return {'FINISHED'}

def get_interface_node(obj):
    """Finds and returns the main interface node group for a given object if it's valid."""
    if not (obj and obj.active_material):
        return None
    mat = obj.active_material
    if not mat.use_nodes:
        return None
    output_node = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
    if not (output_node and output_node.inputs['Surface'].links):
        return None
    interface_node = output_node.inputs['Surface'].links[0].from_node
    return interface_node if interface_node.type == 'GROUP' else None

class UNITY_OT_bake_and_link(bpy.types.Operator):
    """Bakes a procedural input to a texture and links it back to the node group"""
    bl_idname = "unity.bake_and_link"
    bl_label = "Bake Procedural Input"
    bl_options = {'REGISTER', 'UNDO'}

    def get_bake_targets(self, context):
        """
        Finds texture inputs on the node group that are connected to something
        other than a standard Image Texture node (i.e., they are procedurally driven).
        """
        items = []
        interface_node = get_interface_node(context.active_object)
        if not interface_node:
            return items
        
        for socket in interface_node.inputs:
            is_texture_convention = socket.name.lower().endswith("map") or socket.name.lower().endswith("tex")
            if is_texture_convention and socket.is_linked:
                # Check if the source is NOT an image texture, making it a candidate for baking.
                if socket.links[0].from_node.type != 'TEX_IMAGE':
                    items.append((socket.name, socket.name, f"Bake procedural network connected to '{socket.name}'"))
        return items

    def _update_draw(self, context):
        """
        This dummy function's only purpose is to be the 'update' callback
        for bake_mode. Its presence signals to Blender that the UI needs
        to be redrawn when the property changes. This is the standard
        and correct way to solve conditional UI visibility issues in dialogs.
        """
        pass

    target_socket_name: bpy.props.EnumProperty(
        items=get_bake_targets,
        name="Target Input",
        description="The texture input that is currently driven by a procedural network"
    )
    bake_mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ('NEW', "Create New Texture", "Bake to a new image file"),
            ('EXISTING', "Use Existing Texture", "Bake to a pre-existing image datablock"),
        ],
        default='NEW',
        description="Choose whether to create a new texture or overwrite an existing one"
    )
    resolution: bpy.props.IntProperty(
        name="Resolution",
        description="The width and height of the new texture",
        default=2048,
        min=256,
        max=8192
    )
    existing_image_name: bpy.props.StringProperty(
        name="Image",
        description="Select an existing image to bake to"
    )
    uv_map_name: bpy.props.StringProperty(
        name="UV Map",
        description="The UV map to use for baking"
    )

    @classmethod
    def poll(cls, context):
        # We need to make sure there's at least one valid target to bake.
        # The 'self' is not available here, so we have to recreate the logic.
        items = []
        interface_node = get_interface_node(context.active_object)
        if interface_node:
            for socket in interface_node.inputs:
                is_tex = socket.name.lower().endswith("map") or socket.name.lower().endswith("tex")
                if is_tex and socket.is_linked and socket.links[0].from_node.type != 'TEX_IMAGE':
                    items.append(socket.name)
        return len(items) > 0

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "target_socket_name")
        layout.separator()
        
        # UV Map selection (if more than one exists)
        obj = context.active_object
        uv_layers = obj.data.uv_layers if obj and obj.data and hasattr(obj.data, 'uv_layers') else []
        if len(uv_layers) > 1:
            uv_names = [(uv.name, uv.name, "") for uv in uv_layers]
            if not self.uv_map_name:
                self.uv_map_name = uv_layers[0].name
            layout.prop_search(self, "uv_map_name", obj.data, "uv_layers", text="UV Map")
        elif len(uv_layers) == 1:
            self.uv_map_name = uv_layers[0].name

        box = layout.box()
        box.prop(self, "bake_mode")

        if self.bake_mode == 'NEW':
            box.prop(self, "resolution")
        elif self.bake_mode == 'EXISTING':
            # This creates a search field for the bpy.data.images collection.
            box.prop_search(self, "existing_image_name", bpy.data, "images", text="Image")

    def invoke(self, context, event):
        # Set default UV map if not set
        obj = context.active_object
        if obj and obj.data and hasattr(obj.data, 'uv_layers') and len(obj.data.uv_layers) > 0:
            if not self.uv_map_name:
                self.uv_map_name = obj.data.uv_layers[0].name
        return context.window_manager.invoke_props_dialog(self, width=400)

    def _perform_bake(self, context, material, socket_to_bake, obj, uv_map_name, bake_image):
        node_tree = material.node_tree
        # --- Ensure the object is selected and active for baking ---
        prev_active_obj = context.view_layer.objects.active
        prev_selection = [o for o in context.selected_objects]
        if obj not in context.selected_objects:
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
        context.view_layer.objects.active = obj

        # --- Set the correct active UV map for baking ---
        prev_active_uv = None
        if obj and obj.data and hasattr(obj.data, 'uv_layers') and uv_map_name:
            uv_layers = obj.data.uv_layers
            for uv in uv_layers:
                if uv.active:
                    prev_active_uv = uv.name
                uv.active = (uv.name == uv_map_name)

        # --- Find or create the target texture node in the *active* material ---
        bake_target_node = None
        created_nodes = []
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image == bake_image:
                bake_target_node = node
                break
        if not bake_target_node:
            bake_target_node = material.node_tree.nodes.new('ShaderNodeTexImage')
            bake_target_node.image = bake_image
            created_nodes.append(bake_target_node)
        # UV-Node nur bei mehreren UVs
        uv_node = None
        orig_vector_link = None
        if len(obj.data.uv_layers) > 1:
            uv_node = material.node_tree.nodes.new('ShaderNodeUVMap')
            uv_node.uv_map = uv_map_name
            uv_node.location = bake_target_node.location
            uv_node.location.x -= 150
            # Merke evtl. bestehende Vector-Verbindung
            if bake_target_node.inputs['Vector'].is_linked:
                orig_vector_link = bake_target_node.inputs['Vector'].links[0].from_socket
                material.node_tree.links.remove(bake_target_node.inputs['Vector'].links[0])
            material.node_tree.links.new(uv_node.outputs['UV'], bake_target_node.inputs['Vector'])
            created_nodes.append(uv_node)
        # --- Node aktivieren ---
        for n in material.node_tree.nodes: n.select = False
        bake_target_node.select = True
        material.node_tree.nodes.active = bake_target_node
        # --- Temporär umverdrahten, Bake, Restore ---
        output_node = next(n for n in material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
        # Speichere nur die from_sockets, nicht die Link-Objekte selbst!
        original_surface_from_sockets = [l.from_socket for l in output_node.inputs['Surface'].links]
        # Entferne alle Surface-Links und setze temporären Link
        for l in list(output_node.inputs['Surface'].links):
            material.node_tree.links.remove(l)
        material.node_tree.links.new(socket_to_bake, output_node.inputs['Surface'])
        original_engine = context.scene.render.engine
        context.scene.render.engine = 'CYCLES'
        self.report({'INFO'}, f"Baking {obj.name} | {material.name} ...")
        bake_success = True
        try:
            bpy.ops.object.bake(type='EMIT', save_mode='INTERNAL')
        except Exception as e:
            self.report({'ERROR'}, f"Bake failed for {obj.name} | {material.name}: {e}")
            bake_success = False
        context.scene.render.engine = original_engine
        # Restore Surface-Links
        for l in list(output_node.inputs['Surface'].links):
            material.node_tree.links.remove(l)
        for fs in original_surface_from_sockets:
            material.node_tree.links.new(fs, output_node.inputs['Surface'])
        # Restore Vector-Input
        if uv_node and bake_target_node.inputs['Vector'].is_linked:
            material.node_tree.links.remove(bake_target_node.inputs['Vector'].links[0])
        if orig_vector_link:
            material.node_tree.links.new(orig_vector_link, bake_target_node.inputs['Vector'])
        # Entferne temporäre Nodes, falls Bake fehlgeschlagen
        if not bake_success:
            for node in created_nodes:
                material.node_tree.nodes.remove(node)
        # --- Restore previous active UV map ---
        if prev_active_uv and obj and obj.data and hasattr(obj.data, 'uv_layers'):
            for uv in obj.data.uv_layers:
                uv.active = (uv.name == prev_active_uv)
        # --- Restore previous selection and active object ---
        if prev_active_obj:
            context.view_layer.objects.active = prev_active_obj
        for o in context.selected_objects:
            o.select_set(False)
        for o in prev_selection:
            o.select_set(True)
        return bake_target_node if bake_success else None

    def execute(self, context):
        # Multi-Objekt-Unterstützung
        objs = [o for o in context.selected_objects if o.type == 'MESH']
        if not objs:
            self.report({'ERROR'}, "No mesh objects selected.")
            return {'CANCELLED'}
        # Bake-Parameter
        bake_mode = self.bake_mode
        resolution = self.resolution
        existing_image_name = self.existing_image_name
        uv_map_name = self.uv_map_name
        # --- Merke und setze hide_render-Status ---
        prev_hide_render = {obj: obj.hide_render for obj in objs}
        for obj in objs:
            obj.hide_render = False
        try:
            all_dummy_nodes = []  # (mat, node) Paare zum späteren Entfernen
            # Für alle Objekte und alle passenden Materialien:
            for obj in objs:
                interface_node = get_interface_node(obj)
                if not interface_node:
                    self.report({'WARNING'}, f"No valid node group found for object '{obj.name}'. Skipping.")
                    continue
                if not self.target_socket_name:
                    self.report({'ERROR'}, f"Kein Ziel-Input ausgewählt für Objekt '{obj.name}'.")
                    continue
                if self.target_socket_name not in interface_node.inputs:
                    self.report({'WARNING'}, f"Input '{self.target_socket_name}' existiert nicht im Interface-Node von '{obj.name}'. Überspringe Objekt.")
                    continue
                # Zielbild vorbereiten (ein Bild pro Objekt reicht)
                if bake_mode == 'NEW':
                    bake_image_name = f"{obj.name}_{interface_node.name}_{self.target_socket_name}_Baked"
                    bake_image = bpy.data.images.new(
                        name=bake_image_name,
                        width=resolution,
                        height=resolution
                    )
                elif bake_mode == 'EXISTING':
                    if not existing_image_name:
                        self.report({'ERROR'}, "No existing image selected for baking.")
                        continue
                    bake_image = bpy.data.images.get(existing_image_name)
                    if not bake_image:
                        self.report({'ERROR'}, f"Could not find an image named '{existing_image_name}'.")
                        continue
                group_tree = interface_node.node_tree
                # --- Material-Schleife ---
                for mat_slot in obj.material_slots:
                    mat = mat_slot.material
                    if not mat:
                        continue

                    # --- Sicherstellen, dass ein Image-Node mit bake_image existiert (vor evtl. Bake) ---
                    has_bake_node = any(n.type == 'TEX_IMAGE' and n.image == bake_image for n in mat.node_tree.nodes)
                    if not has_bake_node:
                        dummy_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
                        dummy_node.image = bake_image
                        dummy_node.label = "BakeDummy"
                        for n in mat.node_tree.nodes:
                            n.select = False
                        dummy_node.select = True
                        mat.node_tree.nodes.active = dummy_node
                        all_dummy_nodes.append((mat, dummy_node))

                    # --- Prüfen, ob dieses Material die NodeGroup und den Socket enthält ---
                    mat_interface_node = None
                    for n in mat.node_tree.nodes:
                        if n.type == 'GROUP' and n.node_tree == group_tree:
                            mat_interface_node = n
                            break
                    if not mat_interface_node or self.target_socket_name not in mat_interface_node.inputs:
                        # Kein Bake nötig / möglich
                        continue

                    mat_target_socket = mat_interface_node.inputs[self.target_socket_name]
                    mat_orig_link = mat_target_socket.links[0] if mat_target_socket.is_linked else None

                    # --- Entscheiden, ob wir in diesem Material backen müssen ---
                    is_procedural = mat_target_socket.is_linked and mat_target_socket.links[0].from_node.type != 'TEX_IMAGE'

                    if not is_procedural:
                        continue  # Socket ist bereits Textur, kein Bake nötig

                    # --- Actual Bake ---
                    socket_to_bake = mat_target_socket.links[0].from_socket
                    bake_target_node = self._perform_bake(context, mat, socket_to_bake, obj, uv_map_name, bake_image)
                    # Links ersetzen
                    if mat_orig_link:
                        mat.node_tree.links.remove(mat_orig_link)
                    if bake_target_node:
                        mat.node_tree.links.new(bake_target_node.outputs['Color'], mat_target_socket)
                    else:
                        # Rollback bei Bake-Fehler
                        if mat_orig_link:
                            mat.node_tree.links.new(mat_orig_link.from_socket, mat_target_socket)
        finally:
            # --- Dummy-Nodes entfernen ---
            for mat, node in all_dummy_nodes:
                try:
                    if node.name in mat.node_tree.nodes:
                        mat.node_tree.nodes.remove(mat.node_tree.nodes[node.name])
                except Exception:
                    # Node wurde bereits gelöscht oder ist nicht mehr gültig
                    pass
            # --- Restore hide_render-Status ---
            for obj, prev in prev_hide_render.items():
                obj.hide_render = prev
        self.report({'INFO'}, "Baking completed for all selected objects.")
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

def register():
    bpy.utils.register_class(UNITY_OT_quick_export)
    bpy.utils.register_class(UNITY_OT_bake_and_link)
    bpy.utils.register_class(UNITY_OT_apply_rotation_fix)

def unregister():
    bpy.utils.unregister_class(UNITY_OT_apply_rotation_fix)
    bpy.utils.unregister_class(UNITY_OT_bake_and_link)
    bpy.utils.unregister_class(UNITY_OT_quick_export)

if __name__ == "__main__":
    register() 