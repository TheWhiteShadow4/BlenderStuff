# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
import bmesh

# ===== UI TEXT CONSTANTS =====
UV_TOOLS_PANEL_LABEL = "Unity UV Tools"
UV_TOOLS_PANEL_CATEGORY = "Game Tools"
COPY_UV_SECTION = "Copy Selected UV Faces"
TARGET_UV_MAP_TEXT = "Target UV Map"
COPY_SELECTED_UV_TEXT = "Copy Selected UVs"
NO_OBJECT_SELECTED_TEXT = "No mesh object selected"
NO_UV_MAPS_TEXT = "Object has no UV maps"
SAME_UV_MAP_TEXT = "Source and target UV maps are the same"

# ===== HELPER FUNCTIONS =====

def get_other_uv_maps(self, context):
    """EnumProperty callback to get all UV maps except the currently active one."""
    items = []
    
    if not context.object or context.object.type != 'MESH':
        return [("NONE", "No UV Maps", "Object has no UV maps")]
    
    mesh = context.object.data
    if not mesh.uv_layers:
        return [("NONE", "No UV Maps", "Object has no UV maps")]
    
    # Get the currently active UV layer
    active_uv = mesh.uv_layers.active
    active_name = active_uv.name if active_uv else ""
    
    # Add all UV layers except the active one
    for uv_layer in mesh.uv_layers:
        if uv_layer.name != active_name:
            items.append((uv_layer.name, uv_layer.name, f"Copy to UV map '{uv_layer.name}'"))
    
    if not items:
        return [("NONE", "No Other UV Maps", "No other UV maps available")]
    
    return items

# ===== OPERATORS =====

class UNITY_OT_copy_selected_uvs(bpy.types.Operator):
    """Copy selected UV faces from active UV map to target UV map"""
    bl_idname = "unity.copy_selected_uvs"
    bl_label = "Copy Selected UVs"
    bl_options = {'REGISTER', 'UNDO'}
    
    target_uv_map: bpy.props.EnumProperty(
        name="Target UV Map",
        description="UV map to copy the selected UVs to",
        items=get_other_uv_maps
    )
    
    @classmethod
    def poll(cls, context):
        return (context.object and 
                context.object.type == 'MESH' and 
                context.object.data.uv_layers and
                context.mode == 'EDIT_MESH')
    
    def execute(self, context):
        if self.target_uv_map == "NONE":
            self.report({'WARNING'}, "No target UV map selected")
            return {'CANCELLED'}
        
        obj = context.object
        mesh = obj.data
        
        # Check if target UV map exists
        target_uv_layer = mesh.uv_layers.get(self.target_uv_map)
        if not target_uv_layer:
            self.report({'ERROR'}, f"Target UV map '{self.target_uv_map}' not found")
            return {'CANCELLED'}
        
        # Get source UV layer (active)
        source_uv_layer = mesh.uv_layers.active
        if not source_uv_layer:
            self.report({'ERROR'}, "No active UV layer found")
            return {'CANCELLED'}
        
        if source_uv_layer.name == self.target_uv_map:
            self.report({'WARNING'}, SAME_UV_MAP_TEXT)
            return {'CANCELLED'}
        
        # Switch to edit mode and update mesh
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Get bmesh representation from edit mesh
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        
        # Get UV layers from bmesh
        source_uv = bm.loops.layers.uv.get(source_uv_layer.name)
        target_uv = bm.loops.layers.uv.get(target_uv_layer.name)
        
        if not source_uv or not target_uv:
            self.report({'ERROR'}, "UV layers not found in bmesh")
            bm.free()
            return {'CANCELLED'}
        
        copied_faces = 0
        
        # Copy UV coordinates from selected faces
        for face in bm.faces:
            # Check if face is selected in UV editor (check UV selection)
            uv_selected = any(loop[source_uv].select for loop in face.loops)
            
            if uv_selected:
                for loop in face.loops:
                    # Copy UV coordinate from source to target
                    loop[target_uv].uv = loop[source_uv].uv
                copied_faces += 1
        
        if copied_faces == 0:
            self.report({'WARNING'}, "No faces selected")
            bm.free()
            return {'CANCELLED'}
        
        # Update mesh
        bmesh.update_edit_mesh(mesh)
        
        self.report({'INFO'}, f"Copied UVs from {copied_faces} faces to '{self.target_uv_map}'")
        return {'FINISHED'}

# ===== PANEL CLASSES =====

class UNITY_PT_uv_tools_panel(bpy.types.Panel):
    """Creates a Panel in the UV Editor"""
    bl_label = UV_TOOLS_PANEL_LABEL
    bl_idname = "UNITY_PT_uv_tools_panel"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = UV_TOOLS_PANEL_CATEGORY
    
    @classmethod
    def poll(cls, context):
        return (context.space_data.mode == 'UV' and 
                context.object and 
                context.object.type == 'MESH')
    
    def draw(self, context):
        layout = self.layout
        obj = context.object
        
        if not obj or obj.type != 'MESH':
            box = layout.box()
            box.label(text=NO_OBJECT_SELECTED_TEXT, icon='ERROR')
            return
        
        mesh = obj.data
        if not mesh.uv_layers:
            box = layout.box()
            box.label(text=NO_UV_MAPS_TEXT, icon='ERROR')
            return
        
        # Copy UV Faces Section
        box = layout.box()
        box.label(text=COPY_UV_SECTION)
        
        # Show current active UV layer
        active_uv = mesh.uv_layers.active
        if active_uv:
            row = box.row()
            row.label(text=f"Source: {active_uv.name}", icon='UV_DATA')
        
        # Check available UV maps
        other_uv_maps = get_other_uv_maps(None, context)
        
        if other_uv_maps and other_uv_maps[0][0] != "NONE":
            # Add buttons for each UV map
            col = box.column(align=True)
            for uv_name, uv_display, uv_desc in other_uv_maps:
                if uv_name != "NONE":
                    op = col.operator("unity.copy_selected_uvs", text=f"→ {uv_display}")
                    op.target_uv_map = uv_name
        else:
            row = box.row()
            row.label(text="No other UV maps available", icon='INFO')
        
        # Show usage info
        if context.mode != 'EDIT_MESH':
            box = layout.box()
            box.label(text="Switch to Edit Mode to copy UVs", icon='INFO')

# ===== REGISTRATION =====

def register():
    bpy.utils.register_class(UNITY_OT_copy_selected_uvs)
    bpy.utils.register_class(UNITY_PT_uv_tools_panel)

def unregister():
    bpy.utils.unregister_class(UNITY_PT_uv_tools_panel)
    bpy.utils.unregister_class(UNITY_OT_copy_selected_uvs) 