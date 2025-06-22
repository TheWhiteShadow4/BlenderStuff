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

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        scene = context.scene
        unity_props = scene.unity_tool_properties

        if not unity_props.is_path_valid:
            self.report({'ERROR'}, "Unity project path is not valid.")
            return {'CANCELLED'}

        # --- C# Script Handling ---
        # We always write the script to ensure it's up to date with the addon version.
        try:
            editor_script_dir = os.path.join(unity_props.unity_project_path, "Assets", "Editor")
            os.makedirs(editor_script_dir, exist_ok=True)
            editor_script_path = os.path.join(editor_script_dir, "BlenderAssetPostprocessor.cs")
            
            # Get the path of the current script and find the template
            addon_dir = os.path.dirname(os.path.realpath(__file__))
            template_path = os.path.join(addon_dir, "BlenderAssetPostprocessor.cs")

            with open(template_path, 'r') as template_file:
                content = template_file.read()
            
            with open(editor_script_path, "w") as f:
                f.write(content)

        except Exception as e:
            self.report({'ERROR'}, f"Could not create or update editor script: {e}")
            return {'CANCELLED'}

        export_path = os.path.join(unity_props.unity_project_path, unity_props.export_path)

        if not os.path.isdir(export_path):
            try:
                os.makedirs(export_path)
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

        # --- Material Export Logic ---
        if active_obj.active_material:
            mat = active_obj.active_material
            
            # Find the final node connected to the Material Output to act as our interface
            output_node = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
            interface_node = None
            if output_node and output_node.inputs['Surface'].links:
                final_node = output_node.inputs['Surface'].links[0].from_node
                if final_node.type == 'GROUP':
                    interface_node = final_node

            if interface_node:
                # Use the group's internal node_tree name as the shader name
                shader_name = interface_node.node_tree.name
                material_data = {
                    "materialName": mat.name,
                    "shaderName": shader_name,
                    "properties": []
                }
                
                # Iterate through all inputs of the group node
                for input_socket in interface_node.inputs:
                    prop_name = input_socket.name
                    
                    # Convention: Inputs ending with '_Alpha' are helpers and should be ignored.
                    if prop_name.endswith("_Alpha"):
                        continue

                    prop_entry = { "name": prop_name }

                    is_texture_convention = prop_name.lower().endswith("map") or prop_name.lower().endswith("tex")
                    is_color_convention = prop_name.lower().endswith("color")

                    # Determine property type and value based on what the socket is actually connected to
                    if input_socket.is_linked:
                        from_node = input_socket.links[0].from_node

                        # --- Case 1: Connected to an Image Texture node ---
                        if from_node.type == 'TEX_IMAGE':
                            if is_color_convention:
                                self.report({'ERROR'}, f"Input '{prop_name}' follows color convention but is connected to a texture.")
                                continue
                            
                            tex_node = from_node
                            if tex_node.image:
                                prop_entry["type"] = "Texture"
                                source_path = tex_node.image.filepath_from_user()
                                if os.path.exists(source_path):
                                    texture_export_dir = os.path.join(export_path, "Textures")
                                    os.makedirs(texture_export_dir, exist_ok=True)
                                    dest_path = os.path.join(texture_export_dir, os.path.basename(source_path))
                                    shutil.copy(source_path, dest_path)
                                    relative_texture_path = os.path.join(unity_props.export_path, "Textures", os.path.basename(source_path))
                                    prop_entry["path"] = relative_texture_path.replace('\\', '/')
                                else:
                                    self.report({'WARNING'}, f"Texture file not found for '{prop_name}': {source_path}")
                            else:
                                self.report({'WARNING'}, f"Texture node for input '{prop_name}' has no image assigned.")
                                continue
                        
                        # --- Case 2: Connected to an RGB node ---
                        elif from_node.type == 'RGB':
                            if is_texture_convention:
                                self.report({'ERROR'}, f"Input '{prop_name}' follows texture convention but is connected to an RGB Color node.")
                                continue

                            prop_entry["type"] = "Color"
                            color_value = list(from_node.outputs['Color'].default_value)
                            if unity_props.apply_gamma_correction:
                                linear_color = from_node.outputs['Color'].default_value
                                color_value = [
                                    pow(linear_color[0], 1.0/2.2),
                                    pow(linear_color[1], 1.0/2.2),
                                    pow(linear_color[2], 1.0/2.2),
                                    linear_color[3]
                                ]
                            prop_entry["value"] = color_value

                        # --- Case 3: Connected to something else we don't support ---
                        else:
                            self.report({'INFO'}, f"Input '{prop_name}' is connected to an unsupported node type ('{from_node.type}'). It will be ignored.")
                            continue
                    
                    # --- Case 4: The input is not connected, use its default value ---
                    else:
                        if is_texture_convention:
                            self.report({'ERROR'}, f"Input '{prop_name}' follows texture convention but is not connected to an Image Texture node.")
                            continue

                        if input_socket.type == 'RGBA':
                            prop_entry["type"] = "Color"
                            color_value = list(input_socket.default_value)
                            if unity_props.apply_gamma_correction:
                                linear_color = input_socket.default_value
                                color_value = [
                                    pow(linear_color[0], 1.0/2.2),
                                    pow(linear_color[1], 1.0/2.2),
                                    pow(linear_color[2], 1.0/2.2),
                                    linear_color[3]
                                ]
                            prop_entry["value"] = color_value

                        elif input_socket.type == 'VALUE':
                            if is_color_convention:
                                self.report({'ERROR'}, f"Input '{prop_name}' follows color convention but is a Float input, not an RGBA (Color) input.")
                                continue
                            prop_entry["type"] = "Float"
                            prop_entry["floatValue"] = input_socket.default_value
                    
                    # Only add the property if a type was successfully determined
                    if "type" in prop_entry:
                        material_data["properties"].append(prop_entry)

                if material_data["properties"]:
                    json_filepath = filepath + ".b2u.json"
                    try:
                        with open(json_filepath, 'w') as f:
                            json.dump(material_data, f, indent=4)
                        self.report({'INFO'}, f"Exported material data for shader '{shader_name}'")
                    except Exception as e:
                        self.report({'WARNING'}, f"Could not write material json: {e}")

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