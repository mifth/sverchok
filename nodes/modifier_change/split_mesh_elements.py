# This file is part of project Sverchok. It's copyrighted by the contributors
# recorded in the version control history of the file, available from
# its original location https://github.com/nortikin/sverchok/commit/master
#
# SPDX-License-Identifier: GPL3
# License-Filename: LICENSE

from typing import List, Dict

import bpy
from bmesh.ops import split_edges

from sverchok.nodes.list_masks.mask_convert import mask_converter_node
from sverchok.node_tree import SverchCustomTreeNode
from sverchok.data_structure import updateNode, fixed_iter
from sverchok.utils.sv_bmesh_utils import empty_bmesh, add_mesh_to_bmesh, mesh_indexes_from_bmesh
from sverchok.utils.sv_mesh_utils import polygons_to_edges_np
from sverchok.utils.nodes_mixins.sockets_config import ModifierNode
from sverchok.utils.island_mesh import IslandMesh


def split_mesh_elements_node(vertices=None,
                             edges=None,
                             faces=None,
                             face_data=None,
                             mask=None,
                             mask_mode='BY_VERTEX',
                             split_type='VERTS'):

    if not vertices:
        return [], [], [], [], [], []

    edges = edges or []
    faces = faces or []
    face_data = list(fixed_iter(face_data, len(faces))) if face_data else None
    mask = mask or []

    if split_type == 'VERTS':
        if mask_mode != 'BY_VERTEX':
            mask, _, _ = mask_converter_node(
                vertices, edges, faces,
                edges_mask=mask if mask_mode == 'BY_EDGE' else None,
                faces_mask=mask if mask_mode == 'BY_FACE' else None,
                mode=mask_mode)

        vs, es, fs, vi, ei, fi = split_by_vertices(vertices, edges, faces, mask)
    elif split_type == 'EDGES':

        if mask_mode != 'BY_EDGE':
            _, mask, _ = mask_converter_node(
                vertices, edges, faces,
                vertices_mask=mask if mask_mode == 'BY_VERTEX' else None,
                faces_mask=mask if mask_mode == 'BY_FACE' else None,
                mode=mask_mode)

        vs, es, fs, vi, ei, fi = split_by_edges(vertices, edges, faces, mask)
    else:
        raise TypeError(f'Unknown "split_typ" mode = {split_type}')

    return vs, es, fs, vi, ei, fi


def split_by_vertices(verts,
                      edges=None,
                      faces=None,
                      selected_verts: List[bool] = None):
    """it ignores edges without faces currently"""
    faces = faces or []
    if not selected_verts:
        selected_verts = [True] * len(verts)
    elif len(selected_verts) != len(verts):
        selected_verts = list(fixed_iter(selected_verts, len(verts)))

    out_verts = []
    old_v_indexes = []
    out_faces = []
    old_new_verts: Dict[int, int] = dict()
    for face in faces:
        new_face = []
        for i in face:
            if selected_verts[i]:
                out_verts.append(verts[i])
                old_v_indexes.append(i)
                new_face.append(len(out_verts) - 1)
            else:
                if i in old_new_verts:
                    new_face.append(old_new_verts[i])
                else:
                    out_verts.append(verts[i])
                    old_v_indexes.append(i)
                    old_new_verts[i] = len(out_verts) - 1
                    new_face.append(len(out_verts) - 1)
        out_faces.append(new_face)

    if edges:
        edge_indexes = {tuple(sorted(e)): i for i, e in enumerate(edges)}
        out_edges = polygons_to_edges_np([out_faces], unique_edges=True)[0]
        old_e_indexes = []
        for edge in out_edges:
            e = (old_v_indexes[edge[0]], old_v_indexes[edge[1]])
            old_e_indexes.append(edge_indexes.get(tuple(sorted(e)), -1))
    else:
        out_edges = []
        old_e_indexes = []
    old_f_indexes = list(range(len(faces)))
    return out_verts, out_edges, out_faces, old_v_indexes, old_e_indexes, old_f_indexes


