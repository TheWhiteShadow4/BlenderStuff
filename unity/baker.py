# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import traceback
from . import bake_utils
from . import constants
import bpy

# Magic Numbers für Node-Layout
_NODE_OFFSET_VERTICAL = 250    # Vertikaler Abstand zwischen Bake-Pass-Nodes
_NODE_OFFSET_HORIZONTAL = 300  # Horizontaler Abstand vom Socket

class Baker():
	def __init__(self, bake_data: bake_utils.BakeData):
		self.bake_data = bake_data
		self.dummy_image = None
		self.diffuse_pipeline = False
		self.material_metadata = {}
		# Index des Passes, der Debugged werden soll. Der Prozess wird nach diesem Pass beendet und die Nodes werden nicht aufgeräumt.
		self.debug_pass_idx = -1
	
	def get_or_create_dummy_image(self):
		if not self.dummy_image:
			self.dummy_image = bpy.data.images.new(name=constants.DUMMY_IMAGE_NAME, width=1, height=1)
			self.dummy_image.generated_type = 'BLANK'
		return self.dummy_image

	def bake(self):
		self.warnings = []
		self.objects = []

		for obj in bpy.context.selected_objects:
			self.objects.append(obj)

		# globalen State speichern
		preserved_global_state = self._preserve_global_state()
		next(preserved_global_state)

		try:
			# States setzen
			bpy.context.scene.render.engine = 'CYCLES'
			bpy.context.scene.render.bake.use_clear = False

			if self.debug_pass_idx >= 0:
				self.bake_data.passes = [self.bake_data.passes[self.debug_pass_idx]]
			
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
		try:
			print({'INFO'}, f"Prepare '{bake_pass.object.name}'.")
			self._collect_materials_for_pass(bake_pass, self.diffuse_pipeline)
			for material_metadata in self.material_metadata.values():
				material_metadata.prepare()
			for bake_socket in self.bake_sockets:
				bake_socket.prepare(self.material_metadata[bake_socket.material])

			# Blender Bake Operation ausführen.
			if self.diffuse_pipeline:
				bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, save_mode='INTERNAL', margin=bake_pass.max_margin)
			else:
				bpy.ops.object.bake(type='EMIT', save_mode='INTERNAL', margin=bake_pass.max_margin)
			
			# Cleanup
			if self.debug_pass_idx < 0:
				for bake_socket in self.bake_sockets:
					bake_socket.cleanup_pass()
				for material_metadata in self.material_metadata.values():
					material_metadata.cleanup()

		except Exception as e:
			print("Führe Rollback aus.")
			for bake_socket in self.bake_sockets:
				bake_socket.rollback()
			for material_metadata in self.material_metadata.values():
				material_metadata.cleanup()
			raise e


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

	def _collect_materials_for_pass(self, bake_pass, diffuse_pipeline):
		'''
		Sammelt alle Materialien aus den ausgewählten Objekten. 
		Jedes Material muss nur einaml verarbeitet werden.
		'''
		self.bake_sockets = []
		for setting in bake_pass.settings:
			mat = setting.material
			if mat not in self.material_metadata:
				self.material_metadata[mat] = MaterialMetadata(mat, diffuse_pipeline)

			image: bpy.types.Image = setting.image
			if setting.is_dummy():
				image = self.get_or_create_dummy_image()
			elif image == None:
				image = bake_pass.initialize_image(setting)

			v_offset = (len(self.bake_data.passes) / 2 - bake_pass.index) * _NODE_OFFSET_VERTICAL

			image_node = self.material_metadata[mat].get_image_proxy(setting.input_socket, image, v_offset)
			bake_material = BakeMaterial(mat, setting.input_socket, setting.uv_map_name, image_node, setting.channels)

			print({'INFO'}, f"Adding baking material {mat.name}.")
			self.bake_sockets.append(bake_material)


