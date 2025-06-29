# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy

class BakeData():
	def __init__(self):
		self.objects = []
		self.passes: list[BakePass] = []
		# Liste an Dummy Bildern, die hinterher wieder gelöscht werden.
		self.dummy_image = None

	def get_dummy_image(self):
		if not self.dummy_image:
			self.dummy_image = bpy.data.images.new(name="Dummy Image", width=1, height=1)
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
			if image.has_data and image.name != self.get_dummy_image().name:
				
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

#class BakeMaterial():
# 	def __init__(self, material, settings):
# 		self.material = material
# 		self.settings = settings
# 		self.has_interface = settings != None

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

	def get_or_create_image_for_setting(self, setting):
		socket_name = setting.input_socket.name
		if socket_name in self.cached_images:
			return self.cached_images[socket_name]

		print({'INFO'}, f"Creating new image for {socket_name}")
		image = bpy.data.images.new(
			name=f"{self.object.name}_Bake_{socket_name}",
			width=setting.resolution,
			height=setting.resolution
		)
		image.colorspace_settings.name = setting.color_space
		self.cached_images[socket_name] = image
		return image

class BakeMaterialSetting():
	def __init__(self, material, input_socket, uv_map_name, image, channels, bake_mode, resolution, margin, color_space):
		self.material = material
		# Socket für den Bake. Kann Node sein, wenn es ein Dummy ist. 
		self.input_socket = input_socket
		self.uv_map_name = uv_map_name
		self.image = image
		self.channels = channels
		self.bake_mode = bake_mode
		self.resolution = resolution
		self.margin = margin
		self.color_space = color_space

	def is_dummy(self):
		return self.input_socket == None

	def get_target_image_name(self, bake_object):
		"""Returns the name of the target image for this setting."""
		if self.bake_mode == 'EXISTING' and self.image:
			return self.image.name
		elif self.bake_mode == 'NEW' and self.input_socket:
			# Reconstruct the name that will be generated later by the baker
			return f"{bake_object.name}_Bake_{self.input_socket.name}"
		return "Unknown Image"

def get_socket_channel_count(socket):
	if socket.type == 'FLOAT' or socket.type == 'INT' or socket.type == 'BOOLEAN':
		return 1
	elif socket.type == 'VECTOR' or socket.type == 'COLOR':
		return 3
	else:
		return 0