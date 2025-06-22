# Copyright (c) 2025 TheWhiteShadow

from . import ui, operators, properties

bl_info = {
	"name": "Unity Tools",
	"author": "TheWhiteShadow",
	"version": (1, 0),
	"blender": (4, 4, 0),
	"description": "Unity Helper Tools",
	"warning": "",
	"wiki_url": "",
	"category": "3D View"
}

def register():
	ui.register()
	operators.register()
	properties.register()

def unregister():
	ui.unregister()
	operators.unregister()
	properties.unregister()

if __name__ == "__main__":
	register()