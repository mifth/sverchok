
import numpy as np

import bpy
from bpy.props import FloatProperty, EnumProperty, BoolProperty, IntProperty, StringProperty

from sverchok.node_tree import SverchCustomTreeNode
from sverchok.data_structure import updateNode, zip_long_repeat, match_long_repeat
from sverchok.utils.logging import info, exception

class SvVectorFieldEvaluateNode(SverchCustomTreeNode, bpy.types.Node):
    """
    Triggers: Vector Field Evaluate
    Tooltip: Evaluate Vector Field at specific point(s)
    """
    bl_idname = 'SvExVectorFieldEvaluateNode'
    bl_label = 'Evaluate Vector Field'
    bl_icon = 'OUTLINER_OB_EMPTY'
    sv_icon = 'SV_EVAL_VECTOR_FIELD'

    output_numpy: BoolProperty(
        name='Output NumPy',
        description='Output NumPy arrays (improves performance)',
        default=False,
        update=updateNode)

    def sv_init(self, context):
        self.inputs.new('SvVectorFieldSocket', "Field")
        d = self.inputs.new('SvVerticesSocket', "Vertices")
        d.use_prop = True
        d.default_property = (0.0, 0.0, 0.0)
        self.outputs.new('SvVerticesSocket', 'Vectors')

    def draw_buttons_ext(self, context, layout):
        layout.prop(self, 'output_numpy')
    def rclick_menu(self, context, layout):
        layout.prop(self, "output_numpy")

    def process(self):
        if not any(socket.is_linked for socket in self.outputs):
            return

        vertices_s = self.inputs['Vertices'].sv_get()
        fields_s = self.inputs['Field'].sv_get()

        values_out = []
        for field, vertices in zip_long_repeat(fields_s, vertices_s):
            if len(vertices) == 0:
                new_values = []
            elif len(vertices) == 1:
                vertex = vertices[0]
                value = field.evaluate(*vertex)
                new_values = [tuple(value)]
            else:
                XYZ = vertices if isinstance(vertices, np.ndarray) else np.array(vertices)
                xs = XYZ[:,0]
                ys = XYZ[:,1]
                zs = XYZ[:,2]
                new_xs, new_ys, new_zs = field.evaluate_grid(xs, ys, zs)
                new_vectors = np.dstack((new_xs[:], new_ys[:], new_zs[:]))
                new_values = new_vectors if self.output_numpy else new_vectors[0].tolist()

            values_out.append(new_values)

        self.outputs['Vectors'].sv_set(values_out)

def register():
    bpy.utils.register_class(SvVectorFieldEvaluateNode)

def unregister():
    bpy.utils.unregister_class(SvVectorFieldEvaluateNode)
