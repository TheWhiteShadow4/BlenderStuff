# pyright: reportInvalidTypeForm=false
import bpy

class UnityAddonProperties(bpy.types.PropertyGroup):
    unity_project_path: bpy.props.StringProperty(
        name="Unity Project Path",
        description="Path to the root of the Unity project",
        subtype='DIR_PATH',
        default=""
    )

def register():
    bpy.utils.register_class(UnityAddonProperties)
    bpy.types.Scene.unity_tool_properties = bpy.props.PointerProperty(type=UnityAddonProperties)

def unregister():
    del bpy.types.Scene.unity_tool_properties
    bpy.utils.unregister_class(UnityAddonProperties) 