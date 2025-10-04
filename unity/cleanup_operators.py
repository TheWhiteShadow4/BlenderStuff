# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
from . import object_cleanups

class UNITY_OT_remove_disconnected_vertices(bpy.types.Operator):
    """Removes unconnected vertices in the selected object"""
    bl_idname = "unity.remove_disconnected_vertices"
    bl_label = "Remove Unconnected Vertices"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        success, message = object_cleanups.ObjectCleanupTools.remove_disconnected_vertices(obj)
        
        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'ERROR'}, message)
        
        return {'FINISHED'}

class UNITY_OT_remove_unused_materials(bpy.types.Operator):
    """Removes unused material slots in the selected object"""
    bl_idname = "unity.remove_unused_materials"
    bl_label = "Remove Unused Materials"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        success, message = object_cleanups.ObjectCleanupTools.remove_unused_materials(obj)
        
        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'ERROR'}, message)
        
        return {'FINISHED'}

class UNITY_OT_dissolve_small_faces(bpy.types.Operator):
    """Dissolves faces with very small area"""
    bl_idname = "unity.dissolve_small_faces"
    bl_label = "Dissolve Small Faces"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        success, message = object_cleanups.ObjectCleanupTools.dissolve_small_faces(obj)
        
        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'ERROR'}, message)
        
        return {'FINISHED'}

class UNITY_OT_clean_vertex_group_weights(bpy.types.Operator):
    """Cleans vertex groups by removing very small weight values"""
    bl_idname = "unity.clean_vertex_group_weights"
    bl_label = "Clean Vertex Group Weights"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        success, message = object_cleanups.ObjectCleanupTools.clean_vertex_group_weights(obj)
        
        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'ERROR'}, message)
        
        return {'FINISHED'}

class UNITY_OT_remove_empty_vertex_groups(bpy.types.Operator):
    """Removes vertex groups without any weights"""
    bl_idname = "unity.remove_empty_vertex_groups"
    bl_label = "Remove Empty Vertex Groups"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        success, message = object_cleanups.ObjectCleanupTools.remove_empty_vertex_groups(obj)
        
        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'ERROR'}, message)
        
        return {'FINISHED'}

class UNITY_OT_full_cleanup(bpy.types.Operator):
    """Performs a complete cleanup of the selected object"""
    bl_idname = "unity.full_cleanup"
    bl_label = "Full Cleanup"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        success, message = object_cleanups.ObjectCleanupTools.full_cleanup(obj)
        
        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'ERROR'}, message)
        
        return {'FINISHED'}

# List of all cleanup operators
cleanup_operators = [
    UNITY_OT_remove_disconnected_vertices,
    UNITY_OT_remove_unused_materials,
    UNITY_OT_dissolve_small_faces,
    UNITY_OT_clean_vertex_group_weights,
    UNITY_OT_remove_empty_vertex_groups,
    UNITY_OT_full_cleanup
]

def register():
    for op in cleanup_operators:
        bpy.utils.register_class(op)

def unregister():
    for op in reversed(cleanup_operators):
        bpy.utils.unregister_class(op) 