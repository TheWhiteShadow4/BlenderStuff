# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy

class UNITY_PT_animation_panel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport for Animation Tools"""
    bl_label = "Animation Tools"
    bl_idname = "UNITY_PT_animation_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Game Tools'
    bl_parent_id = "UNITY_PT_main_panel"

    def draw(self, context):
        layout = self.layout
        cloth_props = context.scene.unity_cloth_rig_properties

        box = layout.box()
        row = box.row()
        row.prop(cloth_props, "mode", expand=True)
        row = box.row()
        row.prop(cloth_props, "nth")
        if cloth_props.mode == 'FACES':
            row = box.row()
            row.prop(cloth_props, "copy_rotation")
        
        # Vertex Group selection
        row = box.row()
        row.prop_search(cloth_props, "vertex_group", context.active_object, "vertex_groups", text="Vertex Group")
        
        # Target Armature selection
        row = box.row()
        row.prop(cloth_props, "target_armature", text="Target Armature")
        
        # Clean Weights option (only show if target armature is specified)
        row = box.row()
        row.prop(cloth_props, "clean_weights")
        
        row = box.row()
        row.operator("unity.rig_cloth", text="Add Rig to Surface")

def register():
    bpy.utils.register_class(UNITY_PT_animation_panel)

def unregister():
    bpy.utils.unregister_class(UNITY_PT_animation_panel) 