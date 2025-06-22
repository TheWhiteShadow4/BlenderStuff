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
        scene = context.scene
        unity_props = scene.unity_tool_properties

        # Section for Operators
        box = layout.box()
        row = box.row()
        row.operator("unity.apply_rotation_fix", text="Fix Rotation for Unity")

        # Section for Settings
        box = layout.box()
        box.label(text="Settings")
        row = box.row()
        row.prop(unity_props, "unity_project_path", text="")


def register():
    bpy.utils.register_class(UNITY_PT_main_panel)

def unregister():
    bpy.utils.unregister_class(UNITY_PT_main_panel)

if __name__ == "__main__":
    register() 