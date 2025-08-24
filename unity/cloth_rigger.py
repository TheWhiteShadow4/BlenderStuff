# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
import mathutils

def get_faces_with_all_vertices_in_group(mesh_obj, vertex_group_name):
	"""Returns a list of face indices where all vertices are in the specified vertex group"""
	if vertex_group_name not in mesh_obj.vertex_groups:
		return []
	
	vertex_group = mesh_obj.vertex_groups[vertex_group_name]
	vertex_group_indices = set()
	
	# Get all vertex indices that are in the vertex group
	for vertex in mesh_obj.data.vertices:
		for group in vertex.groups:
			if group.group == vertex_group.index:
				vertex_group_indices.add(vertex.index)
				break
	
	# Find faces where all vertices are in the group
	valid_face_indices = []
	for face in mesh_obj.data.polygons:
		if all(v_idx in vertex_group_indices for v_idx in face.vertices):
			valid_face_indices.append(face.index)
	
	return valid_face_indices

def find_selected_armature(context):
	"""Returns the first selected armature object, or None if none found"""
	for obj in context.selected_objects:
		if obj.type == 'ARMATURE':
			return obj
	return None

def get_deform_vertex_groups(surface_obj, armature_obj):
	"""Returns a list of vertex group names that correspond to deform bones in the armature"""
	if not armature_obj or not armature_obj.data:
		return []
	
	deform_groups = []
	for bone in armature_obj.data.bones:
		if not bone.use_deform:
			continue
		if bone.name in surface_obj.vertex_groups:
			deform_groups.append(bone.name)
	
	return deform_groups

