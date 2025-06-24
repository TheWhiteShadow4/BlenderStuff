# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy

class Baker():
	def __init__(self, socket_name, bake_image, uv_map_name):
		# Name des Eingangs, dessen Wert gebaked werden soll. Für alle Mateiralien gleich, aber nicht immer vorhanden.
		self.socket_name = socket_name
		# Bild, das gebaked werden soll.
		self.bake_image = bake_image
		# Name der UV Map, die gebaked werden soll.
		self.uv_map_name = uv_map_name

	def bake_selection(self):
		'''
		Bake the selected objects.
		'''
		self.warnings = []
		self.objects = []
		for obj in bpy.context.selected_objects:
			if obj.type == 'MESH':
				self.objects.append(obj)

		print({'INFO'}, f"Collecting materials for {len(self.objects)} objects.")
		self._collect_materials()
		for bake_material in self.bake_materials:
			bake_material.prepare()

		bake_success = self.execute_bake()
		if bake_success:
			print({'INFO'}, f"Baking successful.")
			for bake_material in self.bake_materials:
				bake_material.cleanup()


		return bake_success	


	def execute_bake(self):
		bake_success = True

		# State speichern
		preserved_state = self._preserve_state()
		next(preserved_state)

		try:
			for obj in self.objects:
				obj.hide_render = False
			bpy.context.scene.render.engine = 'CYCLES'
			bpy.ops.object.bake(type='EMIT', save_mode='INTERNAL')
			
		except Exception as e:
			print({'ERROR'}, f"Error baking: {e}")
			bake_success = False
			for bake_material in self.bake_materials:
				bake_material.rollback()
		finally:
			# State wiederherstellen
			next(preserved_state)

		return bake_success

	def _preserve_state(self):
		'''
		Speichert den aktiven State.
		'''
		prev_hide_render = {obj: obj.hide_render for obj in self.objects}

		prev_active_uv = {}
		for obj in self.objects:
			if obj and obj.data and hasattr(obj.data, 'uv_layers') and self.uv_map_name:
				active_uv_name = None
				for uv in obj.data.uv_layers:
					if uv.active:
						active_uv_name = uv.name
					# Setze während des Bakes ausschließlich die gewünschte UV-Map aktiv
					uv.active = (uv.name == self.uv_map_name)
				# Speichere (auch None möglich) für spätere Wiederherstellung
				prev_active_uv[obj] = active_uv_name

		original_engine = bpy.context.scene.render.engine
		print({'INFO'}, f"State gespeichert.")
		yield

		bpy.context.scene.render.engine = original_engine

		for obj in self.objects:
			if obj and obj.data and hasattr(obj.data, 'uv_layers'):
				original_name = prev_active_uv.get(obj)
				# Falls kein ursprünglicher aktiver Layer gespeichert wurde, bleiben alle UV-Layer inaktiv.
				for uv in obj.data.uv_layers:
					uv.active = (uv.name == original_name)
		
		for obj, prev in prev_hide_render.items():
			obj.hide_render = prev
		print({'INFO'}, f"State wiederhergestellt.")
		yield

	def _collect_materials(self):
		'''
		Sammelt alle Materialien aus den ausgewählten Objekten. 
		Jedes Material muss nur einaml verarbeitet werden.
		'''
		self.bake_materials = []
		for obj in self.objects:
			if not self._has_uv_layer(obj):
				self.warnings.append(f"Object {obj.name} has no UV layer named {self.uv_map_name}")

			for material in obj.material_slots:
				mat = material.material
				if not any(bm.material == mat for bm in self.bake_materials):
					if_node_input = self._get_interface_node_socket(mat)
					image_node = self._get_or_create_image_node(mat, if_node_input)
					bake_material = BakeMaterial(mat, image_node, self.uv_map_name, if_node_input)
					
					if len(obj.data.uv_layers) > 1:
						bake_material.create_uv_node()

					print({'INFO'}, f"Adding baking material {mat.name}. Dummy: {bake_material.is_dummy_material()}")
					self.bake_materials.append(bake_material)

	def _get_or_create_image_node(self, material, if_node_input):
		'''
		Gibt den Image Node des Materials zurück, oder erstellt einen neuen, wenn er nicht existiert.
		'''
		bake_target_node = None
		for node in material.node_tree.nodes:
			if node.type == 'TEX_IMAGE' and node.image == self.bake_image:
				bake_target_node = node
				break
		
		if not bake_target_node:
			bake_target_node = material.node_tree.nodes.new('ShaderNodeTexImage')
			bake_target_node.image = self.bake_image
			if if_node_input.node:
				bake_target_node.location = if_node_input.node.location
				bake_target_node.location.x -= 300
		return bake_target_node


	def _has_uv_layer(self, obj):
		'''
		Findet die UV Map des Materials.
		'''
		for uv in obj.data.uv_layers:
			if uv.name == self.uv_map_name:
				return True
		return False

	def _get_interface_node_socket(self, material):
		'''
		Findet den Node Eingang des Interface im Material.
		'''
		interface_node = get_interface_node_in_material(material)
		if interface_node:
			return interface_node.inputs[self.socket_name]
		return None


