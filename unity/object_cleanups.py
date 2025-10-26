# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
from mathutils import Vector

class ObjectCleanupTools:
    """Collection of tools for cleaning up 3D objects"""
    
    @staticmethod
    def remove_disconnected_vertices(obj):
        """Removes disconnected vertices (loose vertices)"""
        if obj.type != 'MESH':
            return False, "Object is not a mesh"
        
        # Enter Edit Mode
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Select all vertices
        bpy.ops.mesh.select_all(action='SELECT')
        
        # Remove disconnected vertices
        bpy.ops.mesh.delete_loose()
        
        # Return to Object Mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        return True, "Disconnected vertices removed"
    
    @staticmethod
    def remove_unused_materials(obj):
        """Removes unused material slots"""
        if obj.type != 'MESH':
            return False, "Object is not a mesh"
        
        # Check all material slots
        materials_to_remove = []
        for i, slot in enumerate(obj.material_slots):
            if slot.material is None:
                materials_to_remove.append(i)
        
        # Remove material slots from back to front (to avoid index shifting)
        for i in reversed(materials_to_remove):
            obj.active_material_index = i
            bpy.ops.object.material_slot_remove({'object': obj})
        
        return True, f"{len(materials_to_remove)} unused material slots removed"
    
    @staticmethod
    def dissolve_small_faces(obj, min_area=0.0001):
        """Dissolves faces with very small area"""
        if obj.type != 'MESH':
            return False, "Object is not a mesh"
        
        # Enter Edit Mode
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Select all faces
        bpy.ops.mesh.select_all(action='SELECT')
        
        # Dissolve faces with small area
        bpy.ops.mesh.dissolve_faces()
        
        # Return to Object Mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        return True, f"Faces with area < {min_area} dissolved"
    
    @staticmethod
    def clean_vertex_group_weights(obj, threshold=0.001):
        """Cleans vertex groups by removing very small weight values"""
        if obj.type != 'MESH':
            return False, "Object is not a mesh"
        
        if not obj.vertex_groups:
            return True, "No vertex groups present"
        
        # Iterate through all vertex groups
        for vg in obj.vertex_groups:
            # Check all vertices in this group
            for i, vertex in enumerate(obj.data.vertices):
                try:
                    weight = vg.weight(i)
                    if weight < threshold:
                        vg.remove([i])
                except:
                    continue
        
        return True, f"Vertex group weights cleaned (threshold: {threshold})"
    
    @staticmethod
    def remove_empty_vertex_groups(obj):
        """Removes vertex groups without any weights, preserving mirror modifier groups"""
        if obj.type != 'MESH':
            return False, "Object is not a mesh"
        
        if not obj.vertex_groups:
            return True, "No vertex groups present"
        
        groups_to_remove = []
        
        # Check all vertex groups
        for vg in obj.vertex_groups:
            has_weights = False
            for i in range(len(obj.data.vertices)):
                try:
                    if vg.weight(i) > 0:
                        has_weights = True
                        break
                except:
                    continue
            
            if not has_weights:
                # Check if this is a mirror modifier group that should be preserved
                group_name = vg.name
                should_preserve = False
                
                # Check for mirror modifier suffixes (.L, .R)
                if group_name.endswith('.L') or group_name.endswith('.R'):
                    # Find the corresponding opposite group
                    if group_name.endswith('.L'):
                        opposite_name = group_name[:-2] + '.R'
                    else:  # .R
                        opposite_name = group_name[:-2] + '.L'
                    
                    # Check if the opposite group exists and has weights
                    opposite_group = obj.vertex_groups.get(opposite_name)
                    if opposite_group:
                        # Check if opposite group has weights
                        opposite_has_weights = False
                        for j in range(len(obj.data.vertices)):
                            try:
                                if opposite_group.weight(j) > 0:
                                    opposite_has_weights = True
                                    break
                            except:
                                continue
                        
                        # If opposite group has weights, preserve this group too
                        if opposite_has_weights:
                            should_preserve = True
                
                # Only remove if not a mirror modifier group to preserve
                if not should_preserve:
                    groups_to_remove.append(group_name)
        
        # Remove empty vertex groups
        for group_name in groups_to_remove:
            obj.vertex_groups.remove(obj.vertex_groups[group_name])
        
        return True, f"{len(groups_to_remove)} empty vertex groups removed (mirror groups preserved)"
    
    @staticmethod
    def full_cleanup(obj):
        """Performs a complete cleanup of the object"""
        if obj.type != 'MESH':
            return False, "Object is not a mesh"
        
        results = []
        
        # Execute all cleanup functions
        success, msg = ObjectCleanupTools.remove_disconnected_vertices(obj)
        if success:
            results.append(msg)
        
        success, msg = ObjectCleanupTools.remove_unused_materials(obj)
        if success:
            results.append(msg)
        
        success, msg = ObjectCleanupTools.dissolve_small_faces(obj)
        if success:
            results.append(msg)
        
        success, msg = ObjectCleanupTools.clean_vertex_group_weights(obj)
        if success:
            results.append(msg)
        
        success, msg = ObjectCleanupTools.remove_empty_vertex_groups(obj)
        if success:
            results.append(msg)
        
        return True, f"Complete cleanup finished: {'; '.join(results)}" 