class CLOTH_OT_rig_cloth(bpy.types.Operator):
	"""Rig Surface with Bones"""
	bl_idname = "unity.rig_cloth"
	bl_label = "Add Rig to Surface"

	def execute(self, context):
		surface = context.active_object
		if not surface or surface.type != 'MESH':
			self.report({'ERROR'}, "Select a mesh surface object first.")
			return {'CANCELLED'}

		props = context.scene.unity_cloth_rig_properties
		
		# Check if we're in edit mode and get selected elements
		selected_indices = []
		was_in_edit_mode = False
		
		# First priority: Vertex Group
		if props.vertex_group and props.vertex_group in surface.vertex_groups:
			if props.mode == 'VERTICES':
				# Get vertices that are in the vertex group
				vertex_group = surface.vertex_groups[props.vertex_group]
				for vertex in surface.data.vertices:
					for group in vertex.groups:
						if group.group == vertex_group.index:
							selected_indices.append(vertex.index)
							break
			else: # FACES
				# Get faces where all vertices are in the vertex group
				selected_indices = get_faces_with_all_vertices_in_group(surface, props.vertex_group)
			
			if not selected_indices:
				self.report({'WARNING'}, f"No elements found in vertex group '{props.vertex_group}'. Using all elements.")
		
		# Second priority: Selection (if no vertex group specified)
		elif surface.mode == 'EDIT':
			was_in_edit_mode = True
			bpy.ops.object.mode_set(mode='OBJECT')  # Switch to object mode to access selection
			
			if props.mode == 'VERTICES':
				selected_indices = [v.index for v in surface.data.vertices if v.select]
				if not selected_indices:
					self.report({'WARNING'}, "No vertices selected. Using all vertices.")
			else: # FACES
				selected_indices = [f.index for f in surface.data.polygons if f.select]
				if not selected_indices:
					self.report({'WARNING'}, "No faces selected. Using all faces.")
		
		# Determine target armature using priority system
		armature_obj = None
		created_new_armature = False
		
		# First priority: Specified target armature
		if props.target_armature and props.target_armature.type == 'ARMATURE':
			armature_obj = props.target_armature
		
		# Second priority: Selected armature
		elif not was_in_edit_mode:  # Only check selection if we weren't in edit mode
			armature_obj = find_selected_armature(context)
		
		# Third priority: Create new armature
		if not armature_obj:
			bpy.ops.object.add(type='ARMATURE', enter_editmode=False, align='WORLD', location=surface.location)
			armature_obj = context.active_object
			armature_obj.name = f"{surface.name}_Rig"
			armature = armature_obj.data
			armature.name = f"{surface.name}_Rig_Armature"
			created_new_armature = True
		
		# Switch to the armature and enter edit mode
		bpy.context.view_layer.objects.active = armature_obj
		bpy.ops.object.mode_set(mode='EDIT')
		armature = armature_obj.data

		# Calculate transformation matrix from surface to armature space
		surface_to_world = surface.matrix_world
		world_to_armature = armature_obj.matrix_world.inverted()
		surface_to_armature = world_to_armature @ surface_to_world

		elements = []
		if props.mode == 'VERTICES':
			if selected_indices:
				elements = [surface.data.vertices[i] for i in selected_indices]
			else:
				elements = surface.data.vertices
		else: # FACES
			surface.data.calc_tangents()
			if selected_indices:
				elements = [surface.data.polygons[i] for i in selected_indices]
			else:
				elements = surface.data.polygons

		count = 0
		new_bone_names = []  # Track newly created bones
		bone_to_vgroup_mapping = {}  # Map bone names to vertex group names
		
		for i, element in enumerate(elements):
			bone_name = f"cloth_bone_{count}"
			vertex_group_name = f"cloth_vgroup_{count}"  # Different name to avoid dependency loop
			bone = armature.edit_bones.new(bone_name)
			new_bone_names.append(bone_name)  # Store the name
			bone_to_vgroup_mapping[bone_name] = vertex_group_name  # Store the mapping
			
			if props.mode == 'VERTICES':
				vert: bpy.types.MeshVertex = element
				pos = surface_to_armature @ element.co
				normal = surface_to_armature.to_3x3() @ vert.normal

				bone.head = pos
				bone.tail = pos - normal * 0.2
			else: # FACES
				face: bpy.types.MeshPolygon = element
				pos = surface_to_armature @ face.center
				normal = mathutils.Vector()
				tangent = mathutils.Vector()
				bitangent = mathutils.Vector()
				for vert in [surface.data.loops[i] for i in face.loop_indices]:
					normal += vert.normal
					tangent += vert.tangent
					bitangent += vert.bitangent

				normal = normal / len(face.loop_indices)
				tangent = tangent / len(face.loop_indices)
				bitangent = bitangent / len(face.loop_indices)

				# Transform normal vectors to armature space
				normal = surface_to_armature.to_3x3() @ normal
				tangent = surface_to_armature.to_3x3() @ tangent
				bitangent = surface_to_armature.to_3x3() @ bitangent

				bone.head = pos
				bone.tail = pos - bitangent * 0.2
				bone.align_roll(normal)

			# Get vertices that will be assigned to this bone
			vertices_to_assign = []
			if props.mode == 'VERTICES':
				vertices_to_assign = [element.index]
			else: # FACES
				vertices_to_assign = list(element.vertices)

			# Create and assign vertex group with different name to avoid dependency loop
			vgroup = surface.vertex_groups.new(name=vertex_group_name)
			vgroup.add(vertices_to_assign, 1.0, 'REPLACE')

			count += 1
		
		bpy.ops.object.mode_set(mode='OBJECT')

		# Duplicate surface BEFORE creating vertex groups, clean it and prepare for baking
		bpy.ops.object.select_all(action='DESELECT')
		surface.select_set(True)
		bpy.context.view_layer.objects.active = surface
		bpy.ops.object.duplicate()
		
		surface_copy = context.active_object
		surface_copy.name = f"{surface.name}_Deformed"

		# Clean cloth/softbody modifiers from the copy
		for mod in list(surface_copy.modifiers):
			if mod.type in {'CLOTH', 'SOFT_BODY'}:
				surface_copy.modifiers.remove(mod)

		# Create vertex groups on deformed surface with bone names (for armature modifier)
		for bone_name in new_bone_names:
			vertex_group_name = bone_to_vgroup_mapping[bone_name]
			
			# Get vertices from original surface's vertex group
			original_vgroup = surface.vertex_groups.get(vertex_group_name)
			if original_vgroup:
				# Copy vertex assignments
				vertices_to_assign = []
				for vertex in surface.data.vertices:
					for group in vertex.groups:
						if group.group == original_vgroup.index:
							vertices_to_assign.append(vertex.index)
							break
				
				# Clean weights from existing deform groups on deformed surface if enabled and using existing armature
				if props.clean_weights and not created_new_armature:
					deform_groups = get_deform_vertex_groups(surface_copy, armature_obj)
					for group_name in deform_groups:
						if group_name in surface_copy.vertex_groups:
							group = surface_copy.vertex_groups[group_name]
							group.remove(vertices_to_assign)
				
				# Create matching vertex group on deformed surface with bone name
				deformed_vgroup = surface_copy.vertex_groups.new(name=bone_name)
				deformed_vgroup.add(vertices_to_assign, 1.0, 'REPLACE')

		# Add armature modifier to the copy
		armature_mod = surface_copy.modifiers.new(name='Armature', type='ARMATURE')
		armature_mod.object = armature_obj

		# Add constraints to newly created bones only
		bpy.context.view_layer.objects.active = armature_obj
		bpy.ops.object.mode_set(mode='POSE')

		for bone_name in new_bone_names:
			pbone = armature_obj.pose.bones.get(bone_name)
			if pbone:  # Safety check
				vertex_group_name = bone_to_vgroup_mapping[bone_name]
				if props.mode == 'FACES' and props.copy_rotation:
					constraint = pbone.constraints.new(type='COPY_TRANSFORMS')
					constraint.target = surface
					constraint.subtarget = vertex_group_name
				else:
					constraint = pbone.constraints.new(type='COPY_LOCATION')
					constraint.target = surface
					constraint.subtarget = vertex_group_name
		
		bpy.ops.object.mode_set(mode='OBJECT')

		# Hide the original object
		surface.hide_set(True)
		surface.hide_render = True

		# Ensure the new object is active and selected
		bpy.context.view_layer.objects.active = surface_copy
		surface_copy.select_set(True)
		
		if created_new_armature:
			self.report({'INFO'}, f"Created new rig '{armature_obj.name}' and '{surface_copy.name}' ready for baking.")
		else:
			self.report({'INFO'}, f"Added bones to existing rig '{armature_obj.name}' and '{surface_copy.name}' ready for baking.")
		return {'FINISHED'}

def register():
	bpy.utils.register_class(CLOTH_OT_rig_cloth)

def unregister():
	bpy.utils.unregister_class(CLOTH_OT_rig_cloth) 