# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
from . import constants

class BakeData():
	def __init__(self):
		self.objects = []
		self.passes: list[BakePass] = []
		# Liste an Dummy Bildern, die hinterher wieder gelöscht werden.
		self.dummy_image = None

	def get_dummy_image(self):
		if not self.dummy_image:
			self.dummy_image = bpy.data.images.new(name=constants.DUMMY_IMAGE_NAME, width=1, height=1)
		return self.dummy_image

	def clear_images(self):
		images_to_clear = set()
		for bake_pass in self.passes:
			# Collect images from settings
			for setting in bake_pass.settings:
				if setting.image:
					images_to_clear.add(setting.image)
			
			# Collect images from cache (might be redundant but safe)
			for image in bake_pass.cached_images.values():
				images_to_clear.add(image)

		for image in images_to_clear:
			# Only clear images that have pixel data (generated images) and are not the dummy
			if image.has_data and image.name != constants.DUMMY_IMAGE_NAME:
				
				# Decide whether to clear based on the image's custom override or the global setting
				do_clear = bpy.context.scene.render.bake.use_clear # Global default
				if image.unity_bake_settings.use_override:
					do_clear = image.unity_bake_settings.clear_image # Per-image override
				
				if do_clear:
					print(f"Clearing image: {image.name} (Override: {image.unity_bake_settings.use_override})")
					# Fill with transparent black
					clear_color = [0.0, 0.0, 0.0, 0.0]
					pixels = clear_color * (image.width * image.height)
					image.pixels.foreach_set(pixels)
				else:
					print(f"Skipping clear for image: {image.name}")

	def validate(self):
		for obj in bpy.context.selected_objects:
			if obj.type != 'MESH':
				print(f"Objekt {obj.name} ist kein Mesh.")
				return False

		# Alle Passes haben Objekt und Settings
		for bake_pass in self.passes:
			if bake_pass.object == None:
				print("Kein Objekt im Pass")
				return False
			if len(bake_pass.settings) == 0:
				print("Keine Settings im Pass")
				return False

			# Alle Settings haben gültige UV Maps.
			for setting in bake_pass.settings:
				if not setting.is_dummy() and bake_pass.object.material_slots.get(setting.material.name):
					if not bake_pass.object.data.uv_layers.get(setting.uv_map_name):
						print(f"UV Map {setting.uv_map_name} nicht gefunden in {bake_pass.object.name}")
						return False

				# Alle Passes haben gültige Materialien.
				found = False
				if bake_pass.object.material_slots.get(setting.material.name):
					found = True
					break
				if not found:
					print(f"Material {setting.material.name} wurde im Objekt {bake_pass.object.name} nicht gefunden.")
					return False
			
			#for setting in bake_pass.settings:
			#	# Alle Sockets sind verbunden.
			#	if len(setting.input_socket.links) == 0:
			#		print(f"Socket {setting.input_socket.name} in Material {setting.material.name} ist nicht verbunden.")
			#		return False

		# Alle Materialien des Objekts sind in den Passes berücksichtigt
		for material in bake_pass.object.material_slots:
			found = False
			for setting in bake_pass.settings:
				if setting.material.name == material.material.name:
					found = True
					break
			if not found:
				print(f"Material {bake_pass.object.name}.{material.material.name} nicht gefunden.")
				return False

		# Prüfen, ob eine Object/Material/Socket-Kombination doppelt vorkommt.
		baked_sockets = set()
		for bake_pass in self.passes:
			for setting in bake_pass.settings:
				if not setting.is_dummy():
					# Tuple als Key für das Set
					key = (bake_pass.object, setting.material, setting.input_socket)
					if key in baked_sockets:
						print(f"Doppelte Anweisung zum Backen für {bake_pass.object.name} -> {setting.material.name} -> {setting.input_socket.name}")
						return False
					baked_sockets.add(key)

		return True


class BakePass():
	"""
	Ein Bake durchlauf mit allen Materialien.
	Blender erzwingt immer alle Materialien gleichzeitig zu backen.
	"""
	def __init__(self, object, settings, index):
		self.object = object
		self.settings = settings
		self.cached_images = {}
		self.index = index
		self.max_margin = 0

	def initialize_image(self, setting):
		socket_name = setting.input_socket.name
		if socket_name in self.cached_images:
			return self.cached_images[socket_name]

		print({'INFO'}, f"Creating new image for {socket_name}")
		setting.image = setting.image_meta.create(f"{self.object.name}_{socket_name}")
		self.cached_images[socket_name] = setting.image
		return setting.image


