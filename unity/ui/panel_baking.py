# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
import bpy
from .. import baker
from .. import bake_utils


def get_bakeable_sockets(self, context):
	"""EnumProperty callback to get bakeable sockets from the material's node group."""
	items = [] # Start with an empty list
	if not context.material:
		return items

	interface_node = baker.get_interface_node(context.material)
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

def get_active_socket(context):
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

	interface_node = baker.get_interface_node(context.material)
	if not interface_node:
		return None
	
	socket = interface_node.inputs.get(socket_name)
	return socket


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

class MaterialBakeBase(bpy.types.PropertyGroup):
	target_socket: bpy.props.EnumProperty(items=get_bakeable_sockets, update=on_update_target_socket_enum, name="Target Input")
	target_socket_name: bpy.props.StringProperty() # Hidden property to store the actual name persistently

	uv_map: bpy.props.EnumProperty(name="UV Map", items=get_uv_maps, update=on_update_uv_map_enum)
	uv_map_name: bpy.props.StringProperty()

	bake_mode: bpy.props.EnumProperty(items=[('NEW', "New", ""), ('EXISTING', "Existing", "")], default='NEW', name="Mode")
	existing_image: bpy.props.PointerProperty(name="Image", type=bpy.types.Image)
	resolution: bpy.props.IntProperty(name="Resolution", default=1024, min=64, max=8192)

	single_channel_target: bpy.props.EnumProperty(items=[('R', "R", ""), ('G', "G", ""), ('B', "B", "")])
	multi_channel_targets: bpy.props.EnumProperty(items=[('R', "R", ""), ('G', "G", ""), ('B', "B", "")], options={'ENUM_FLAG'}, name="Channels")
	color_space: bpy.props.EnumProperty(
		name="Color Space",
		description="Color space for newly created images",
		items=[
			('sRGB', 'sRGB', "Standard RGB color space for color textures"),
			('Non-Color', 'Non-Color', "For data textures like normals or roughness"),
			('Linear', 'Linear', "Raw linear color space"),
		],
		default='sRGB'
	)


class MaterialBakeOverride(MaterialBakeBase): 
	"""Stores all material-specific override settings for a bake operation."""
	name: bpy.props.StringProperty()
	material: bpy.props.PointerProperty(type=bpy.types.Material)

	use_override: bpy.props.BoolProperty(
		name="Override Global Settings",
		description="Use custom settings for this material instead of the global preset settings",
		default=False
	)

	margin: bpy.props.IntProperty(name="Margin", description="Extends the baked result as a post-process filter", default=16, min=0)
	use_margin_override: bpy.props.BoolProperty(
		name="Override Margin",
		description="Use a custom margin for this material instead of the preset's global margin",
		default=False
	)


class BakePreset(MaterialBakeBase):
    """A single, named bake configuration with global settings and per-material overrides."""
    name: bpy.props.StringProperty(name="Name", default="Bake Preset")
    is_active: bpy.props.BoolProperty(name="Active", default=True)

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

            # Check if any override is active and display an icon with a dynamic tooltip
            num_overrides = sum(1 for o in item.material_overrides if o.use_override or o.use_margin_override)
            if num_overrides > 0:
                plural = "s" if num_overrides > 1 else ""
                tooltip = f"{num_overrides} material override{plural} in use"
                
                op = row.operator("ui.show_tooltip", text="", icon='MOD_ARRAY', emboss=False)
                op.tooltip_text = tooltip

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)


class UNITY_OT_show_tooltip(bpy.types.Operator):
    """A dummy operator that does nothing but carry a tooltip, which is generated dynamically."""
    bl_idname = "ui.show_tooltip"
    bl_label = "Active Preset Index"
    bl_options = {'INTERNAL'}

    tooltip_text: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip_text

    def execute(self, context):
        return {'PASS_THROUGH'}


def _safe_reset_socket(preset_or_override):
    """Timer callback to safely reset the target_socket if it's invalid."""
    preset_or_override.target_socket = "NONE"
    return None


