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
	def __init__(self, object, settings):
		self.object = object
		self.settings = settings

class BakeMaterialSetting():
	def __init__(self, material, input_socket, uv_map_name, image, channels):
		self.material = material
		# Socket für den Bake. Kann Node sein, wenn es ein Dummy ist. 
		self.input_socket = input_socket
		self.uv_map_name = uv_map_name
		self.image = image
		self.channels = channels

	def is_dummy(self):
		return self.input_socket == None

def get_socket_channel_count(socket):
	if socket.type == 'FLOAT' or socket.type == 'INT' or socket.type == 'BOOLEAN':
		return 1
	elif socket.type == 'VECTOR' or socket.type == 'COLOR':
		return 3
	else:
		return 0