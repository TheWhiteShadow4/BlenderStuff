# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
from . import baker
from . import bake_utils


class UNITY_PT_main_panel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport"""
    bl_label = "Unity Tools"
    bl_idname = "UNITY_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Unity'

    def draw(self, context):
        layout = self.layout

        # Reload button
        row = layout.row()
        row.operator("script.reload", text="Reload Addon", icon='FILE_REFRESH')

        scene = context.scene
        unity_props = scene.unity_tool_properties

        # Section for Operators
        box = layout.box()
        row = box.row()
        row.operator("unity.apply_rotation_fix", text="Fix Rotation for Unity")
        box = layout.box()
        row = box.row()
        row.prop(unity_props, "apply_gamma_correction")
        row = box.row()
        row.operator("unity.quick_export", text="Quick Export")

        # Section for Advanced Operations
        box = layout.box()
        box.label(text="Baking")
        row = box.row()
        row.operator("unity.bake_and_link", text="Bake Procedural Textures")
        row = box.row()
        row.operator("unity.create_baking_data", text="Bake to new Object")

        # Section for Settings
        box = layout.box()
        box.label(text="Game Engine Settings")
        row = box.row()
        row.prop(unity_props, "engine_project_path", text="Project")

        if unity_props.engine_version:
            row = box.row()
            row.label(text=f"Version: {unity_props.engine_version}", icon='INFO')

        if unity_props.engine_project_path and not unity_props.is_path_valid:
            row = box.row()
            row.alert = True
            row.label(text="Invalid Project Path", icon='ERROR')

        row = box.row()
        row.prop(unity_props, "export_path", text="Export Path")


def get_bakeable_sockets(self, context):
	"""EnumProperty callback to get bakeable sockets from the material's node group."""
	items = [] # Start with an empty list
	if not context.material:
		return items

	interface_node = baker.get_interface_node_in_material(context.material)
	if not interface_node:
		return items # Return empty list for unsupported materials

	# For supported materials, add "None" as the first option
	items.append(("NONE", "None", "Do not bake anything"))
	for socket in interface_node.inputs:
		identifier = socket.name
		name = socket.name
		description = f"Bake the input '{socket.name}'"
		items.append((identifier, name, description))
	
	return items


def get_uv_maps(self, context):
	"""EnumProperty callback to get all UV maps from the active object."""
	items = []
	if not context.object or context.object.type != 'MESH':
		return [("NONE", "No UV Maps", "Object has no UV maps")]

	for uv_layer in context.object.data.uv_layers:
		items.append((uv_layer.name, uv_layer.name, f"Use UV map '{uv_layer.name}'"))

	if not items:
		return [("NONE", "No UV Maps", "Object has no UV maps")]
	
	return items

def get_socket_type(context):
	"""
	Returns the type of the currently selected socket,
	respecting whether the active material is using a global or override setting.
	"""
	if not context.object or not context.material:
		return None
	
	settings = context.object.unity_bake_settings
	if settings.active_index < 0 or len(settings.presets) == 0:
		return None
	active_preset = settings.presets[settings.active_index]

	# Find the override for the active material
	active_override = None
	for o in active_preset.material_overrides:
		if o.material == context.material:
			active_override = o
			break
	
	# Determine which settings object (preset or override) is currently active
	source = active_preset
	if active_override and active_override.use_override:
		source = active_override

	socket_name = source.target_socket_name
	if socket_name == "NONE":
		return None

	interface_node = baker.get_interface_node_in_material(context.material)
	if not interface_node:
		return None
	
	socket = interface_node.inputs.get(socket_name)
	return socket.type if socket else None


def on_update_target_socket_data(self, context):
	"""When the bake target name changes, reset UV map and channel settings."""
	if self.target_socket_name != "NONE":
		if context.object and context.object.type == 'MESH' and len(context.object.data.uv_layers) > 0:
			self.uv_map = context.object.data.uv_layers[0].name
		self.single_channel_target = 'R'
		self.multi_channel_targets = {'R', 'G', 'B'}
	return None

def on_update_target_socket_enum(self, context):
	"""When the UI enum changes, write its value to the persistent string property and run updates."""
	self.target_socket_name = self.target_socket
	on_update_target_socket_data(self, context)
	return None

def on_update_uv_map_enum(self, context):
	"""When the UI enum for UV map changes, write its value to the persistent string property."""
	self.uv_map_name = self.uv_map
	return None