def draw_bake_settings_ui(layout, context, override_settings, preset_settings):
	"""Helper function to draw the common bake settings UI for a material.
	It handles showing global preset values or material-specific overrides.
	"""
	settings_source = override_settings if override_settings.use_override else preset_settings

	# --- Target Socket ---
	row = layout.row(align=True)
	split = row.split(factor=0.4)
	split.label(text="Target Input")
	split.prop(settings_source, "target_socket", text="")

	layout.separator()

	if settings_source.target_socket == "NONE":
		return

	# --- Dynamic Channel Selection ---
	socket = get_active_socket(context)
	row = layout.row(align=True)
	split = row.split(factor=0.4)
	if socket:
		if socket.type in {'VALUE', 'INT', 'BOOLEAN'}:
			split.label(text="Bake to Channel")
			sub_row = split.row(align=True)
			sub_row.prop(settings_source, "single_channel_target", expand=True)
		else:
			split.label(text="Bake Channels")
			sub_row = split.row(align=True)
			op_r = sub_row.operator(UNITY_OT_toggle_bake_channel.bl_idname, text="R", depress=('R' in settings_source.multi_channel_targets))
			op_r.channel = 'R'
			op_g = sub_row.operator(UNITY_OT_toggle_bake_channel.bl_idname, text="G", depress=('G' in settings_source.multi_channel_targets))
			op_g.channel = 'G'
			op_b = sub_row.operator(UNITY_OT_toggle_bake_channel.bl_idname, text="B", depress=('B' in settings_source.multi_channel_targets))
			op_b.channel = 'B'
			#op_a = sub_row.operator(UNITY_OT_toggle_bake_channel.bl_idname, text="A", depress=('A' in settings_source.multi_channel_targets))
			#op_a.channel = 'A'

	# --- Other Bake Settings ---
	row = layout.row(align=True)
	split = row.split(factor=0.4)
	split.label(text="UV Map")
	split.prop(settings_source, "uv_map", text="")

	row = layout.row(align=True)
	split = row.split(factor=0.4)
	split.label(text="Bake Mode")
	split.prop(settings_source, "bake_mode", text="")

	if settings_source.bake_mode == 'NEW':
		row = layout.row(align=True)
		split = row.split(factor=0.4)
		split.label(text="Resolution")
		split.prop(settings_source, "resolution", text="")
		
		row = layout.row(align=True)
		split = row.split(factor=0.4)
		split.label(text="Color Space")
		split.prop(settings_source, "color_space", text="")

	elif settings_source.bake_mode == 'EXISTING':
		row = layout.row(align=True)
		split = row.split(factor=0.4)
		split.label(text="Image")
		split.prop(settings_source, "existing_image", text="")

	# --- Margin UI ---
	row = layout.row(align=True)
	split = row.split(factor=0.4)
	split.label(text="Margin-Override")

	margin_row = split.row(align=True)
	margin_row.prop(override_settings, "use_margin_override", text="")

	if override_settings.use_margin_override:
		margin_row.prop(override_settings, "margin", text="")
	else:
		sub_row = margin_row.row()
		sub_row.enabled = False
		sub_row.prop(context.scene.render.bake, "margin", text="")

	# --- Plausibility Warnings (full width below the split) ---
	layout.separator()
	if socket:
		if settings_source.bake_mode == 'NEW':
			if bake_utils.is_value_socket(socket) and settings_source.color_space == 'sRGB':
				warning_box = layout.box()
				warning_box.label(text=f"Socket likely expects linear data, but Color Space is sRGB.", icon='ERROR')

		elif settings_source.bake_mode == 'EXISTING':
			if settings_source.existing_image:
				image_color_space = settings_source.existing_image.colorspace_settings.name
				if bake_utils.is_value_socket(socket) and image_color_space == 'sRGB':
					warning_box = layout.box()
					warning_box.label(text=f"Socket expects linear data, but Image Color Space is sRGB.", icon='ERROR')


class SocketBakeInfo(bpy.types.PropertyGroup):
	"""Helper to show socket/channel info in the confirmation dialog."""
	socket_name: bpy.props.StringProperty()
	channels: bpy.props.StringProperty()

class ImageBakeInfo(bpy.types.PropertyGroup):
	"""Helper to show image-related info in the confirmation dialog."""
	image_name: bpy.props.StringProperty()
	mode: bpy.props.StringProperty()
	socket_infos: bpy.props.CollectionProperty(type=SocketBakeInfo)

