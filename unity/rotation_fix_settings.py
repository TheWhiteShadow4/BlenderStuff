# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy

class RotationFixSettings:
    """
    Simple settings manager specifically for the rotation fix operation.
    Stores and restores only the settings needed for this specific operation.
    """
    
    def __init__(self, context):
        self.context = context
        self.original_cursor_location = None
        self.original_pivot_point = None
        self.original_automerge = None
        self.original_mirror_x = None
        self.original_mirror_y = None
        self.original_mirror_z = None
    
    def __enter__(self):
        # Store current settings
        self.original_cursor_location = self.context.scene.cursor.location.copy()
        self.original_pivot_point = self.context.scene.tool_settings.transform_pivot_point
        self.original_automerge = self.context.scene.tool_settings.use_mesh_automerge
        
        # Store mesh mirror settings from active object
        active_obj = self.context.object
        if active_obj and active_obj.type == 'MESH':
            self.original_mirror_x = getattr(active_obj, 'use_mesh_mirror_x', None)
            self.original_mirror_y = getattr(active_obj, 'use_mesh_mirror_y', None)
            self.original_mirror_z = getattr(active_obj, 'use_mesh_mirror_z', None)
        
        # Set required settings for rotation fix
        self.context.scene.tool_settings.transform_pivot_point = 'CURSOR'
        self.context.scene.tool_settings.use_mesh_automerge = False  # Prevent unwanted vertex merging
        
        # Disable mesh symmetry to prevent unexpected mirroring during rotation
        if active_obj and active_obj.type == 'MESH':
            if hasattr(active_obj, 'use_mesh_mirror_x'):
                active_obj.use_mesh_mirror_x = False
            if hasattr(active_obj, 'use_mesh_mirror_y'):
                active_obj.use_mesh_mirror_y = False
            if hasattr(active_obj, 'use_mesh_mirror_z'):
                active_obj.use_mesh_mirror_z = False
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original settings
        if self.original_cursor_location is not None:
            self.context.scene.cursor.location = self.original_cursor_location
        
        if self.original_pivot_point is not None:
            self.context.scene.tool_settings.transform_pivot_point = self.original_pivot_point
        
        if self.original_automerge is not None:
            self.context.scene.tool_settings.use_mesh_automerge = self.original_automerge
        
        # Restore mesh mirror settings
        active_obj = self.context.object
        if active_obj and active_obj.type == 'MESH':
            if self.original_mirror_x is not None and hasattr(active_obj, 'use_mesh_mirror_x'):
                active_obj.use_mesh_mirror_x = self.original_mirror_x
            if self.original_mirror_y is not None and hasattr(active_obj, 'use_mesh_mirror_y'):
                active_obj.use_mesh_mirror_y = self.original_mirror_y
            if self.original_mirror_z is not None and hasattr(active_obj, 'use_mesh_mirror_z'):
                active_obj.use_mesh_mirror_z = self.original_mirror_z 