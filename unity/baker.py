# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import traceback
from . import bake_utils
import bpy

class Baker():
	def __init__(self, bake_data: bake_utils.BakeData):
		self.bake_data = bake_data
		self.dummy_image = None
	
	def get_or_create_dummy_image(self):
		if not self.dummy_image:
			self.dummy_image = bpy.data.images.new(name="Dummy Image", width=1, height=1)
			self.dummy_image.generated_type = 'BLANK'
		return self.dummy_image

	def bake(self):
		self.warnings = []
		self.objects = []

		# TODO: ungültige Objekte vorab aus der Bake Data nehmen.
		for obj in bpy.context.selected_objects:
			if obj.type == 'MESH':
				self.objects.append(obj)

		# globalen State speichern
		preserved_global_state = self._preserve_global_state()
		next(preserved_global_state)

		try:
			# States setzen
			bpy.context.scene.render.engine = 'CYCLES'
			bpy.context.scene.render.bake.use_clear = False

			for bake_pass in self.bake_data.passes:
				print(f"Bake Pass {bake_pass.index}")
				self.bake_pass(bake_pass)

		except Exception as e:
			print(traceback.format_exc())
			print({'ERROR'}, f"{e}")
			return {'CANCELLED'}

		finally:
			# State wiederherstellen
			next(preserved_global_state)
			if self.dummy_image:
				bpy.data.images.remove(self.dummy_image)

		return {'FINISHED'}	

	def bake_pass(self, bake_pass: bake_utils.BakePass):
		preserved_object_state = self._preserve_object_state(bake_pass.object, bake_pass)
		next(preserved_object_state)

		try:
			print({'INFO'}, f"Prepare '{bake_pass.object.name}'.")
			self._collect_materials_for_pass(bake_pass)
			for bake_material in self.bake_materials:
				bake_material.prepare()

			# TODO: Funktionalität frei von der KI interpretiert.
			# Hier ist weitere Arbeit erfordferlich wie weit sich das auswirkt, und das die Erwartunghaltung vom Benutzer wäre.
			print(f"Baking with margin: {bake_pass.max_margin}")
			bpy.ops.object.bake(type='EMIT', save_mode='INTERNAL', margin=bake_pass.max_margin)
			
			for bake_material in self.bake_materials:
				bake_material.cleanup()

		except Exception as e:
			print("Führe Rollback aus.")
			for bake_material in self.bake_materials:
				bake_material.rollback()
			raise e
		finally:
			next(preserved_object_state)


	def _preserve_global_state(self):
		'''
		Speichert den aktiven State.
		'''
		prev_hide_render = {obj: obj.hide_render for obj in self.objects}
		
		original_engine = bpy.context.scene.render.engine
		original_use_clear = bpy.context.scene.render.bake.use_clear

		print({'INFO'}, f"State gespeichert.")
		# Hier wird die Funktion pausiert und der Bake durchgeführt.
		yield

		# State wiederherstellen
		bpy.context.scene.render.bake.use_clear = original_use_clear
		bpy.context.scene.render.engine = original_engine
		
		for obj, prev in prev_hide_render.items():
			obj.hide_render = prev

		print({'INFO'}, f"State wiederhergestellt.")
		yield

	def _preserve_object_state(self, obj, bake_pass):
		# TODO: Wenn die Funktion so leer bleibt, kann sie weg

		# TODO: Neuer Ansatz: UV vor dem Image Node setzen
		#prev_active_uv = {}
		#if obj and obj.data and hasattr(obj.data, 'uv_layers') and self.uv_map_name:
		#	active_uv_name = None
		#	for uv in obj.data.uv_layers:
		#		if uv.active:
		#			active_uv_name = uv.name
		#		# Setze während des Bakes ausschließlich die gewünschte UV-Map aktiv
		#		uv.active = (uv.name == self.uv_map_name)
		#	# Speichere (auch None möglich) für spätere Wiederherstellung
		#	prev_active_uv[obj] = active_uv_name

		#print({'INFO'}, f"Object State gespeichert.")
		yield

		#if obj and obj.data and hasattr(obj.data, 'uv_layers'):
		#	original_name = prev_active_uv.get(obj)
		#	# Falls kein ursprünglicher aktiver Layer gespeichert wurde, bleiben alle UV-Layer inaktiv.
		#	for uv in obj.data.uv_layers:
		#		uv.active = (uv.name == original_name)
		

		#print({'INFO'}, f"Object State wiederhergestellt.")
		yield

	def _collect_materials_for_pass(self, bake_pass):
		'''
		Sammelt alle Materialien aus den ausgewählten Objekten. 
		Jedes Material muss nur einaml verarbeitet werden.
		'''
		self.bake_materials = []
		for setting in bake_pass.settings:
			mat = setting.material

			image = setting.image
			if setting.is_dummy():
				image = self.get_or_create_dummy_image()
			elif image == None:
				image = bake_pass.get_or_create_image_for_setting(setting)

			v_offset = (len(self.bake_data.passes) / 2 - bake_pass.index) * 250

			image_node = self._get_or_create_image_node(mat, setting.input_socket, image, v_offset)
			bake_material = BakeMaterial(mat, setting.input_socket, setting.uv_map_name, image_node, setting.channels)

			print({'INFO'}, f"Adding baking material {mat.name}.")
			self.bake_materials.append(bake_material)

	def _get_or_create_image_node(self, material, if_node_input, bake_image, v_offset):
		'''
		Gibt den Image Node des Materials zurück, oder erstellt einen neuen, wenn er nicht existiert.
		'''
		bake_target_node = None
		if bake_image:
			for node in material.node_tree.nodes:
				if node.type == 'TEX_IMAGE' and node.image == bake_image:
					bake_target_node = node
					break
		else:
			bake_image = self.get_or_create_dummy_image()
		
		if not bake_target_node and if_node_input:
			bake_target_node = material.node_tree.nodes.new('ShaderNodeTexImage')
			bake_target_node.image = bake_image
			if if_node_input.node:
				bake_target_node.location = if_node_input.node.location
				bake_target_node.location.x -= 300
				bake_target_node.location.y += v_offset
		return bake_target_node