class BakePassInfo(bpy.types.PropertyGroup):
	"""Helper property group to display bake pass info in the confirmation dialog."""
	object_name: bpy.props.StringProperty()
	materials_list: bpy.props.StringProperty()
	margin_info: bpy.props.StringProperty()
	pass_index: bpy.props.IntProperty()
	image_infos: bpy.props.CollectionProperty(type=ImageBakeInfo)

class BakeConfirmationSettings(bpy.types.PropertyGroup):
	"""Stores the collected info for all bake passes to show in the dialog."""
	passes: bpy.props.CollectionProperty(type=BakePassInfo)
	active_index: bpy.props.IntProperty(name="Active Pass Index", default=0)

class UNITY_UL_bake_pass_info(bpy.types.UIList):
	"""UI List to display the bake pass summary."""
	def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
		# 'item' is a BakePassInfo instance
		if self.layout_type in {'DEFAULT', 'COMPACT'}:
			# Only show the main pass info in the list itself
			layout.label(text=f"Pass #{item.pass_index + 1}: {item.object_name}", icon='MOD_UVPROJECT')


class UNITY_OT_confirm_bake(bpy.types.Operator):
	"""Shows a confirmation dialog with a summary of the bake passes."""
	bl_idname = "unity_bake.confirm_bake"
	bl_label = "Bake Preview"
	bl_options = {'REGISTER', 'INTERNAL'}

	@classmethod
	def poll(cls, context):
		# This operator should only be called by other scripts, not directly from the UI
		return True

	def execute(self, context):
		# The actual baking logic is now here
		bake_data = UNITY_OT_bake_batch.bake_data_to_confirm
		if not bake_data:
			self.report({'ERROR'}, "No bake data found to execute.")
			return {'CANCELLED'}
		
		print("--- Starting Bake from Confirmation ---")
		baker_instance = baker.Baker(bake_data)
		result = baker_instance.bake()
		
		# Clean up the temporary data
		UNITY_OT_bake_batch.bake_data_to_confirm = None
		context.window_manager.bake_confirmation.passes.clear()
		
		return result

	def invoke(self, context, event):
		wm = context.window_manager
		return wm.invoke_props_dialog(self, width=360)

	def draw(self, context):
		layout = self.layout
		wm = context.window_manager
		
		layout.label(text=f"The addon will perform {len(wm.bake_confirmation.passes)} bake operations.")
		layout.label(text="Please review the passes before starting.")
		layout.separator()

		layout.template_list("UNITY_UL_bake_pass_info", "", wm.bake_confirmation, "passes", wm.bake_confirmation, "active_index", rows=5)

		# Show details for the selected pass below the list
		passes = wm.bake_confirmation.passes
		active_index = wm.bake_confirmation.active_index
        
		if active_index >= 0 and active_index < len(passes):
			active_pass = passes[active_index]
			box = layout.box()
			col = box.column(align=True)
			col.label(text=f"Materials: {active_pass.materials_list}")
			
			col.label(text="Images:")
			if active_pass.image_infos:
				for image_info in active_pass.image_infos:
					col.label(text=f"• {image_info.image_name} ({image_info.mode})")

					# Group by channel configuration for cleaner display
					grouped_by_channels = {}
					for socket_info in image_info.socket_infos:
						channels_str = socket_info.channels
						if channels_str not in grouped_by_channels:
							grouped_by_channels[channels_str] = []
						grouped_by_channels[channels_str].append(socket_info.socket_name)
					
					# Draw the grouped sockets and channels
					box_inner = col.box()
					for channels_str, socket_names in sorted(grouped_by_channels.items()):
						split = box_inner.split(factor=0.65)
						
						socket_col = split.column()
						for s_name in sorted(socket_names):
							socket_col.label(text=f"  {s_name}")

						channel_col = split.column()
						channel_col.alignment = 'RIGHT'
						channel_col.label(text=channels_str or "N/A")
			else:
				col.label(text="  (None)")

			col.separator()
			col.label(text=f"Margin: {active_pass.margin_info}")


class ImageBakeSettings(bpy.types.PropertyGroup):
	"""Custom bake settings that can be attached to an Image datablock."""
	use_override: bpy.props.BoolProperty(
		name="Material Override",
		description="Use custom bake settings for this image instead of the preset's global settings",
		default=False
	)
	clear_image: bpy.props.BoolProperty(
		name="Clear Image",
		description="Clear the image to transparent black before baking to it. Has no effect if 'Override' is disabled.",
		default=True
	)

