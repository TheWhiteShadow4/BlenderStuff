# Copyright (c) 2025 TheWhiteShadow

import bpy
from . import ui, operators, properties

bl_info = {
	"name": "Unity Tools",
	"author": "TheWhiteShadow",
	"version": (1, 0),
	"blender": (4, 4, 0),
	"description": "Unity Helper Tools",
	"warning": "",
	"wiki_url": "",
	"category": "System"
}

if "bpy" in locals():
    import importlib
    importlib.reload(properties)
    importlib.reload(operators)
    importlib.reload(ui)
    

def validate_and_refresh_ui():
    """
    Performs the validation and UI update.
    Called from a handler and on registration via a timer.
    Returns None so the timer only runs once.
    """
    if bpy.context and bpy.context.scene:
        props = bpy.context.scene.unity_tool_properties
        if props:
            properties.update_unity_path(props, bpy.context)
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'UI':
                            region.tag_redraw()
    return None

def on_load_handler(dummy):
    """Wrapper to call the validation from the load_post handler."""
    # The timer is more reliable for startup
    if not bpy.app.timers.is_registered(validate_and_refresh_ui):
        bpy.app.timers.register(validate_and_refresh_ui)

def register():
	properties.register()
	operators.register()
	ui.register()
	
	bpy.app.handlers.load_post.append(on_load_handler)
	
	# Schedule the validation to run once, very soon after registration,
    # when the context is available.
	if not bpy.app.timers.is_registered(validate_and_refresh_ui):
		bpy.app.timers.register(validate_and_refresh_ui)


def unregister():
	ui.unregister()
	operators.unregister()
	properties.unregister()
	
	if on_load_handler in bpy.app.handlers.load_post:
		bpy.app.handlers.load_post.remove(on_load_handler)
	
	if bpy.app.timers.is_registered(validate_and_refresh_ui):
		bpy.app.timers.unregister(validate_and_refresh_ui)


if __name__ == "__main__":
	register()