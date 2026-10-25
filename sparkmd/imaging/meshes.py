"""Offline display surfaces in unrecentered (-R, S, A) millimetres.

Nodule ellipsoids localize detector boxes; they are not segmented measurements.
"""
import json
from pathlib import Path
import struct

import numpy as np
from scipy import ndimage, sparse
from skimage.measure import marching_cubes


_RAS_TO_GL = np.array([[-1., 0., 0.], [0., 0., 1.], [0., 1., 0.]])
_MARKER = {'kind': 'detector_box_ellipsoid', 'measurement': False,
           'description': 'Display localization marker, not a validated segmented measurement'}


def _outward(vertices, faces):
    # Translation-independent signed volume; these surfaces are closed.
    centered = vertices - vertices.mean(axis=0)
    triangles = centered[faces]
    volume6 = np.einsum('ij,ij->i', triangles[:, 0],
                        np.cross(triangles[:, 1], triangles[:, 2])).sum()
    return faces[:, [0, 2, 1]] if volume6 < 0 else faces


def _normals(vertices, faces):
    triangles = vertices[faces]
    cross = np.cross(triangles[:, 1] - triangles[:, 0],
                     triangles[:, 2] - triangles[:, 0])
    normals = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(normals, faces[:, corner], cross)
    length = np.linalg.norm(normals, axis=1)
    normals /= np.maximum(length[:, None], np.finfo(np.float32).tiny)
    return normals


def _taubin(vertices, faces):
    edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    adjacency = sparse.coo_matrix((np.ones(len(edges) * 2, dtype=np.float32),
                                  (np.concatenate((edges[:, 0], edges[:, 1])),
                                   np.concatenate((edges[:, 1], edges[:, 0])))),
                                 shape=(len(vertices), len(vertices))).tocsr()
    adjacency.data.fill(1)
    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    adjacency = sparse.diags(1 / np.maximum(degree, 1)) @ adjacency
    for _ in range(10):
        for factor in (.5, -.53):
            vertices += factor * (adjacency @ vertices - vertices)
    return vertices


def _lung_surface(labels, bounds, label, affine):
    # Crop before allocating float data; never copy the full CT per surface.
    mask = np.pad(labels[bounds] == label, 4).astype(np.float32)
    ndimage.gaussian_filter(mask, sigma=1, output=mask, mode='constant')
    if mask.max() <= .5:
        return None
    vertices, faces, _, _ = marching_cubes(mask, level=.5, step_size=2,
                                           allow_degenerate=False)
    vertices = _taubin(vertices, faces)
    faces = _outward(vertices, faces)
    vertices += np.array([part.start - 4 for part in bounds])
    transform = _RAS_TO_GL @ affine[:3, :3]
    vertices = vertices @ transform.T + _RAS_TO_GL @ affine[:3, 3]
    if np.linalg.det(transform) < 0:
        faces = faces[:, [0, 2, 1]]
    return vertices, faces


def _ellipsoid(size):
    # Cardinal axes occur explicitly, so bounds equal the detector dimensions.
    sectors, latitudes = 32, 16
    vertices = [[0., 0., 1.]]
    for ring in range(1, latitudes):
        theta = np.pi * ring / latitudes
        for sector in range(sectors):
            phi = 2 * np.pi * sector / sectors
            vertices.append([np.sin(theta) * np.cos(phi),
                             np.sin(theta) * np.sin(phi), np.cos(theta)])
    vertices.append([0., 0., -1.])
    faces = []
    for sector in range(sectors):
        nxt = (sector + 1) % sectors
        faces.append([0, 1 + sector, 1 + nxt])
        for ring in range(latitudes - 2):
            a, b = 1 + ring * sectors + sector, 1 + ring * sectors + nxt
            faces.extend(([a, a + sectors, b], [b, a + sectors, b + sectors]))
        last = 1 + (latitudes - 2) * sectors
        faces.append([last + sector, len(vertices) - 1, last + nxt])
    vertices = np.asarray(vertices) * (np.asarray(size) / 2)
    vertices = vertices @ _RAS_TO_GL.T
    return vertices, _outward(vertices, np.asarray(faces, dtype=np.uint32))


