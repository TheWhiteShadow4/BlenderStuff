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
        return context.active_object is not None and context.active_object.type == 'MESH'

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
    bpy.utils.register_class(UNITY_OT_apply_rotation_fix)

def unregister():
    bpy.utils.unregister_class(UNITY_OT_apply_rotation_fix)
    bpy.utils.unregister_class(UNITY_OT_quick_export)

if __name__ == "__main__":
    register() 