class MaterialBakeOverride(bpy.types.PropertyGroup):
	"""Stores all material-specific override settings for a bake operation."""
	name: bpy.props.StringProperty()
	material: bpy.props.PointerProperty(type=bpy.types.Material)

	use_override: bpy.props.BoolProperty(
		name="Override Global Settings",
		description="Use custom settings for this material instead of the global preset settings",
		default=False
	)

	target_socket: bpy.props.EnumProperty(items=get_bakeable_sockets, update=on_update_target_socket_enum, name="Target Input")
	target_socket_name: bpy.props.StringProperty() # Hidden property to store the actual name persistently

	single_channel_target: bpy.props.EnumProperty(items=[('R', "R", ""), ('G', "G", ""), ('B', "B", "")])
	multi_channel_targets: bpy.props.EnumProperty(items=[('R', "R", ""), ('G', "G", ""), ('B', "B", "")], options={'ENUM_FLAG'}, name="Channels")
	bake_mode: bpy.props.EnumProperty(items=[('NEW', "New", ""), ('EXISTING', "Existing", "")], default='NEW', name="Mode")
	resolution: bpy.props.IntProperty(name="Resolution", default=1024, min=64, max=8192)
	existing_image: bpy.props.PointerProperty(name="Image", type=bpy.types.Image)
	uv_map: bpy.props.EnumProperty(name="UV Map", items=get_uv_maps, update=on_update_uv_map_enum)
	uv_map_name: bpy.props.StringProperty()


class BakePreset(bpy.types.PropertyGroup):
    """A single, named bake configuration with global settings and per-material overrides."""
    name: bpy.props.StringProperty(name="Name", default="Bake Preset")
    is_active: bpy.props.BoolProperty(name="Active", default=True)
    
    # --- Global Settings ---
    target_socket: bpy.props.EnumProperty(name="Target Input", items=get_bakeable_sockets, update=on_update_target_socket_enum)
    target_socket_name: bpy.props.StringProperty() # Hidden property to store the actual name persistently

    uv_map: bpy.props.EnumProperty(name="UV Map", items=get_uv_maps, update=on_update_uv_map_enum)
    uv_map_name: bpy.props.StringProperty()
    single_channel_target: bpy.props.EnumProperty(items=[('R', "R", ""), ('G', "G", ""), ('B', "B", "")], default='R')
    multi_channel_targets: bpy.props.EnumProperty(name="Channels", items=[('R', "R", ""), ('G', "G", ""), ('B', "B", "")], options={'ENUM_FLAG'}, default={'R', 'G', 'B'})
    bake_mode: bpy.props.EnumProperty(name="Mode", items=[('NEW', "New", ""), ('EXISTING', "Existing", "")], default='NEW')
    resolution: bpy.props.IntProperty(name="Resolution", default=1024, min=64, max=8192)
    existing_image: bpy.props.PointerProperty(name="Image", type=bpy.types.Image)

    # --- Per-Material Overrides ---
    material_overrides: bpy.props.CollectionProperty(type=MaterialBakeOverride)

class ObjectBakeSettings(bpy.types.PropertyGroup):
	"""Stores a collection of bake presets for an object."""
	presets: bpy.props.CollectionProperty(type=BakePreset)
	active_index: bpy.props.IntProperty(name="Active Preset Index", default=0)


class UNITY_OT_toggle_bake_channel(bpy.types.Operator):
	"""Toggle a channel in the multi-channel bake setting, respecting overrides."""
	bl_idname = "unity_bake.toggle_channel"
	bl_label = "Toggle Bake Channel"
	bl_options = {'REGISTER'}

	channel: bpy.props.StringProperty()

	@classmethod
	def poll(cls, context):
		if not context.object or not context.material: return False
		settings = context.object.unity_bake_settings
		if not (settings.active_index >= 0 and len(settings.presets) > 0): return False
		active_preset = settings.presets[settings.active_index]
		for o in active_preset.material_overrides:
			if o.material == context.material: return True
		return False

	def execute(self, context):
		settings = context.object.unity_bake_settings
		active_preset = settings.presets[settings.active_index]
		
		active_override = None
		for o in active_preset.material_overrides:
			if o.material == context.material:
				active_override = o
				break
		if not active_override: return {'CANCELLED'}

		source = active_preset
		if active_override.use_override:
			source = active_override

		current_channels = set(source.multi_channel_targets)
		if self.channel in current_channels:
			current_channels.remove(self.channel)
		else:
			current_channels.add(self.channel)
		
		source.multi_channel_targets = current_channels
		context.area.tag_redraw()
		return {'FINISHED'}


class UNITY_UL_bake_presets(bpy.types.UIList):
    """UIList for displaying bake presets."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "is_active", text="")
            row.prop(item, "name", text="", emboss=False, icon_value=icon)
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)


def _safe_reset_socket(preset_or_override):
    """Timer callback to safely reset the target_socket if it's invalid."""
    preset_or_override.target_socket = "NONE"
    return None


