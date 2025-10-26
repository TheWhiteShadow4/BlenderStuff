# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
from .. import object_cleanups

# ===== UI TEXT CONSTANTS =====
# Main Panel
MAIN_PANEL_LABEL = "Unity Tools"
MAIN_PANEL_CATEGORY = "Game Tools"
RELOAD_ADDON_TEXT = "Reload Addon"
FIX_ROTATION_TEXT = "Fix Rotation for Unity"
QUICK_EXPORT_TEXT = "Quick Export"
MERGE_OBJECTS_SECTION = "Merge Objects"
MERGE_COLLECTION_TEXT = "Merge Collection"
BAKING_SECTION = "Baking"
BAKE_ACTIVE_PRESETS_TEXT = "Bake Material Presets"
GAME_ENGINE_SETTINGS_SECTION = "Game Engine Settings"
PROJECT_TEXT = "Project"
VERSION_TEXT = "Version"
INVALID_PROJECT_PATH_TEXT = "Invalid Project Path"
EXPORT_PATH_TEXT = "Export Path"

# Cleanup Panel
CLEANUP_PANEL_LABEL = "Object Cleanup"
NO_MESH_SELECTED_TEXT = "No mesh object selected"
INDIVIDUAL_OPERATIONS_SECTION = "Individual Operations"
REMOVE_UNCONNECTED_VERTICES_TEXT = "Remove Unconnected Vertices"
REMOVE_UNUSED_MATERIALS_TEXT = "Remove Unused Materials"
DISSOLVE_SMALL_FACES_TEXT = "Dissolve Small Faces"
VERTEX_GROUP_CLEANUP_SECTION = "Vertex Group Cleanup"
CLEAN_VERTEX_GROUP_WEIGHTS_TEXT = "Clean Vertex Group Weights"
REMOVE_EMPTY_VERTEX_GROUPS_TEXT = "Remove Empty Vertex Groups"
COMPLETE_CLEANUP_SECTION = "Complete Cleanup"
FULL_CLEANUP_TEXT = "Full Cleanup"

# Animation Panel
ANIMATION_PANEL_LABEL = "Animation Tools"
VERTEX_GROUP_TEXT = "Vertex Group"
TARGET_ARMATURE_TEXT = "Target Armature"
ADD_RIG_TO_SURFACE_TEXT = "Add Rig to Surface"

# ===== PANEL CLASSES =====