class MaterialMetadata():
	def __init__(self, material, diffuse_pipeline):
		self.material = material
		self.image_proxies = {}
		self.combine_node = None
		self.diffuse_pipeline = diffuse_pipeline
		self.diffuse_node = None
		self.alpha_node = None
		self.shader_mix_node = None

		self.output_node = next(n for n in self.material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
		if self.output_node == None:
			raise ValueError(f"Output node not found for material {self.material.name}.")
		self.proxy_output_pin = self.output_node.inputs['Surface']
		self.original_shader_output = [l.from_socket for l in self.proxy_output_pin.links]

	def get_image_proxy(self, socket, image, v_offset):
		image_proxy = self.image_proxies.get(image)
		if not image_proxy:
			image_node = None
			was_created = False
			if image not in self.image_proxies:
				for node in self.material.node_tree.nodes:
					if node.type == 'TEX_IMAGE' and node.image == image:
						image_node = node
						break

			if not image_node:
				image_node = self.material.node_tree.nodes.new('ShaderNodeTexImage')
				image_node.image = image
				was_created = True
				if socket:
					image_node.location = socket.node.location
					image_node.location.x -= _NODE_OFFSET_HORIZONTAL
					image_node.location.y += v_offset
			image_proxy = bake_utils.ImageNodeProxy(self.material, image_node, was_created)
			self.image_proxies[image] = image_proxy
		return image_proxy

	def prepare(self):
		self.proxy_output_pin = self.output_node.inputs['Surface']
		if self.diffuse_pipeline:
			self.diffuse_node = self.material.node_tree.nodes.new('ShaderNodeBsdfDiffuse')
			self.alpha_node = self.material.node_tree.nodes.new('ShaderNodeBsdfTransparent')
			self.shader_mix_node = self.material.node_tree.nodes.new('ShaderNodeMixShader')
			self.shader_mix_node.inputs['Fac'].default_value = 1.0
			self.material.node_tree.links.new(self.shader_mix_node.outputs['Shader'], self.proxy_output_pin)
			self.material.node_tree.links.new(self.diffuse_node.outputs['BSDF'], self.shader_mix_node.inputs[2])
			self.material.node_tree.links.new(self.alpha_node.outputs['BSDF'], self.shader_mix_node.inputs[1])
			self.proxy_output_pin = self.diffuse_node.inputs['Color']

	def connect_color(self, output_to_bake, _channels):
		self.material.node_tree.links.new(output_to_bake, self.proxy_output_pin)

	def connect_single(self, output_to_bake, ch):
		if ch == 'A':
			if self.shader_mix_node:
				self.material.node_tree.links.new(output_to_bake, self.shader_mix_node.inputs['Fac'])
			else:
				raise ValueError(f"Alpha channel is only supported in diffuse pipeline.")
		else:
			if not self.combine_node:
				self.combine_node = self.material.node_tree.nodes.new('ShaderNodeCombineRGB')
				self.material.node_tree.links.new(self.combine_node.outputs['Image'], self.proxy_output_pin)
			self.material.node_tree.links.new(output_to_bake, self.combine_node.inputs[ch])


	def cleanup(self):
		self.proxy_output_pin = self.output_node.inputs['Surface']
		for fs in self.original_shader_output:
			self.material.node_tree.links.new(fs, self.proxy_output_pin)
		
		if self.combine_node:
			self.material.node_tree.nodes.remove(self.combine_node)
			self.combine_node = None
		if self.diffuse_node:
			self.material.node_tree.nodes.remove(self.diffuse_node)
			self.diffuse_node = None
		if self.alpha_node:
			self.material.node_tree.nodes.remove(self.alpha_node)
			self.alpha_node = None
		if self.shader_mix_node:
			self.material.node_tree.nodes.remove(self.shader_mix_node)
			self.shader_mix_node = None


class BakeMaterial():
	"""
	Material, das gebaked werden soll. Enthält die referenz auf den Image Node, die UV Map und obe es sich um ein Dummy Material handelt.
	"""
	def __init__(self, material, input_socket, uv_map_name, image_node, channels):
		self.material = material
		self.uv_map_name = uv_map_name
		self.input_socket = input_socket
		self.alpha_socket = None
		self.socket_link = None
		self.output_to_bake = None
		self.alpha_to_bake = None
		self.channels = channels

		# Nodes
		self.image_node = image_node
		self.uv_node = None
		self.proxy_value_node = None


	def is_dummy(self):
		return self.output_to_bake is None


	def prepare(self, metadata: MaterialMetadata):
		if not self.image_node:
			raise ValueError(f"Image node not found for material {self.material.name}.")

		if self.input_socket:
			if len(self.input_socket.links) > 0:
				self.socket_link = self.input_socket.links[0]
				self.output_to_bake = self.socket_link.from_socket
			else:
				print(f"Creating proxy value node for {self.input_socket.name}")
				if bake_utils.is_single_channel_socket(self.input_socket):
					self.proxy_value_node = self.material.node_tree.nodes.new('ShaderNodeValue')
					self.proxy_value_node.outputs[0].default_value = self.input_socket.default_value
					self.output_to_bake = self.proxy_value_node.outputs['Value']
				else:
					self.proxy_value_node = self.material.node_tree.nodes.new('ShaderNodeRGB')
					self.proxy_value_node.outputs[0].default_value = self.input_socket.default_value
					self.output_to_bake = self.proxy_value_node.outputs['Color']
					
				self.proxy_value_node.location = self.input_socket.node.location
				self.proxy_value_node.location.x -= 200

		if self.output_to_bake:
			if bake_utils.is_single_channel_socket(self.input_socket):
				for ch in self.channels:
					metadata.connect_single(self.output_to_bake, ch)
			else:
				metadata.connect_color(self.output_to_bake, self.input_socket)
				if 'A' in self.channels:
					self.alpha_to_bake = self.find_alpha_input()
					if self.alpha_to_bake:
						metadata.connect_single(self.alpha_to_bake, 'A')


		if not self.is_dummy():
			self.image_node.add_uv(self.uv_map_name)
		self.image_node.select()


	def cleanup(self):
		if self.is_dummy() and self.image_node:
			self.image_node.remove()
			return


	def cleanup_pass(self):
		if self.is_dummy():
			self.image_node.remove()
			return
		
		self.image_node.connect_to(self.input_socket, self.channels)
		if self.alpha_to_bake:
			self.image_node.connect_alpha_to(self.alpha_socket)

		if self.proxy_value_node:
			self.material.node_tree.nodes.remove(self.proxy_value_node)


	def rollback(self):
		'''
		Setzt den Material zurück auf den ursprünglichen Zustand.
		'''
		if not self.is_dummy():
			self.material.node_tree.links.new(self.output_to_bake, self.input_socket)
		self.image_node.remove(rollback=True)
		if self.proxy_value_node:
			self.material.node_tree.nodes.remove(self.proxy_value_node)
			self.proxy_value_node = None


	def find_alpha_input(self):
		alpha_input_name = f"{self.input_socket.name}_Alpha"
		alpha_socket = self.input_socket.node.inputs[alpha_input_name]
		if alpha_socket and alpha_socket.is_linked:
			self.alpha_socket = alpha_socket
			return alpha_socket.links[0].from_socket
		return None


def get_interface_node(material):
	"""Finds and returns the main interface node group for a given object if it's valid."""
	if not material.use_nodes:
		return None
	output_node = next((n for n in material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
	if not (output_node and output_node.inputs['Surface'].links):
		return None
	interface_node = output_node.inputs['Surface'].links[0].from_node
	return interface_node # if interface_node.type == 'GROUP' else None