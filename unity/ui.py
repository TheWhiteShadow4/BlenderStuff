# pyright: reportInvalidTypeForm=false
import bpy


class UNITY_PT_main_panel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport"""
    bl_label = "Unity Tools"
    bl_idname = "UNITY_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Unity'

    def draw(self, context):
        layout = self.layout

        # Reload button
        row = layout.row()
        row.operator("script.reload", text="Reload Addon", icon='FILE_REFRESH')

        scene = context.scene
        unity_props = scene.unity_tool_properties

        # Section for Operators
        box = layout.box()
        row = box.row()
        row.operator("unity.apply_rotation_fix", text="Fix Rotation for Unity")
        row = box.row()
        row.operator("unity.quick_export", text="Quick Export")

        # Section for Settings
        box = layout.box()
        box.label(text="Unity Settings")
        row = box.row()
        row.prop(unity_props, "unity_project_path", text="Project")

        if unity_props.unity_version:
            row = box.row()
            row.label(text=f"Version: {unity_props.unity_version}", icon='INFO')

        if unity_props.unity_project_path and not unity_props.is_path_valid:
            row = box.row()
            row.alert = True
            row.label(text="Invalid Unity Project Path", icon='ERROR')

        row = box.row()
        row.prop(unity_props, "export_path", text="Export Path")

        row = box.row()
        row.prop(unity_props, "apply_gamma_correction")

        #row = box.row()
        #row.prop(unity_props, "unity_executable_path", text="Unity Executable")


def register():
    bpy.utils.register_class(UNITY_PT_main_panel)

def unregister():
    bpy.utils.unregister_class(UNITY_PT_main_panel)

if __name__ == "__main__":
    register() 