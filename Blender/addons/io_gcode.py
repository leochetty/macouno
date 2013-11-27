# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8-80 compliant>

bl_info = {
	"name": "GCODE format",
	"author": "macouno",
	"version": (1, 0),
	"blender": (2, 69, 0),
	"location": "File > Import-Export > Gcode",
	"description": "Import-Export Gcode files",
	"warning": "",
	"wiki_url": "",
	"tracker_url": "",
	"support": 'TESTING',
	"category": "Import-Export"}


import os, math
import bpy, bmesh
from macouno import bmesh_extras
from bpy.props import (StringProperty,
					   BoolProperty,
					   CollectionProperty,
					   EnumProperty,
					   FloatProperty,
					   )
from bpy_extras.io_utils import (ImportHelper,
								 ExportHelper,
								 axis_conversion,
								 )
from bpy.types import Operator, OperatorFileListElement

# Get the float from a line segment of gcode
def gVal(input):
	input = input.replace(';','')
	return float(input[1:])
	

class ImportGCODE(Operator, ImportHelper):
	"""Load Gcode into mesh data"""
	bl_idname = "import_mesh.gcode"
	bl_label = "Import Gcode"
	bl_options = {'UNDO'}

	filename_ext = ".gcode"

	filter_glob = StringProperty(
			default="*.gcode",
			options={'HIDDEN'},
			)
	files = CollectionProperty(
			name="File Path",
			type=OperatorFileListElement,
			)
	directory = StringProperty(
			subtype='DIR_PATH',
			)

	def execute(self, context):
	
		paths = [os.path.join(self.directory, name.name)
				 for name in self.files]

		if not paths:
			paths.append(self.filepath)

		if bpy.ops.object.mode_set.poll():
			bpy.ops.object.mode_set(mode='OBJECT')

		if bpy.ops.object.select_all.poll():
			bpy.ops.object.select_all(action='DESELECT')

		for path in paths:
			objName = bpy.path.display_name(os.path.basename(path))
			print("FOUND FILE",objName)
			
			with open(path,'r') as f:
			
				slice = False
				bm = False
				me = False
				ob = False
				preI =False
				x = 0.0
				y = 0.0
				z = 0.0
				e = 0.0
				aPrev = False
				t = False
				
				
				for li, line in enumerate(f.readlines()):
				
					# Keep track of what slice we're on
					if line.startswith('; Slice'):
						
						slice = line.replace('; Slice ', '')
						slice = int(slice)
					
					# Only slices are added! The stuff before we don't need
					if not slice is False:
					
						if line.startswith('G1 '):
						
							# Create a fresh new bmesh and an object for it to go into
							# We need the object here so we can make vertex groups later on (in bmesh_extras)
							if bm is False:
								bm = bmesh.new()
								me = bpy.data.meshes.new(objName)
								ob = bpy.data.objects.new(objName, me)
								scn =bpy.context.scene
								scn.objects.link(ob)
								ob.select = True
								scn.objects.active = ob
								
								try:
									ex = bm.verts.layers.float['extrusions']
								except KeyError:
									ex = bm.verts.layers.float.new('extrusions')
								
								# Don't forget that the string type needs encoded bytes!!! Shees...
								try:
									et = bm.edges.layers.string['types']
								except KeyError:
									et = bm.edges.layers.string.new('types')

							# Lets get coordinates
							words = line.split(' ')
							t = None
							for word in words:
								if len(word) > 1:
									if word.startswith('X'):
										x = gVal(word)		
									elif word.startswith('Y'):
										y = gVal(word)
									elif word.startswith('Z'):
										z = gVal(word)
										
									elif word.endswith('\n'):
										t = word.replace('\n','')
										if t == 'move':
											t = 'Travel move'
										elif t == 'position':
											t = 'Move to start position'
										elif t == 'print':
											t = 'End of print'
										
									elif word.startswith('A'):
										aCur = gVal(word.replace(';',''))
										if aPrev:
											e = aCur - aPrev
										else:
											e = 0.0
										aPrev = aCur
											
										if li < 100:
											print(e,aCur,aPrev)
											

									
							#	Only add a point for actual defined positions
							if t:
								
								# Add a vert at the correct coords
								curV = bm.verts.new((x,y,z))
								curV[ex] = e
								curI = len(bm.verts)-1
								
								# Add the vert to the correct vertex group
								bm, group_index = bmesh_extras.add_to_group(bme=bm, verts = [curV], newGroup=False, groupName=t)
								
								# Add an edge if we can!
								if not preI is False:
									curE = bm.edges.new([bm.verts[curI], bm.verts[preI]])
									curE[et] = t.encode('utf-8')
									
								# Set the previous vert index to the current index
								preI = curI
							
					# Do not go beyond the end of the print
					if t == 'End of print':
						break
						
							
			if not bm is False:
				bm.to_mesh(me)
				bm.free()
				

		return {'FINISHED'}