class _GLB:
    def __init__(self):
        self.binary = bytearray()
        self.document = {'asset': {'version': '2.0', 'generator': 'sparkmd offline B9'},
                         'scene': 0, 'scenes': [{}],
                         'extras': {'coordinate_system': '(-R,S,A)', 'units': 'mm',
                                    'recentered': False}}
        self.stats = []

    def _accessor(self, values, component_type, kind, target, bounds=False):
        values = np.ascontiguousarray(values, dtype='<f4' if component_type == 5126 else '<u4')
        self.binary.extend(b'\0' * (-len(self.binary) % 4))
        views = self.document.setdefault('bufferViews', [])
        views.append({'buffer': 0, 'byteOffset': len(self.binary),
                      'byteLength': values.nbytes, 'target': target})
        self.binary.extend(values.tobytes())
        accessor = {'bufferView': len(views) - 1, 'componentType': component_type,
                    'count': len(values), 'type': kind}
        if bounds:
            accessor.update(min=values.min(axis=0).tolist(), max=values.max(axis=0).tolist())
        accessors = self.document.setdefault('accessors', [])
        accessors.append(accessor)
        return len(accessors) - 1

    def add(self, name, vertices, faces, *, translation=None, extras=None, lung=False):
        normals = _normals(vertices, faces)
        attributes = {'POSITION': self._accessor(vertices, 5126, 'VEC3', 34962, True),
                      'NORMAL': self._accessor(normals, 5126, 'VEC3', 34962)}
        indices = self._accessor(faces.reshape(-1), 5125, 'SCALAR', 34963)
        materials = self.document.setdefault('materials', [])
        materials.append({'name': name, 'pbrMetallicRoughness': {
            'baseColorFactor': [.55, .72, .86, .22] if lung else [1., .52, .12, 1.],
            'metallicFactor': 0., 'roughnessFactor': .8},
            'alphaMode': 'BLEND' if lung else 'OPAQUE'})
        meshes = self.document.setdefault('meshes', [])
        mesh = {'name': name, 'primitives': [{'attributes': attributes, 'indices': indices,
                                             'material': len(materials) - 1, 'mode': 4}]}
        node = {'name': name, 'mesh': len(meshes)}
        if translation is not None:
            node['translation'] = translation
        if extras is not None:
            node['extras'] = dict(extras)
            mesh['extras'] = dict(extras)
        meshes.append(mesh)
        nodes = self.document.setdefault('nodes', [])
        self.document['scenes'][0].setdefault('nodes', []).append(len(nodes))
        nodes.append(node)
        self.stats.append({'name': name, 'vertices': len(vertices), 'triangles': len(faces)})

    def save(self, path):
        if self.binary:
            self.document['buffers'] = [{'byteLength': len(self.binary)}]
        encoded = json.dumps(self.document, separators=(',', ':'), allow_nan=False).encode()
        encoded += b' ' * (-len(encoded) % 4)
        binary = bytes(self.binary) + b'\0' * (-len(self.binary) % 4)
        total = 12 + 8 + len(encoded) + (8 + len(binary) if binary else 0)
        with path.open('wb') as stream:
            stream.write(struct.pack('<4sII', b'glTF', 2, total))
            stream.write(struct.pack('<I4s', len(encoded), b'JSON'))
            stream.write(encoded)
            if binary:
                stream.write(struct.pack('<I4s', len(binary), b'BIN\0'))
                stream.write(binary)
        return {'bytes': total, 'nodes': len(self.stats),
                'vertices': sum(item['vertices'] for item in self.stats),
                'triangles': sum(item['triangles'] for item in self.stats),
                'meshes': self.stats}


def render_meshes(lung_split, nodules, output, study_uid):
    """Write standalone lung/nodule GLBs and mesh_stats.json; return asset URLs."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    lungs, markers = _GLB(), _GLB()
    objects = ndimage.find_objects(lung_split.labels, max_label=2)
    for label, name in ((1, 'lung_right'), (2, 'lung_left')):
        bounds = objects[label - 1] if label <= len(objects) else None
        if bounds is not None:
            surface = _lung_surface(lung_split.labels, bounds, label, lung_split.affine)
            if surface is not None:
                lungs.add(name, *surface, lung=True)
    for nodule in nodules:
        vertices, faces = _ellipsoid(nodule['size_mm'])
        center = (_RAS_TO_GL @ np.asarray(nodule['center_mm'], dtype=float)).tolist()
        markers.add(nodule['nodule_id'], vertices, faces, translation=center, extras=_MARKER)
    stats = {'coordinate_mapping': {'input': 'RAS mm', 'output': '(-R,S,A) mm',
                                    'recentered': False},
             'provenance': {'lung': 'threshold LungSplit labels: 1 right, 2 left',
                            'lung_affine_ras_mm': np.asarray(lung_split.affine).tolist(),
                            'gaussian_sigma_voxels': 1, 'marching_cubes_level': .5,
                            'marching_cubes_step_size': 2,
                            'taubin': {'iterations': 10, 'lambda': .5, 'mu': -.53},
                            'nodules': dict(_MARKER)},
             'lung': lungs.save(output / 'lung.glb'),
             'nodules': markers.save(output / 'nodules.glb')}
    (output / 'mesh_stats.json').write_text(json.dumps(stats, indent=2, allow_nan=False) + '\n')
    base = f'/api/studies/{study_uid}/assets/'
    return {'lung_mesh': base + 'lung.glb', 'nodule_mesh': base + 'nodules.glb'}