def draw_bake_settings_ui(layout, context, source):
    """Helper function to draw the common bake settings UI.
    NOTE: This function does NOT validate the target_socket. The caller must do so.
    """
    
    layout.prop(source, "target_socket")
    
    # Stop drawing if no valid target is selected
    if source.target_socket == "NONE":
        return

    # --- Dynamic Channel Selection ---
    socket_type = get_socket_type(context)
    if socket_type in {'VALUE', 'INT', 'BOOLEAN'}:
        row = layout.row(align=True)
        row.label(text="Bake to Channel:")
        sub = row.row(align=True)
        sub.prop(source, "single_channel_target", expand=True, text="RGB")
    
    elif socket_type in {'VECTOR', 'RGBA'}:
        row = layout.row(align=True)
        row.label(text="Bake Channels:")
        sub = row.row(align=True)
        op_r = sub.operator(UNITY_OT_toggle_bake_channel.bl_idname, text="R", depress=('R' in source.multi_channel_targets))
        op_r.channel = 'R'
        op_g = sub.operator(UNITY_OT_toggle_bake_channel.bl_idname, text="G", depress=('G' in source.multi_channel_targets))
        op_g.channel = 'G'
        op_b = sub.operator(UNITY_OT_toggle_bake_channel.bl_idname, text="B", depress=('B' in source.multi_channel_targets))
        op_b.channel = 'B'

    # --- Other Bake Settings ---
    settings_box = layout.box()
    col = settings_box.column()
    col.prop(source, "uv_map")
    col.separator()
    col.prop(source, "bake_mode")
    if source.bake_mode == 'NEW':
        col.prop(source, "resolution")
    elif source.bake_mode == 'EXISTING':
        col.prop(source, "existing_image")


class UNITY_PT_baking_panel(bpy.types.Panel):
    bl_label = "Baking Presets"
    bl_idname = "UNITY_PT_baking_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        settings = context.object.unity_bake_settings

        row = layout.row()
        row.template_list("UNITY_UL_bake_presets", "", settings, "presets", settings, "active_index")
        col = row.column(align=True)
        col.operator(UNITY_OT_add_bake_preset.bl_idname, icon='ADD', text="")
        col.operator(UNITY_OT_remove_bake_preset.bl_idname, icon='REMOVE', text="")

        if settings.active_index >= 0 and len(settings.presets) > 0:
            active_preset = settings.presets[settings.active_index]
            box = layout.box()

            active_material = context.material
            if not active_material:
                box.label(text="Select a material to configure settings.", icon='INFO')
                return

            interface_node = baker.get_interface_node_in_material(active_material)
            if not interface_node:
                box.label(text="Unsupported material node setup", icon='ERROR')
                return

            active_override = None
            for o in active_preset.material_overrides:
                if o.material == active_material:
                    active_override = o
                    break
            
            if not active_override:
                box.label(text=f"No bake settings for '{active_material.name}'.", icon='ERROR')
                return

            # --- Main Settings UI ---
            col = box.column()
            col.prop(active_override, "use_override")

            if active_override.use_override:
                sub_box = box.box()
                # Validate and reset the OVERRIDE's socket if it's invalid for this material
                valid_socket_items = get_bakeable_sockets(active_override, context)
                valid_socket_identifiers = {item[0] for item in valid_socket_items}
                if active_override.target_socket not in valid_socket_identifiers:
                    bpy.app.timers.register(lambda p=active_override: _safe_reset_socket(p))
                
                draw_bake_settings_ui(sub_box, context, active_override)
            else: # Using global settings
                sub_box = box.box()

                # Check if the PRESET's socket is compatible with this material
                valid_socket_items = get_bakeable_sockets(active_preset, context)
                valid_socket_identifiers = {item[0] for item in valid_socket_items}

                if active_preset.target_socket_name not in valid_socket_identifiers and active_preset.target_socket_name != '':
                    # If not compatible, show an error and stop.
                    sub_box.label(text=f"Global input '{active_preset.target_socket_name}' not found on this material.", icon='ERROR')
                    sub_box.label(text="Create an override to select a different input.")
                else:
                    # If compatible, just draw the UI. The enum will handle showing "(Not Found)" if needed.
                    draw_bake_settings_ui(sub_box, context, active_preset)