class BakeMaterial():
	"""
	Material, das gebaked werden soll. Enthält die referenz auf den Image Node, die UV Map und obe es sich um ein Dummy Material handelt.
	"""
	def __init__(self, material, input_socket, uv_map_name, image_node, channels):
		self.material = material
		self.uv_map_name = uv_map_name
		self.input_socket = input_socket
		self.socket_link = None
		self.output_to_bake = None
		self.channels = channels

		# Nodes
		self.image_node = image_node
		self.uv_node = None
		self.output_node = next(n for n in self.material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
		self.original_shader_output = [l.from_socket for l in self.output_node.inputs['Surface'].links]
		self.proxy_value_node = None


	def is_dummy(self):
		return self.output_to_bake is None


	def prepare(self):
		if self.input_socket:
			if len(self.input_socket.links) > 0:
				self.socket_link = self.input_socket.links[0]
				self.output_to_bake = self.socket_link.from_socket
			else:
				print(f"Creating proxy value node for {self.input_socket.name}")
				if self.input_socket.type in {'VALUE', 'INT', 'BOOLEAN'}:
					self.proxy_value_node = self.material.node_tree.nodes.new('ShaderNodeValue')
					self.proxy_value_node.outputs[0].default_value = self.input_socket.default_value
					self.output_to_bake = self.proxy_value_node.outputs['Value']
				else:
					self.proxy_value_node = self.material.node_tree.nodes.new('ShaderNodeRGB')
					self.proxy_value_node.outputs[0].default_value = self.input_socket.default_value
					self.output_to_bake = self.proxy_value_node.outputs['Color']
					
				self.proxy_value_node.location = self.input_socket.node.location
				self.proxy_value_node.location.x -= 200

		self.create_uv_node()
		if self.output_to_bake:
			self.material.node_tree.links.new(self.output_to_bake, self.output_node.inputs['Surface'])
		if self.image_node:
			self.image_node.select = True
			self.material.node_tree.nodes.active = self.image_node


	def _restore_output_node(self):
		for fs in self.original_shader_output:
			self.material.node_tree.links.new(fs, self.output_node.inputs['Surface'])


	def cleanup(self):
		'''
		Entfernt alle temporären Nodes und Links.
		'''
		if self.is_dummy() and self.image_node:
			self.material.node_tree.nodes.remove(self.image_node)
			if self.uv_node:
				self.material.node_tree.nodes.remove(self.uv_node)
			return

		self.material.node_tree.links.remove(self.output_node.inputs['Surface'].links[0])

		if not self.is_dummy():
			if self.input_socket.type in {'VALUE', 'INT', 'BOOLEAN'}:
				separate_node = self.material.node_tree.nodes.new('ShaderNodeSeparateColor')
				separate_node.location = self.image_node.location
				separate_node.location.x += 150
				
				self.material.node_tree.links.new(self.image_node.outputs['Color'], separate_node.inputs['Color'])
				
				channel_map = {'R': 'Red', 'G': 'Green', 'B': 'Blue'}
				if len(self.channels) != 1:
					raise ValueError(f"Expected exactly one channel for single-channel bake for material '{self.material.name}', but got {self.channels}.")

				channel_key = next(iter(self.channels))
				output_name = channel_map.get(channel_key)

				if output_name is None:
					raise ValueError(f"Invalid channel '{channel_key}' specified for material '{self.material.name}'. Must be one of {list(channel_map.keys())}.")

				self.material.node_tree.links.new(separate_node.outputs[output_name], self.input_socket)
			else:
				self.material.node_tree.links.new(self.image_node.outputs['Color'], self.input_socket)

		if self.proxy_value_node:
			self.material.node_tree.nodes.remove(self.proxy_value_node)

		self._restore_output_node()


	def rollback(self):
		'''
		Setzt den Material zurück auf den ursprünglichen Zustand.
		'''
		if not self.is_dummy():
			self.material.node_tree.links.new(self.output_to_bake, self.input_socket)
			self.material.node_tree.nodes.remove(self.image_node)
		if self.uv_node:
			self.material.node_tree.nodes.remove(self.uv_node)
		if self.proxy_value_node:
			self.material.node_tree.nodes.remove(self.proxy_value_node)
		self._restore_output_node()


	def create_uv_node(self):
		if self.is_dummy():
			return
		uv_node = self.material.node_tree.nodes.new('ShaderNodeUVMap')
		uv_node.uv_map = self.uv_map_name
		uv_node.location = self.image_node.location
		uv_node.location.x -= 200
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