class UNITY_PT_main_panel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport"""
    bl_label = MAIN_PANEL_LABEL
    bl_idname = "UNITY_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = MAIN_PANEL_CATEGORY

    def draw(self, context):
        layout = self.layout

        # Reload button
        row = layout.row()
        row.operator("script.reload", text=RELOAD_ADDON_TEXT, icon='FILE_REFRESH')

        scene = context.scene
        unity_props = scene.unity_tool_properties

        # Section for Operators
        box = layout.box()
        row = box.row()
        row.operator("unity.apply_rotation_fix", text=FIX_ROTATION_TEXT)
        box = layout.box()
        row = box.row()
        row.prop(unity_props, "apply_gamma_correction")
        row = box.row()
        row.operator("unity.quick_export", text=QUICK_EXPORT_TEXT)

        # Merge Objects
        box = layout.box()
        box.label(text=MERGE_OBJECTS_SECTION)
        row = box.row()
        row.prop(unity_props, "isolate_mono_animation_objects")
        row = box.row()
        row.operator("unity.merge_objects", text=MERGE_COLLECTION_TEXT)

        box = layout.box()
        box.label(text=BAKING_SECTION)
        row = box.row()
        row.operator("unity.bake_batch", text=BAKE_ACTIVE_PRESETS_TEXT)

        # Section for Settings
        box = layout.box()
        box.label(text=GAME_ENGINE_SETTINGS_SECTION)
        row = box.row()
        row.prop(unity_props, "engine_project_path", text=PROJECT_TEXT)

        if unity_props.engine_version:
            row = box.row()
            row.label(text=f"{VERSION_TEXT}: {unity_props.engine_version}", icon='INFO')

        if unity_props.engine_project_path and not unity_props.is_path_valid:
            row = box.row()
            row.alert = True
            row.label(text=INVALID_PROJECT_PATH_TEXT, icon='ERROR')

        row = box.row()
        row.prop(unity_props, "export_path", text=EXPORT_PATH_TEXT)


class UNITY_PT_cleanup_panel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport for Object Cleanup Tools"""
    bl_label = CLEANUP_PANEL_LABEL
    bl_idname = "UNITY_PT_cleanup_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = MAIN_PANEL_CATEGORY
    bl_parent_id = "UNITY_PT_main_panel"

    def draw(self, context):
        layout = self.layout
        
        # Check if an object is selected
        active_obj = context.active_object
        if not active_obj or active_obj.type != 'MESH':
            box = layout.box()
            box.label(text=NO_MESH_SELECTED_TEXT, icon='ERROR')
            return
        
        # Individual cleanup operations
        box = layout.box()
        box.label(text=INDIVIDUAL_OPERATIONS_SECTION)
        
        # Remove Disconnected Vertices
        row = box.row()
        row.operator("unity.remove_disconnected_vertices", text=REMOVE_UNCONNECTED_VERTICES_TEXT)
        
        # Remove Unused Materials
        row = box.row()
        row.operator("unity.remove_unused_materials", text=REMOVE_UNUSED_MATERIALS_TEXT)
        
        # Dissolve Small Faces
        row = box.row()
        row.operator("unity.dissolve_small_faces", text=DISSOLVE_SMALL_FACES_TEXT)
        
        # Vertex Group Cleanup
        box = layout.box()
        box.label(text=VERTEX_GROUP_CLEANUP_SECTION)
        
        row = box.row()
        row.operator("unity.clean_vertex_group_weights", text=CLEAN_VERTEX_GROUP_WEIGHTS_TEXT)
        
        row = box.row()
        row.operator("unity.remove_empty_vertex_groups", text=REMOVE_EMPTY_VERTEX_GROUPS_TEXT)
        
        # Complete cleanup
        box = layout.box()
        box.label(text=COMPLETE_CLEANUP_SECTION)
        
        row = box.row()
        row.operator("unity.full_cleanup", text=FULL_CLEANUP_TEXT, icon='BRUSH_DATA')


class UNITY_PT_animation_panel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport for Animation Tools"""
    bl_label = ANIMATION_PANEL_LABEL
    bl_idname = "UNITY_PT_animation_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = MAIN_PANEL_CATEGORY
    bl_parent_id = "UNITY_PT_main_panel"

    def draw(self, context):
        layout = self.layout
        cloth_props = context.scene.unity_cloth_rig_properties

        box = layout.box()
        row = box.row()
        row.prop(cloth_props, "mode", expand=True)
        #row = box.row()
        #row.prop(cloth_props, "nth")
        if cloth_props.mode == 'FACES':
            row = box.row()
            row.prop(cloth_props, "copy_rotation")
        
        # Vertex Group selection
        row = box.row()
        if context.active_object:
            row.prop_search(cloth_props, "vertex_group", context.active_object, "vertex_groups", text=VERTEX_GROUP_TEXT)
        else:
            row.enabled = False
            row.label(text=VERTEX_GROUP_TEXT + ": No active object")
        
        # Target Armature selection
        row = box.row()
        row.prop(cloth_props, "target_armature", text=TARGET_ARMATURE_TEXT)
        
        # Clean Weights option (only show if target armature is specified)
        row = box.row()
        row.prop(cloth_props, "clean_weights")
        
        row = box.row()
        row.operator("unity.rig_cloth", text=ADD_RIG_TO_SURFACE_TEXT)


# ===== REGISTRATION =====

def register():
    bpy.utils.register_class(UNITY_PT_main_panel)
    bpy.utils.register_class(UNITY_PT_cleanup_panel)
    bpy.utils.register_class(UNITY_PT_animation_panel)


def unregister():
    bpy.utils.unregister_class(UNITY_PT_animation_panel)
    bpy.utils.unregister_class(UNITY_PT_cleanup_panel)
    bpy.utils.unregister_class(UNITY_PT_main_panel) 