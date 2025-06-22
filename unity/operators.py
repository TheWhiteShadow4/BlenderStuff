# pyright: reportInvalidTypeForm=false
import bpy
import math
import os

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

        editor_script_dir = os.path.join(unity_props.unity_project_path, "Assets", "Editor")
        editor_script_path = os.path.join(editor_script_dir, "BlenderAssetPostprocessor.cs")

        if not os.path.exists(editor_script_path):
            try:
                os.makedirs(editor_script_dir, exist_ok=True)
                
                # Get the path of the current script and find the template
                addon_dir = os.path.dirname(os.path.realpath(__file__))
                template_path = os.path.join(addon_dir, "BlenderAssetPostprocessor.cs.template")

                with open(template_path, 'r') as template_file:
                    content = template_file.read()
                
                with open(editor_script_path, "w") as f:
                    f.write(content)

            except Exception as e:
                self.report({'ERROR'}, f"Could not create editor script: {e}")
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

        # Create a marker file so the Unity AssetPostprocessor knows to modify this file.
        try:
            marker_filepath = filepath + ".b2u"
            with open(marker_filepath, 'w') as f:
                pass # Just create an empty file
        except Exception as e:
            self.report({'WARNING'}, f"Could not create marker file: {e}")

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