class ExportGCODE(Operator, ExportHelper):
	"""Save STL triangle mesh data from the active object"""
	bl_idname = "export_mesh.gcode"
	bl_label = "Export Gcode"

	filename_ext = ".gcode"
	filter_glob = StringProperty(default="*.gcode", options={'HIDDEN'})
	
	newlines = []
	dEdges = []
	bm = None
	dvert_lay = None
	Arot = 0.0
	slice = {'nr': 0, 'position': 0.0}
	percentage = 0.0
	Anchored = False
	
	'''
	Movetypes{
		'Groupname': {
			'F': Speed,
			'A': Extrusion rotation,
			'Type': Extrusion rotation interpretation (set is set value, len = multiplied by mm of move,
			'index': the index of the vertex group with the same name as the group,
			}
		}
	'''
	moveTypes = {
		'Move to start position':	{'F':9000.0,	'A':0.0, 		'Type':'set',	'index':None},
		'Anchor':								{'F':1800.0,	'A':0.175, 	'Type':'len',	'index':None},
		'Restart':								{'F':1500.0,	'A':1.3, 		'Type':'set',	'index':None},
		'Travel move':					{'F':9000.0,	'A':0.0, 		'Type':'set', 	'index':None},
		'Connection':						{'F':1620.0,	'A':0.035, 	'Type':'len', 	'index':None},
		'Retract':								{'F':1500.0,	'A':-1.3, 	'Type':'set', 	'index':None},
		'Outline':								{'F':720.0,	'A':0.035, 	'Type':'len', 	'index':None},
		'Inset':									{'F':1800.0,	'A':0.035, 	'Type':'len',	'index':None},
		'Infill': 									{'F':1620.0,	'A':0.035, 	'Type':'len', 	'index':None},
		'End of print': 						{'F':1500.0,	'A':-1.3, 	'Type':'set',	'index':None}
		}

	'''
	# The extrusion speed for any normal move!!!
	# This is normally 0.035 * the length of the move
	# Anchor 0.175
	ExtrusionFactor = FloatProperty(
			name="Extrusion factor",
			min=0.001, max=10.0,
			default=0.035,
			)
	'''
	
	def makeStart(self):
		self.newlines.append("""M136 (enable build progress)
M73 P0
G162 X Y F2000(home XY axes maximum)
G161 Z F900(home Z axis minimum)
G92 X0 Y0 Z-5 A0 B0 (set Z to -5)
G1 Z0.0 F900(move Z to '0')
G161 Z F100(home Z axis minimum)
M132 X Y Z A B (Recall stored home offsets for XYZAB axis)
G92 X152 Y75 Z0 A0 B0
G1 X-112 Y-73 Z150 F3300.0 (move to waiting position)
G130 X20 Y20 A20 B20 (Lower stepper Vrefs while heating)
M135 T0
M104 S230 T0
M133 T0
G130 X127 Y127 A127 B127 (Set Stepper motor Vref to defaults)
; Slice 0
; Position  0
; Thickness 0.2
; Width 0.4
M73 P0; """)
		return
		
		
		
	def makeEnd(self):	
		self.newlines.append("""M18 A B(Turn off A and B Steppers)
G1 Z155 F900
G162 X Y F2000
M18 X Y Z(Turn off steppers after a build)
M104 S0 T0
M70 P5 (We <3 Making Things!)
M72 P1  ( Play Ta-Da song )
M73 P100 (end  build progress )
M137 (build end notification)""")
		return

		
		
	# Find the vertex group for this vertex
	def findGroup(self,v):
		for key in self.moveTypes:
			move = self.moveTypes[key]
			groupIndex = move['index']
			if not groupIndex is None:
				try:
					x = v[self.dvert_lay][groupIndex]
					return move, key
				except:
					pass
		return None
		
		
		
	# Make a line of gcode for this vertex
	def makeLine(self, v, e):
		
		line = 'G1'
		
		# Add a nice percentage counter for display on the makerbot
		prcnt =  math.floor((len(self.dEdges) / len(self.bm.edges) )* 100)
		if prcnt > self.percentage:
			self.percentage = prcnt
			line = 'M73 P'+str(prcnt)+';\n'+line
		
		
		x = round(v.co[0],3)
		y = round(v.co[1],3)
		z = round(v.co[2],3)
		line = line+' X'+str(x)
		line = line+' Y'+str(y)
		line = line+' Z'+str(z)
		
		
		# Check for the next slice
		if z > self.slice['position']:
			self.slice['nr'] += 1
			self.slice['position'] = z
			line = '; Slice '+str(self.slice['nr'])+'\n; Position '+str(z)+'\n; Thickness 0.2\n; Width 0.4\n'+line
		
		
		# Get the specific values for this type of movement!
		move, moveName = self.findGroup(v)
		if not move is None:
			line = line+' F'+str(round(move['F'],3))
			
			# THe first anchor only gets a value of 5.0!! Yeah
			if moveName == 'Anchor' and not self.Anchored:
				self.Arot += 5.0
				self.Anchored = True
			elif move['Type'] == 'set':
				self.Arot += move['A']
			else:
				self.Arot += move['A'] * e.calc_length()
			line = line+' A'+str(round(self.Arot,3))
			line = line +'; '+moveName
		line = line + '\n'
		return line
	
	
	
	# Step through the code to be printed!
	def step(self, vert):
	
		for e in vert.link_edges:
			if not e.index in self.dEdges:
				for v in e.verts:
					if not v is vert:
						self.dEdges.append(e.index)
						self.newlines.append(self.makeLine(v,e))
						self.step(v)
						
		return
	
	
	def execute(self, context):
		
		self.makeStart()
		
		# Let's go make some lines with gcode!
		self.bm = bmesh_extras.get_bmesh()
		
		self.dvert_lay = self.bm.verts.layers.deform.active
		if self.dvert_lay is None:
			print('Cancelling export... no use to try without vertex groups')
			return
			
		# Here we get all the group indexes and add them to the dict!
		for key in self.moveTypes:
			try:
				group = bpy.context.active_object.vertex_groups[key]
				self.moveTypes[key]['index'] = group.index
			except:
				pass
		# Lets find the vert at the start of the print!
		#group = bpy.context.active_object.vertex_groups['Move to start position']
		start_index = self.moveTypes['Move to start position']['index']
			
		startV = None
		for v in self.bm.verts:
			try:
				x = v[self.dvert_lay][start_index]
				startV = v
			except:
				pass
			
		if startV:
			self.newlines.append(self.makeLine(startV,None))
			self.step(startV)
		else:
			print('Unable to retrieve start position')
		
		self.bm.free()
		self.makeEnd()
		
		fOut = self.filepath
		with open(fOut, 'w') as f:
			for line in self.newlines:
				f.write(line)
		

		return {'FINISHED'}


def menu_import(self, context):
	self.layout.operator(ImportGCODE.bl_idname, text="Gcode (.gcode)")


def menu_export(self, context):
	default_path = os.path.splitext(bpy.data.filepath)[0] + ".gcode"
	self.layout.operator(ExportGCODE.bl_idname, text="Gcode (.gcode)")


def register():
	bpy.utils.register_module(__name__)

	bpy.types.INFO_MT_file_import.append(menu_import)
	bpy.types.INFO_MT_file_export.append(menu_export)


def unregister():
	bpy.utils.unregister_module(__name__)

	bpy.types.INFO_MT_file_import.remove(menu_import)
	bpy.types.INFO_MT_file_export.remove(menu_export)


if __name__ == "__main__":
	register()