def split_by_edges(verts, edges=None, faces=None, selected_edges: List[bool] = None):
    with empty_bmesh() as bm:
        add_mesh_to_bmesh(bm, verts, edges, faces, 'initial_index')
        split_edges(bm, edges=[e for e, b in zip(bm.edges, selected_edges) if b])
        v, e, f, vi, ei, fi, _ = mesh_indexes_from_bmesh(bm, 'initial_index')
        return v, e, f, vi, ei, fi


class SvSplitMeshElements(ModifierNode, SverchCustomTreeNode, bpy.types.Node):
    """
    Triggers: split rip separate

    Split selected mesh elements from each other
    """
    bl_idname = 'SvSplitMeshElements'
    bl_label = 'Split mesh elements'
    bl_icon = 'MOD_EDGESPLIT'

    select_mode_items = [(n.upper(), n, '', ic, i) for i, (n, ic) in enumerate(zip(
        ('By_Vertex', 'By_Edge', 'By_Face'), ('VERTEXSEL', 'EDGESEL', 'FACESEL')))]

    mask_mode: bpy.props.EnumProperty(items=select_mode_items, update=updateNode)
    split_type: bpy.props.EnumProperty(items=[(i.upper(), i, '') for i in ['verts', 'edges']], update=updateNode)

    def draw_buttons(self, context, layout):
        layout.prop(self, 'split_type', expand=True)

    def draw_mask_socket(self, socket, context, layout):
        row = layout.row()
        text = f'. {socket.objects_number}' if socket.objects_number else ""
        row.label(text=f'{socket.label or socket.name}{text}')
        row.prop(self, 'mask_mode', expand=True, icon_only=True)

    def sv_init(self, context):
        self.inputs.new('SvVerticesSocket', 'Vertices')
        self.inputs.new('SvStringsSocket', 'Edges')
        self.inputs.new('SvStringsSocket', 'Faces')
        self.inputs.new('SvStringsSocket', 'FaceData')
        self.inputs.new('SvStringsSocket', 'Mask').custom_draw = 'draw_mask_socket'
        self.outputs.new('SvVerticesSocket', 'Vertices')
        self.outputs.new('SvStringsSocket', 'Edges')
        self.outputs.new('SvStringsSocket', 'Faces')
        self.outputs.new('SvStringsSocket', 'FaceData')

    def process(self):
        vertices = self.inputs['Vertices'].sv_get(deepcopy=False, default=[])
        edges = self.inputs['Edges'].sv_get(deepcopy=False, default=[])
        faces = self.inputs['Faces'].sv_get(deepcopy=False, default=[])
        face_data = self.inputs['FaceData'].sv_get(deepcopy=False, default=[])
        mask = self.inputs['Mask'].sv_get(deepcopy=False, default=[])

        if not edges and faces:
            edges = polygons_to_edges_np(faces, unique_edges=True)

        me = IslandMesh(vertices, edges, faces)
        me.set_attribute('face_data', face_data)
        domain = {'BY_VERTEX': 'POINT', 'BY_EDGE': 'EDGE', 'BY_FACE': 'FACE'}
        me.set_attribute('mask', mask, domain[self.mask_mode])
        vs, es, fs, vi, ei, fi = split_mesh_elements_node(
            me.verts,
            me.edges,
            me.faces,
            me.get_attribute('face_data'),
            me.get_attribute('mask'),
            self.mask_mode,
            self.split_type
        )
        me.update(vs, es, fs, vi, ei, fi)
        vs, es, fs = me.split_islands()

        self.outputs['Vertices'].sv_set(vs)
        self.outputs['Edges'].sv_set(es)
        self.outputs['Faces'].sv_set(fs)
        self.outputs['FaceData'].sv_set([])


register, unregister = bpy.utils.register_classes_factory([SvSplitMeshElements])