class UNITY_OT_add_bake_preset(bpy.types.Operator):
    """Add a new bake preset to the list"""
    bl_idname = "unity_bake.add_preset"
    bl_label = "Add Bake Preset"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        settings = context.object.unity_bake_settings
        new_preset = settings.presets.add()
        new_preset.name = f"Preset {len(settings.presets)}"

        # Populate material overrides
        new_preset.material_overrides.clear()
        if context.object:
            if context.object.type == 'MESH' and len(context.object.data.uv_layers) > 0:
                uv_name = context.object.data.uv_layers[0].name
                new_preset.uv_map = uv_name
                new_preset.uv_map_name = uv_name

            for mat_slot in context.object.material_slots:
                if mat_slot.material:
                    override = new_preset.material_overrides.add()
                    override.name = mat_slot.material.name
                    override.material = mat_slot.material
                    override.uv_map = new_preset.uv_map
                    override.uv_map_name = new_preset.uv_map_name

        settings.active_index = len(settings.presets) - 1
        return {'FINISHED'}


class UNITY_OT_create_baking_data(bpy.types.Operator):
	"""Create baking data for the selected object"""
	bl_idname = "unity.create_baking_data"
	bl_label = "Create Baking Data"
	bl_options = {'REGISTER', 'UNDO'}

	def convert_setting(self, mat, setting, socket, channels):
		image = setting.existing_image if setting.bake_mode == 'EXISTING' else None
		return bake_utils.BakeMaterialSetting(mat, socket, setting.uv_map_name, image, channels)

	def create_baking_data(self, bake_data, obj):
		if len(obj.unity_bake_settings.presets) == 0:
			return

		all_materials = [ms.material for ms in obj.material_slots if ms.material]

		for preset in obj.unity_bake_settings.presets:
			if not preset.is_active:
				continue
			
			pass_settings = []
			is_pass_effective = False 
			# A dictionary to track [ (image, uv_map) -> { channel: source_socket_name } ] for this pass
			pass_bake_targets = {}

			for material in all_materials:
				interface = baker.get_interface_node_in_material(material)
				
				# Find effective setting source (preset or override)
				effective_setting = preset
				if interface:
					for o in preset.material_overrides:
						if o.material == material and o.use_override:
							effective_setting = o
							break

				# Use the effective setting source to create the bake instruction
				socket_name = effective_setting.target_socket_name
				socket = interface.inputs.get(socket_name) if interface and socket_name != "NONE" else None

				if socket:
					# This is a REAL bake operation for this material in this pass
					socket_type = socket.type
					if socket_type in {'VALUE', 'INT', 'BOOLEAN'}:
						channels = {effective_setting.single_channel_target}
					else:
						channels = effective_setting.multi_channel_targets
					
					# --- New, more precise validation logic ---
					if effective_setting.bake_mode == 'EXISTING':
						image = effective_setting.existing_image
						if not image:
							self.report({'ERROR'}, f"Bake mode is 'Existing' but no image is selected in preset '{preset.name}' for material '{material.name}'.")
							return {'CANCELLED'}

						uv_map_name = effective_setting.uv_map_name
						target_key = (image, uv_map_name)

						if target_key not in pass_bake_targets:
							pass_bake_targets[target_key] = {} # Stores { channel: source_socket_name }

						for ch in channels:
							if ch in pass_bake_targets[target_key] and pass_bake_targets[target_key][ch] != socket.name:
								conflicting_socket_name = pass_bake_targets[target_key][ch]
								self.report({'ERROR'}, (
									f"Bake conflict in preset '{preset.name}':\n"
									f"- Image: '{image.name}'\n"
									f"- UV Map: '{uv_map_name}'\n"
									f"- Channel: '{ch}'\n"
									f"Is targeted by both '{socket.name}' and '{conflicting_socket_name}'."
								))
								return {'CANCELLED'}
							else:
								pass_bake_targets[target_key][ch] = socket.name

					bake_material_setting = self.convert_setting(material, effective_setting, socket, channels)
					pass_settings.append(bake_material_setting)
					is_pass_effective = True
				else:
					# This is a DUMMY operation
					dummy_setting = bake_utils.BakeMaterialSetting(material, None, None, None, None)
					pass_settings.append(dummy_setting)

			if is_pass_effective:
				bake_data.passes.append(bake_utils.BakePass(obj, pass_settings))


	def execute(self, context):
		print("--- Raw Bake Settings ---")
		for obj in context.selected_objects:
			if not hasattr(obj, 'unity_bake_settings') or not obj.unity_bake_settings.presets:
				continue
			print(f"Object: {obj.name}")
			for i, preset in enumerate(obj.unity_bake_settings.presets):
				print(f"  Preset #{i}: '{preset.name}' (Active: {preset.is_active})")
				if not preset.is_active:
					continue
				
				print(f"    Global Settings:")
				print(f"      Target Socket: {preset.target_socket_name}")
				print(f"      UV Map: {preset.uv_map_name}")
				print(f"      Bake Mode: {preset.bake_mode}")
				if preset.bake_mode == 'NEW':
					print(f"      Resolution: {preset.resolution}")
				elif preset.bake_mode == 'EXISTING':
					image_name = preset.existing_image.name if preset.existing_image else 'None'
					print(f"      Image: {image_name}")
					
				print(f"    Material Overrides ({len(preset.material_overrides)}):")
				for j, override in enumerate(preset.material_overrides):
					mat_name = override.material.name if override.material else 'None'
					print(f"      - Mat: '{mat_name}', Use Override: {override.use_override}")
					if override.use_override:
						print(f"          Target Socket: {override.target_socket_name}")
						print(f"          UV Map: {override.uv_map_name}")
						print(f"          Bake Mode: {override.bake_mode}")
						if override.bake_mode == 'NEW':
							print(f"          Resolution: {override.resolution}")
						elif override.bake_mode == 'EXISTING':
							image_name = override.existing_image.name if override.existing_image else 'None'
							print(f"          Image: {image_name}")
		print("---------------------------")

		bake_data = bake_utils.BakeData()

		selected_objects_with_presets = [obj for obj in context.selected_objects if len(obj.unity_bake_settings.presets) > 0]

		for obj in selected_objects_with_presets:
			result = self.create_baking_data(bake_data, obj)
			if result and 'CANCELLED' in result:
				return result

		print("--------------------------------")
		print(f"Baking {len(bake_data.passes)} passes")
		for n, bake_pass in enumerate(bake_data.passes):
			effective = [x for x in bake_pass.settings if not x.is_dummy()]
			print(f"Pass #{n} Effektiv: {len(effective)} / {len(bake_pass.settings)}; Objekt: {bake_pass.object.name}; Materialien: {len(bake_pass.object.material_slots)}")
			for setting in bake_pass.settings:
				socket_name = setting.input_socket.name if setting.input_socket else "NONE"
				print(f"	Socket: {socket_name} in {setting.material.name}; UV: {setting.uv_map_name} -> {setting.channels} in {setting.image.name if setting.image else 'None'}")

		is_valid = bake_data.validate()
		print(f"Valid: {is_valid}")
		if not is_valid:
			self.report({'ERROR'}, "Bake data validation failed. Check console for details.")
			return {'CANCELLED'}

		return {'FINISHED'}