class BakeMaterialSetting():
	def __init__(self, material, input_socket, uv_map_name, channels, image, image_meta):
		self.material = material
		# Socket für den Bake. Kann None sein, wenn es ein Dummy ist. 
		self.input_socket = input_socket
		self.uv_map_name = uv_map_name
		self.image = image
		self.image_meta = image_meta
		self.channels = channels

	def is_dummy(self):
		return self.input_socket == None

	def get_target_image_name(self, bake_object):
		"""Returns the name of the target image for this setting."""
		if self.image:
			return self.image.name
		else:
			return f"{bake_object.name}_{self.input_socket.name}"


class ImageMeta():
	def __init__(self, bake_mode, resolution, margin, color_space):
		self.bake_mode = bake_mode
		self.resolution = resolution
		self.margin = margin
		self.color_space = color_space

	def is_new(self):
		return self.bake_mode == 'NEW'

	def create(self, name):
		image = bpy.data.images.new(
			name=name,
			width=self.resolution,
			height=self.resolution
		)
		image.colorspace_settings.name = self.color_space
		return image

CHANNEL_MAP = {'R': 'Red', 'G': 'Green', 'B': 'Blue'}

class ImageNodeProxy():
	def __init__(self, material, image_node, was_created=False):
		if not image_node:
			raise ValueError(f"Invalid image node in {material.name}.")

		print(f"ImageNodeProxy: {material.name} {image_node.image.name} was_created: {was_created}")

		self.material = material
		self.image_node = image_node
		self.separate_node = None
		self.location = self.image_node.location if self.image_node else 0
		self.was_created = was_created
		self.uv_node = None

	def connect_to(self, socket, channels):
		if is_single_channel_socket(socket):
			if len(channels) != 1:
				raise ValueError(f"Expected exactly one channel for single-channel bake for material '{self.material.name}', but got {channels}.")

			channel_key = next(iter(channels))
			output_name = CHANNEL_MAP.get(channel_key)

			if output_name is None:
				raise ValueError(f"Invalid channel '{channel_key}' specified for material '{self.material.name}'. Must be one of {list(CHANNEL_MAP.keys())}.")

			if not self.separate_node:
				self.separate_node = self.material.node_tree.nodes.new('ShaderNodeSeparateColor')
				self.separate_node.location = self.image_node.location
				self.material.node_tree.links.new(self.image_node.outputs['Color'], self.separate_node.inputs['Color'])

				self.image_node.location.x -= 150
				self.location = self.image_node.location
			
			self.material.node_tree.links.new(self.separate_node.outputs[output_name], socket)
		else:
			self.material.node_tree.links.new(self.image_node.outputs['Color'], socket)

	def connect_alpha_to(self, socket):
		self.material.node_tree.links.new(self.image_node.outputs['Alpha'], socket)

	def add_uv(self, uv_map_name):
		if not self.uv_node:
			self.uv_node = self.material.node_tree.nodes.new('ShaderNodeUVMap')
			self.uv_node.uv_map = uv_map_name
			self.uv_node.location = self.image_node.location
			self.uv_node.location.x -= 200
		self.material.node_tree.links.new(self.uv_node.outputs['UV'], self.image_node.inputs['Vector'])

	def select(self):
		self.image_node.select = True
		self.material.node_tree.nodes.active = self.image_node

	def remove(self, rollback=False):
		if self.image_node and (self.was_created or rollback):
			self.material.node_tree.nodes.remove(self.image_node)
		if self.separate_node:
			self.material.node_tree.nodes.remove(self.separate_node)
		if self.uv_node:
			self.material.node_tree.nodes.remove(self.uv_node)
		self.uv_node = None
		self.separate_node = None

def is_single_channel_socket(socket):
	return socket and socket.type in {'VALUE', 'INT', 'BOOLEAN'}

def is_value_socket(socket):
	return socket and socket.type in {'VALUE', 'INT', 'BOOLEAN', 'VECTOR'}