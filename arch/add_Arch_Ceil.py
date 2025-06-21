bl_info = {
	"name": "Arch Ceil",
	"author": "TheWhiteShadow",
	"version": (1, 0),
	"blender": (2, 80, 0),
	"location": "View3D > Add > Mesh > New Object",
	"description": "Adds a new Arch Ceil",
	"warning": "",
	"wiki_url": "",
	"category": "Add Mesh",
	}

# pyright: reportInvalidTypeForm=false
import bpy
import math
from bpy.types import Operator
from bpy.props import IntProperty, FloatProperty, BoolProperty
from bpy_extras.object_utils import AddObjectHelper, object_data_add
from mathutils import Vector, Euler


def add_arch_ceil(self, context):
	if (self.extrude <= -self.size):
		self.extrude = -self.size + 0.001
	 
	size = self.size + self.extrude
	arch_radius = ((self.arch_radius*self.size) + self.extrude) / (size)

	# Normalisierte Bogengroeße
	radius = size
	size = size / math.tan(math.pi / self.edges)
	
	# Detailgrad
	steps = self.steps
	half_stepsize = math.pi / self.edges
	
	# Winkel an dem sich die Boegen schneiden
	ceil_angle = math.acos(((arch_radius) - 1) / (arch_radius) )
	# Bogenstreckung an den Ecken
	diagonal = size / math.cos(math.pi / self.edges)
	
	verts = []
	edges = []
	faces = []
	
	# berechne die hoehe und erstelle den oberen Mittelpunkt
	z = math.sin(ceil_angle) * arch_radius * radius
	verts.append((0, 0, z))
	
	if (self.edges > 2):
		# erstelle die oberen Bogenpunkte
		ang = 0
		while (ang < 2*math.pi):
			x = math.cos(ang) * size
			y = math.sin(ang) * size
			verts.append((x, y, z))
			
			ang += 2*half_stepsize
		
	# erstelle die weiteren Halbboegen und verbinde sie
	ang = half_stepsize
	for edge_index in range(1, self.edges+1):
		# Winkel für den rechten und linken Halbbogen
		eul1 = Euler((0.0, 0.0, ang-half_stepsize), 'XYZ')
		eul2 = Euler((0.0, 0.0, ang+half_stepsize), 'XYZ')
		
		# erstelle den unteren Eckpunkt
		vec = Vector((size, radius, 0))
		vec.rotate(eul1)
		verts.append(vec)
		
		step_size = ceil_angle / steps
		z_angle = step_size
		# iteriere durch den Bogen
		for loop in range(0, steps-1):
			dist = math.cos(z_angle) * (arch_radius) - (arch_radius-1)
			z = math.sin(z_angle) * arch_radius * radius
			z_angle += step_size
			
			vec = Vector((size, dist * radius, z))
			vec.rotate(eul1)
			verts.append(vec)
			
			if (self.edges > 2):
				vec = Vector((size, -dist * radius, z))
				vec.rotate(eul2)
				verts.append(vec)

				x = math.cos(ang) * dist * diagonal
				y = math.sin(ang) * dist * diagonal
				verts.append( Vector((x, y, z)) )
			
				last = len(verts)-1
				# Sonderfall beim Boden (Dreieck)
				if (loop == 0):
					faces.append([last-2, last-3, last])
					faces.append([last-3, last-1, last])
				else:
					faces.append([last-2, last-5, last-3, last])
					faces.append([last-3, last-4, last-1, last])
			else:
				last = len(verts)-1
				edges.append([last-1, last])
		
		if (self.edges > 2):
			# den Ring schliessen
			faces.append([edge_index, last-2, last, 0])
			if (edge_index == self.edges):
				faces.append([last, last-1, 1, 0])
			else:
				faces.append([last, last-1, edge_index+1, 0])
		else:
			edges.append([last, 0])
		ang += 2*half_stepsize

	mesh = bpy.data.meshes.new(name="Arch Ceil")
	mesh.from_pydata(verts, edges, faces)
	object_data_add(context, mesh, operator=self)


class OBJECT_OT_add_arch_ceil(Operator, AddObjectHelper):
	"""Create a new Arch Ceil"""
	bl_idname = "mesh.add_arch_ceil"
	bl_label = "Add Arch Ceil"
	bl_options = {'REGISTER', 'UNDO'}

	size: FloatProperty(
			name="Size",
			default=1.0,
			description="Size of the arch ceil.",
			precision=3
			)
			
	arch_radius: FloatProperty(
			name="Arch Radius",
			min=1,
			max=100.0,
			default=2.0,
			description="Size of the arch radius.",
			precision=3
			)
			
	steps: IntProperty(
			name="Steps",
			min=2,
			max=128,
			default=12,
			description="Steps of the arch curve.",
			)
			
	extrude: FloatProperty(
			name="Extrude",
			min=-100.0,
			max=100.0,
			default=0.0,
			description="Extrude the arch. You can also use the formula:\narch_radius = 1 + (arch_radius_0 - 1) / (size - size_0) with (size - size_0) as extrude value ;-)",
			precision=3
			)
			
	edges: IntProperty(
			name="Edges",
			min=2,
			max=32,
			default=4,
			description="Edges of the arch.",
			)

	def execute(self, context):

		add_arch_ceil(self, context)

		return {'FINISHED'}


# Registration
def add_object_button(self, context):
	self.layout.operator(OBJECT_OT_add_arch_ceil.bl_idname, text="Arch Ceil", icon='PLUGIN')

def register():
	bpy.utils.register_class(OBJECT_OT_add_arch_ceil)
	#bpy.utils.register_manual_map(add_object_manual_map)
	bpy.types.VIEW3D_MT_mesh_add.append(add_object_button)


def unregister():
	bpy.utils.unregister_class(OBJECT_OT_add_arch_ceil)
	#bpy.utils.unregister_manual_map(add_object_manual_map)
	bpy.types.VIEW3D_MT_mesh_add.remove(add_object_button)


if __name__ == "__main__":
	register()