class UNITY_PT_image_bake_settings_panel(bpy.types.Panel):
	"""Adds a panel to the Image Properties window for our custom bake settings."""
	bl_label = "Unity Bake Settings"
	bl_idname = "UNITY_PT_image_bake_settings"
	bl_space_type = 'PROPERTIES'
	bl_region_type = 'WINDOW'
	bl_context = "image"
	bl_category = 'Game Tools'

	@classmethod
	def poll(cls, context):
		return context.image is not None

	def draw(self, context):
		layout = self.layout
		image_settings = context.image.unity_bake_settings

		layout.prop(image_settings, "use_override")
		
		box = layout.box()
		col = box.column()
		col.enabled = image_settings.use_override
		col.prop(image_settings, "clear_image")


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
		col.separator()
		col.operator("unity_bake.move_preset_up", icon='TRIA_UP', text="")
		col.operator("unity_bake.move_preset_down", icon='TRIA_DOWN', text="")

		if settings.active_index >= 0 and len(settings.presets) > 0:
			active_preset = settings.presets[settings.active_index]
			box = layout.box()

			active_material = context.material
			if not active_material:
				box.label(text="Select a material to configure settings.", icon='INFO')
				return

			interface_node = baker.get_interface_node(active_material)
			if not interface_node:
				box.label(text="Unsupported material node setup", icon='ERROR')
				return

			# Check for unsupported shader types and outputs
			unsupported_node_types = {'ShaderNodeMixShader', 'ShaderNodeAddShader', 'ShaderNodeHoldout'}
			is_unsupported_type = interface_node.bl_idname in unsupported_node_types

			# The get_interface_node check should ensure output_node exists, but we check again for safety
			output_node = next((n for n in active_material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
			if output_node and output_node.inputs['Surface'].links:
				from_socket = output_node.inputs['Surface'].links[0].from_socket
				is_shader_output = from_socket.type == 'SHADER'
				
				if is_unsupported_type or not is_shader_output:
					warning_box = box.box()
					if is_unsupported_type:
						shader_name = interface_node.bl_idname.replace('ShaderNode', '')
						warning_box.label(text=f"Unsupported Shader: '{shader_name}'", icon='ERROR')
					elif not is_shader_output:
						warning_box.label(text="Material output is not a BSDF shader.", icon='ERROR')
					return
			else:
				# This case should technically be caught by the get_interface_node check above,
				# but we'll handle it here as a fallback.
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
			
			sub_box = box.box()

			# Determine the correct source for validation
			validation_source = active_override if active_override.use_override else active_preset
			valid_socket_items = get_bakeable_sockets(validation_source, context)
			valid_socket_identifiers = {item[0] for item in valid_socket_items}

			# If the selected socket is invalid for the current source, show an error.
			if validation_source.target_socket_name not in valid_socket_identifiers and validation_source.target_socket_name not in ('', 'NONE'):
				sub_box.label(text=f"Input '{validation_source.target_socket_name}' not found on this material.", icon='ERROR')
				if not active_override.use_override:
					sub_box.label(text="Enable override to select a different input.")
			else:
				# Ensure the enum property is reset if its value is no longer valid
				if validation_source.target_socket not in valid_socket_identifiers:
						bpy.app.timers.register(lambda p=validation_source: _safe_reset_socket(p))
				
				# Draw the consolidated UI
				draw_bake_settings_ui(sub_box, context, active_override, active_preset)


class UNITY_OT_move_bake_preset_up(bpy.types.Operator):
	"""Move the selected bake preset up in the list"""
	bl_idname = "unity_bake.move_preset_up"
	bl_label = "Move Bake Preset Up"
	bl_options = {'REGISTER', 'UNDO'}

	@classmethod
	def poll(cls, context):
		if not context.object: return False
		settings = context.object.unity_bake_settings
		if not settings: return False
		return settings.active_index > 0

	def execute(self, context):
		settings = context.object.unity_bake_settings
		index = settings.active_index
		settings.presets.move(index, index - 1)
		settings.active_index -= 1
		return {'FINISHED'}

class UNITY_OT_move_bake_preset_down(bpy.types.Operator):
	"""Move the selected bake preset down in the list"""
	bl_idname = "unity_bake.move_preset_down"
	bl_label = "Move Bake Preset Down"
	bl_options = {'REGISTER', 'UNDO'}

	@classmethod
	def poll(cls, context):
		if not context.object: return False
		settings = context.object.unity_bake_settings
		if not settings: return False
		return 0 <= settings.active_index < len(settings.presets) - 1

	def execute(self, context):
		settings = context.object.unity_bake_settings
		index = settings.active_index
		settings.presets.move(index, index + 1)
		settings.active_index += 1
		return {'FINISHED'}


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


class UNITY_OT_bake_batch(bpy.types.Operator):
	"""Create baking data for the selected object"""
	bl_idname = "unity.bake_batch"
	bl_label = "Bake Materials"
	bl_options = {'REGISTER', 'UNDO'}

	# Class variable to hold the bake data between the dry run and the confirmation
	bake_data_to_confirm = None

	def convert_setting(self, mat, setting, socket, channels, margin_val):
		image = setting.existing_image if setting.bake_mode == 'EXISTING' else None
		image_meta = bake_utils.ImageMeta(setting.bake_mode, setting.resolution, margin_val, setting.color_space)
		return bake_utils.BakeMaterialSetting(
			mat, 
			socket, 
			setting.uv_map_name,
			channels,
			image,
			image_meta)

	def bake_batch(self, bake_data, obj, context):
		if len(obj.unity_bake_settings.presets) == 0:
			return

		all_materials = [ms.material for ms in obj.material_slots if ms.material]

		pass_bake_targets = {}
		pass_index = len(bake_data.passes)
		for preset in obj.unity_bake_settings.presets:
			if not preset.is_active:
				continue
			
			pass_settings = []
			is_pass_effective = False 
			for material in all_materials:
				interface = baker.get_interface_node(material)
				
				# --- Determine sources ---
				# 1. Source for main settings (depends on the main override toggle)
				effective_setting = preset
				if interface:
					for o in preset.material_overrides:
						if o.material == material and o.use_override:
							effective_setting = o
							break
				
				# 2. Source for margin override (is always the material's specific override entry)
				margin_override = None
				if interface:
					for o in preset.material_overrides:
						if o.material == material:
							margin_override = o
							break

				socket_name = effective_setting.target_socket_name
				socket = interface.inputs.get(socket_name) if interface and socket_name != "NONE" else None

				if socket:
					socket_type = socket.type
					if socket_type in {'VALUE', 'INT', 'BOOLEAN'}:
						channels = {effective_setting.single_channel_target}
					else:
						channels = effective_setting.multi_channel_targets
					
					if effective_setting.bake_mode == 'EXISTING':
						image = effective_setting.existing_image
						if not image:
							self.report({'ERROR'}, f"Bake mode is 'Existing' but no image is selected in preset '{preset.name}' for material '{material.name}'.")
							return {'CANCELLED'}

						uv_map_name = effective_setting.uv_map_name
						target_key = (image, uv_map_name, material)

						if target_key not in pass_bake_targets:
							pass_bake_targets[target_key] = {}
							for ch in channels:
								pass_bake_targets[target_key][ch] = socket.name
						else:
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

							candidate_pass = self.find_existing_pass(bake_data.passes, image, uv_map_name, material)
							if candidate_pass != None:
								bake_material_setting = self.convert_setting(material, effective_setting, socket, channels, final_margin)
								candidate_pass.settings.append(bake_material_setting)
								continue

					# Determine final margin based on the independent margin override
					final_margin = context.scene.render.bake.margin # Default to global blender bake margin
					if margin_override and margin_override.use_margin_override:
						final_margin = margin_override.margin

					bake_material_setting = self.convert_setting(material, effective_setting, socket, channels, final_margin)
					pass_settings.append(bake_material_setting)
					is_pass_effective = True
				else:
					dummy_setting = bake_utils.BakeMaterialSetting(material, None, None, None, None, bake_utils.ImageMeta('DUMMY', 1, 0, 'sRGB'))
					pass_settings.append(dummy_setting)

			if is_pass_effective:
				bake_data.passes.append(bake_utils.BakePass(obj, pass_settings, pass_index))
				pass_index += 1
		
		return {'CONTINUE'} # Using a custom return value to signal success

	def find_existing_pass(self, passes, image, uv_map_name, material):
		for bake_pass in passes:
			for setting in bake_pass.settings:
				if setting.image == image and setting.uv_map_name == uv_map_name and setting.material == material:
					return bake_pass
		return None

	@classmethod
	def poll(cls, context):
		return context.selected_objects

	def execute(self, context):
		bake_data = bake_utils.BakeData()

		selected_objects_with_presets = [obj for obj in context.selected_objects if len(obj.unity_bake_settings.presets) > 0]

		for obj in selected_objects_with_presets:
			result = self.bake_batch(bake_data, obj, context)
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

		self.report({'INFO'}, f"Bake job created with {len(bake_data.passes)} passes.")

		# --- Dry Run & Confirmation Step ---
		# Clear previous confirmation data
		wm = context.window_manager
		wm.bake_confirmation.passes.clear()
		
		# Calculate max margin per pass and prepare confirmation data
		for bake_pass in bake_data.passes:
			max_margin = 0
			materials_in_pass = set()
			image_details = {} # Dict to aggregate info per image: name -> {mode, sockets: {name->channels}}

			# Determine highest margin and collect names for UI
			for setting in bake_pass.settings:
				if not setting.is_dummy():
					materials_in_pass.add(setting.material.name)
					if setting.image_meta.margin > max_margin:
						max_margin = setting.image_meta.margin
					
					# Aggregate image details, now including socket info
					img_name = setting.get_target_image_name(bake_pass.object)
					socket_name = setting.input_socket.name
					if img_name not in image_details:
						image_details[img_name] = {
							"mode": setting.image_meta.bake_mode,
							"sockets": {}
						}
					
					if socket_name not in image_details[img_name]["sockets"]:
						image_details[img_name]["sockets"][socket_name] = set()

					if setting.channels:
						image_details[img_name]["sockets"][socket_name].update(setting.channels)

			bake_pass.max_margin = max_margin

			# --- Add summary item for the dialog using the new PropertyGroups ---
			info_pass = wm.bake_confirmation.passes.add()
			info_pass.pass_index = bake_pass.index
			info_pass.object_name = bake_pass.object.name
			info_pass.materials_list = ", ".join(sorted(list(materials_in_pass))) or "N/A"
			info_pass.margin_info = f"{max_margin}px"
			
			rgb_order = ['R', 'G', 'B', 'A']
			for img_name, details in sorted(image_details.items()):
				info_image = info_pass.image_infos.add()
				info_image.image_name = img_name
				info_image.mode = "New" if details["mode"] == 'NEW' else "Existing"

				for socket_name, channels in sorted(details["sockets"].items()):
					info_socket = info_image.socket_infos.add()
					info_socket.socket_name = socket_name
					sorted_channels = [ch for ch in rgb_order if ch in channels]
					info_socket.channels = ",".join(sorted_channels)

		# Store bake data for the confirmation operator and invoke the dialog
		UNITY_OT_bake_batch.bake_data_to_confirm = bake_data
		bpy.ops.unity_bake.confirm_bake('INVOKE_DEFAULT')
		
		return {'FINISHED'}

	def print_raw_bake_settings(self, context):
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


classes = (
	MaterialBakeOverride,
	BakePreset,
	ObjectBakeSettings,
	UNITY_OT_move_bake_preset_up,
	UNITY_OT_move_bake_preset_down,
	UNITY_OT_add_bake_preset,
	UNITY_OT_remove_bake_preset,
	UNITY_OT_toggle_bake_channel,
	UNITY_UL_bake_presets,
	UNITY_OT_show_tooltip,
	UNITY_PT_baking_panel,
	ImageBakeSettings,
	UNITY_PT_image_bake_settings_panel,
	SocketBakeInfo,
	ImageBakeInfo,
	BakePassInfo,
	BakeConfirmationSettings,
	UNITY_UL_bake_pass_info,
	UNITY_OT_confirm_bake,
	UNITY_OT_bake_batch,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Object.unity_bake_settings = bpy.props.PointerProperty(type=ObjectBakeSettings)
    bpy.types.Image.unity_bake_settings = bpy.props.PointerProperty(type=ImageBakeSettings)
    bpy.types.WindowManager.bake_confirmation = bpy.props.PointerProperty(type=BakeConfirmationSettings)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        
    del bpy.types.Object.unity_bake_settings
    del bpy.types.Image.unity_bake_settings
    del bpy.types.WindowManager.bake_confirmation