class BakeMaterial():
	"""
	Material, das gebaked werden soll. Enthält die referenz auf den Image Node, die UV Map und obe es sich um ein Dummy Material handelt.
	"""
	def __init__(self, material, image_node, uv_map_name, if_node_input):
		self.material = material
		self.image_node = image_node
		self.uv_map_name = uv_map_name
		self.if_node_input = if_node_input
		self.uv_node = None
		self.output_node = next(n for n in self.material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')

		self.socket_link = None
		self.output_to_bake = None
		if self.if_node_input:
			self.socket_link = self.if_node_input.links[0]
		if self.socket_link:
			self.output_to_bake = self.socket_link.from_socket


	def is_dummy_material(self):
		return self.output_to_bake is None


	def prepare(self):
		self.original_surface_from_sockets = [l.from_socket for l in self.output_node.inputs['Surface'].links]
		if self.output_to_bake:
			self.material.node_tree.links.new(self.output_to_bake, self.output_node.inputs['Surface'])
		self.image_node.select = True
		self.material.node_tree.nodes.active = self.image_node


	def _restore_output_node(self):
		for fs in self.original_surface_from_sockets:
			self.material.node_tree.links.new(fs, self.output_node.inputs['Surface'])


	def cleanup(self):
		'''
		Entfernt alle temporären Nodes und Links.
		'''
		if self.is_dummy_material():
			self.material.node_tree.nodes.remove(self.image_node)
			if self.uv_node:
				self.material.node_tree.nodes.remove(self.uv_node)
			return

		self.material.node_tree.links.remove(self.output_node.inputs['Surface'].links[0])
		self.material.node_tree.links.new(self.image_node.outputs['Color'], self.if_node_input)

		self._restore_output_node()


	def rollback(self):
		'''
		Setzt den Material zurück auf den ursprünglichen Zustand.
		'''
		self.material.node_tree.links.new(self.output_to_bake, self.if_node_input)
		self.material.node_tree.nodes.remove(self.image_node)
		if self.uv_node:
			self.material.node_tree.nodes.remove(self.uv_node)
		self._restore_output_node()


	def create_uv_node(self):
		uv_node = self.material.node_tree.nodes.new('ShaderNodeUVMap')
		uv_node.uv_map = self.uv_map_name
		uv_node.location = self.image_node.location
		uv_node.location.x -= 150
		self.material.node_tree.links.new(uv_node.outputs['UV'], self.image_node.inputs['Vector'])


def get_interface_node(obj):
	"""Finds and returns the main interface node group for a given object if it's valid."""
	if not (obj and obj.active_material):
		return None
	mat = obj.active_material
	return get_interface_node_in_material(mat)

def get_interface_node_in_material(material):
	"""Finds and returns the main interface node group for a given object if it's valid."""
	if not material.use_nodes:
		return None
	output_node = next((n for n in material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
	if not (output_node and output_node.inputs['Surface'].links):
		return None
	interface_node = output_node.inputs['Surface'].links[0].from_node
	return interface_node if interface_node.type == 'GROUP' else None