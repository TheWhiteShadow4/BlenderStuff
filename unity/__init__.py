# Copyright (c) 2025 TheWhiteShadow

from . import ui, operators

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

def register():
	ui.register()
	operators.register()
	#properties.register()

def unregister():
	ui.unregister()
	operators.unregister()
	#properties.unregister()

if __name__ == "__main__":
	register()