class UNITY_OT_remove_bake_preset(bpy.types.Operator):
    """Remove the selected bake preset from the list"""
    bl_idname = "unity_bake.remove_preset"
    bl_label = "Remove Bake Preset"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if context.object:
            settings = context.object.unity_bake_settings
            return len(settings.presets) > 0
        return False

    def execute(self, context):
        settings = context.object.unity_bake_settings
        index = settings.active_index
        settings.presets.remove(index)
        if index >= len(settings.presets):
            settings.active_index = max(0, len(settings.presets) - 1)
        return {'FINISHED'}


def register():
    bpy.utils.register_class(UNITY_PT_main_panel)
    bpy.utils.register_class(MaterialBakeOverride)
    bpy.utils.register_class(BakePreset)
    bpy.utils.register_class(ObjectBakeSettings)
    bpy.types.Object.unity_bake_settings = bpy.props.PointerProperty(type=ObjectBakeSettings)
    bpy.utils.register_class(UNITY_OT_add_bake_preset)
    bpy.utils.register_class(UNITY_OT_remove_bake_preset)
    bpy.utils.register_class(UNITY_OT_toggle_bake_channel)
    bpy.utils.register_class(UNITY_UL_bake_presets)
    bpy.utils.register_class(UNITY_PT_baking_panel)
    bpy.utils.register_class(UNITY_OT_create_baking_data)


def unregister():
    bpy.utils.unregister_class(UNITY_PT_main_panel)
    bpy.utils.unregister_class(UNITY_PT_baking_panel)
    bpy.utils.unregister_class(UNITY_UL_bake_presets)
    bpy.utils.unregister_class(UNITY_OT_toggle_bake_channel)
    bpy.utils.unregister_class(UNITY_OT_remove_bake_preset)
    bpy.utils.unregister_class(UNITY_OT_add_bake_preset)
    del bpy.types.Object.unity_bake_settings
    bpy.utils.unregister_class(ObjectBakeSettings)
    bpy.utils.unregister_class(BakePreset)
    bpy.utils.unregister_class(MaterialBakeOverride)
    bpy.utils.unregister_class(UNITY_OT_create_baking_data)

if __name__ == "__main__":
    register() 