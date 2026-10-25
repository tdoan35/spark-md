import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from sparkmd.imaging.lobes import LungSplit
from sparkmd.imaging.meshes import render_meshes
from sparkmd.imaging.volume import Volume


def read_glb(path):
    data = path.read_bytes()
    magic, version, total = struct.unpack_from('<4sII', data)
    assert (magic, version, total) == (b'glTF', 2, len(data))
    chunks = []
    offset = 12
    while offset < total:
        length, kind = struct.unpack_from('<I4s', data, offset)
        assert length % 4 == 0
        chunks.append((kind, data[offset + 8:offset + 8 + length]))
        offset += 8 + length
    assert offset == total and chunks[0][0] == b'JSON'
    document = json.loads(chunks[0][1])
    binary = chunks[1][1] if len(chunks) > 1 else b''
    assert len(chunks) <= 2
    if len(chunks) == 2:
        assert chunks[1][0] == b'BIN\0'
    for buffer in document.get('buffers', []):
        assert 'uri' not in buffer
        assert buffer['byteLength'] <= len(binary)
    for image in document.get('images', []):
        assert 'uri' not in image
    return document, binary


def accessor(document, binary, index):
    entry = document['accessors'][index]
    view = document['bufferViews'][entry['bufferView']]
    assert entry['componentType'] in (5126, 5125)
    assert view.get('byteOffset', 0) % 4 == 0
    assert 'byteStride' not in view
    dtype = '<f4' if entry['componentType'] == 5126 else '<u4'
    width = {'VEC3': 3, 'SCALAR': 1}[entry['type']]
    offset = view.get('byteOffset', 0) + entry.get('byteOffset', 0)
    length = entry['count'] * width * 4
    assert length <= view['byteLength']
    values = np.frombuffer(binary, dtype=dtype, count=entry['count'] * width, offset=offset)
    return values.reshape(entry['count'], width) if width > 1 else values


def geometry(document, binary, node):
    mesh = document['meshes'][node['mesh']]
    primitive, = mesh['primitives']
    assert primitive.get('mode', 4) == 4
    position_index = primitive['attributes']['POSITION']
    normal_index = primitive['attributes']['NORMAL']
    assert document['accessors'][position_index]['componentType'] == 5126
    assert document['accessors'][normal_index]['componentType'] == 5126
    assert document['accessors'][primitive['indices']]['componentType'] == 5125
    positions = accessor(document, binary, position_index)
    normals = accessor(document, binary, normal_index)
    faces = accessor(document, binary, primitive['indices']).reshape(-1, 3)
    bounds = document['accessors'][position_index]
    np.testing.assert_array_equal(bounds['min'], positions.min(axis=0))
    np.testing.assert_array_equal(bounds['max'], positions.max(axis=0))
    return positions, normals, faces


def synthetic_split(mirrored=False):
    shape = (72, 48, 56)
    x, y, z = np.ogrid[tuple(slice(n) for n in shape)]
    labels = np.zeros(shape, dtype=np.uint8)
    centers = {1: 20 if mirrored else 52, 2: 52 if mirrored else 20}
    for label, cx in centers.items():
        mask = ((x - cx) / 10) ** 2 + ((y - 24) / 14) ** 2 + ((z - 28) / 18) ** 2 <= 1
        labels[mask] = label
    affine = np.diag([-2 if mirrored else 2, 3, 4, 1]).astype(float)
    affine[:3, 3] = [72 if mirrored else -72, -60, -80]
    return LungSplit(labels, affine, {})


def synthetic_volume(split):
    return Volume(np.full(split.labels.shape, -1000, dtype=np.float32),
                  split.affine.copy(), 'synthetic-series')


class TestMeshAssets(unittest.TestCase):
    def assert_outward(self, positions, normals, faces, center):
        self.assertTrue(np.isfinite(positions).all())
        self.assertTrue(np.isfinite(normals).all())
        np.testing.assert_allclose(np.linalg.norm(normals, axis=1), 1, atol=2e-6)
        self.assertGreater(len(faces), 0)
        self.assertLess(int(faces.max()), len(positions))
        triangles = positions[faces].astype(float)
        cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        self.assertTrue((np.linalg.norm(cross, axis=1) > 0).all())
        radial_faces = triangles.mean(axis=1) - center
        self.assertTrue((np.einsum('ij,ij->i', cross, radial_faces) > 0).all())
        self.assertTrue((np.einsum('ij,ij->i', normals, positions - center) > 0).all())
        face_normals = normals[faces].mean(axis=1)
        self.assertTrue((np.einsum('ij,ij->i', cross, face_normals) > 0).all())

    def test_lung_world_geometry_and_winding_with_both_affine_handednesses(self):
        for mirrored in (False, True):
            with self.subTest(mirrored=mirrored), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                split = synthetic_split(mirrored)
                result = render_meshes(split, [], output, 'study-123',
                                       volume=synthetic_volume(split))
                self.assertEqual(result, {
                    'lung_mesh': '/api/studies/study-123/assets/lung.glb',
                    'nodule_mesh': '/api/studies/study-123/assets/nodules.glb'})
                document, binary = read_glb(output / 'lung.glb')
                self.assertEqual(document['asset']['version'], '2.0')
                self.assertEqual(document['scenes'][document['scene']]['nodes'], [0, 1])
                self.assertEqual([node['name'] for node in document['nodes']], ['lung_right', 'lung_left'])
                totals = {'vertices': 0, 'triangles': 0}
                for node in document['nodes']:
                    right = node['name'] == 'lung_right'
                    center = np.array([-32 if right else 32, 32, 12])
                    self.assertNotIn('translation', node)
                    self.assertEqual(document['meshes'][node['mesh']]['name'], node['name'])
                    positions, normals, faces = geometry(document, binary, node)
                    # Physical axes: voxel x -> -R, voxel z -> S, voxel y -> A.
                    np.testing.assert_allclose((positions.min(axis=0) + positions.max(axis=0)) / 2,
                                               center, atol=2)
                    np.testing.assert_allclose((positions.max(axis=0) - positions.min(axis=0)) / 2,
                                               [20, 72, 42], atol=4)
                    self.assertTrue((positions[:, 0] < 0).all() if right else (positions[:, 0] > 0).all())
                    self.assert_outward(positions, normals, faces, center)
                    totals['vertices'] += len(positions)
                    totals['triangles'] += len(faces)
                stats = json.loads((output / 'mesh_stats.json').read_text())
                self.assertEqual(stats['lung']['bytes'], (output / 'lung.glb').stat().st_size)
                self.assertEqual(stats['lung']['nodes'], 2)
                for key, value in totals.items():
                    self.assertEqual(stats['lung'][key], value)
                self.assertEqual(stats['coordinate_mapping']['output'], '(-R,S,A) mm')
                self.assertFalse(stats['coordinate_mapping']['recentered'])
                self.assertEqual(stats['provenance']['lung_affine_ras_mm'], synthetic_split(mirrored).affine.tolist())
                for layer in ('airways', 'vessels', 'skeleton'):
                    audit = stats['layer_audit']['layers'][layer]
                    self.assertEqual(audit['status'], 'absent')
                    self.assertTrue(audit['reason'])
                    self.assertEqual(audit['voxels'], 0)
                    self.assertEqual(stats['provenance']['layers'][layer]['surface_status'], 'omitted')

    def test_detector_markers_have_exact_centers_extents_and_identity(self):
        nodules = [
            {'nodule_id': 'nodule_left_01', 'center_mm': [23.125, -8.75, 41.5], 'size_mm': [8, 12, 20]},
            {'nodule_id': 'nodule_right_02', 'center_mm': [-37.25, 13.5, -11.125], 'size_mm': [18, 6, 10]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            split = synthetic_split()
            render_meshes(split, nodules, output, 'study', volume=synthetic_volume(split))
            document, binary = read_glb(output / 'nodules.glb')
            self.assertEqual(len(document['nodes']), 2)
            for node, source in zip(document['nodes'], nodules):
                mesh = document['meshes'][node['mesh']]
                self.assertEqual(node['name'], source['nodule_id'])
                self.assertEqual(mesh['name'], source['nodule_id'])
                center = [-source['center_mm'][0], source['center_mm'][2], source['center_mm'][1]]
                self.assertEqual(node['translation'], center)
                self.assertNotIn('matrix', node)
                self.assertNotIn('scale', node)
                for item in (node, mesh):
                    self.assertFalse(item['extras']['measurement'])
                    self.assertEqual(item['extras']['kind'], 'detector_box_ellipsoid')
                positions, normals, faces = geometry(document, binary, node)
                extents = np.array(source['size_mm'])[[0, 2, 1]]
                np.testing.assert_allclose(positions.min(axis=0), -extents / 2, atol=1e-6)
                np.testing.assert_allclose(positions.max(axis=0), extents / 2, atol=1e-6)
                np.testing.assert_allclose(positions.mean(axis=0), 0, atol=1e-6)
                world = positions + center
                np.testing.assert_allclose((world.min(axis=0) + world.max(axis=0)) / 2, center, atol=1e-6)
                self.assert_outward(positions, normals, faces, np.zeros(3))
            stats = json.loads((output / 'mesh_stats.json').read_text())
            self.assertEqual(stats['nodules']['bytes'], (output / 'nodules.glb').stat().st_size)
            self.assertEqual(stats['nodules']['nodes'], 2)
            self.assertFalse(stats['provenance']['nodules']['measurement'])

    def test_empty_nodules_are_a_standalone_empty_scene(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            split = synthetic_split()
            render_meshes(split, [], output, 'empty', volume=synthetic_volume(split))
            document, binary = read_glb(output / 'nodules.glb')
            self.assertNotIn('nodes', document)
            self.assertNotIn('nodes', document['scenes'][document['scene']])
            self.assertEqual(document.get('meshes', []), [])
            self.assertEqual(binary, b'')
            self.assertNotIn('buffers', document)
            stats = json.loads((output / 'mesh_stats.json').read_text())
            self.assertEqual(stats['nodules']['triangles'], 0)
            self.assertEqual(stats['nodules']['vertices'], 0)

    def test_volume_boundary_surface_is_closed(self):
        labels = np.zeros((30, 30, 30), dtype=np.uint8)
        labels[:18, 5:25, 5:25] = 1
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            split = LungSplit(labels, np.eye(4), {})
            render_meshes(split, [], output, 'boundary', volume=synthetic_volume(split))
            document, binary = read_glb(output / 'lung.glb')
            node, = document['nodes']
            positions, normals, faces = geometry(document, binary, node)
            self.assertGreater(positions[:, 0].max(), 0)  # Padding closes beyond the first voxel.
            edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
            _, counts = np.unique(np.sort(edges, axis=1), axis=0, return_counts=True)
            np.testing.assert_array_equal(counts, 2)
            self.assert_outward(positions, normals, faces, np.array([-8.5, 14.5, 14.5]))

    def test_all_anatomy_layers_keep_independent_world_geometry_and_serialized_counts(self):
        definitions = {
            'airways': ((12, 12, 16), (7, 8, 10), '#d8e6f2'),
            'vessels': ((40, 17, 35), (8, 6, 9), '#e3a3ae'),
            'skeleton': ((57, 35, 19), (6, 8, 11), '#efe4cf')}
        for mirrored in (False, True):
            with self.subTest(mirrored=mirrored), tempfile.TemporaryDirectory() as directory:
                split = synthetic_split(mirrored)
                split.affine[:3, 3] += [123.25, -77.5, 51.75]
                x, y, z = np.ogrid[tuple(slice(n) for n in split.labels.shape)]
                masks, audit_layers = {}, {}
                voxel_mm3 = abs(np.linalg.det(split.affine[:3, :3]))
                for name, (center, radii, _) in definitions.items():
                    masks[name] = sum(((axis - value) / radius) ** 2
                                      for axis, value, radius in zip((x, y, z), center, radii)) <= 1
                    voxels = int(masks[name].sum())
                    audit_layers[name] = {
                        'status': 'present', 'reason': 'synthetic_geometry',
                        'voxels': voxels, 'volume_mm3': voxels * voxel_mm3,
                        'parameters': {'fixture': 'independent ellipsoid'}}
                audit = {'source': 'synthetic_geometry', 'layers': audit_layers}
                output = Path(directory)
                with patch('sparkmd.imaging.meshes.build_layers', return_value=(masks, audit)):
                    render_meshes(split, [], output, 'layers', volume=synthetic_volume(split))
                document, binary = read_glb(output / 'lung.glb')
                names = ['lung_right', 'lung_left', 'airways', 'vessels', 'skeleton']
                self.assertEqual([node['name'] for node in document['nodes']], names)
                self.assertEqual(document['scenes'][document['scene']]['nodes'], list(range(5)))
                self.assertFalse(document['extras']['recentered'])
                stats = json.loads((output / 'mesh_stats.json').read_text())
                serialized_stats = []
                for node in document['nodes']:
                    mesh = document['meshes'][node['mesh']]
                    self.assertEqual(mesh['name'], node['name'])
                    for transform in ('translation', 'matrix', 'rotation', 'scale'):
                        self.assertNotIn(transform, node)
                    positions, normals, faces = geometry(document, binary, node)
                    primitive, = mesh['primitives']
                    vertex_count = document['accessors'][primitive['attributes']['POSITION']]['count']
                    index_count = document['accessors'][primitive['indices']]['count']
                    self.assertEqual(vertex_count, len(positions))
                    self.assertEqual(index_count, len(faces) * 3)
                    serialized_stats.append({
                        'name': node['name'], 'vertices': vertex_count,
                        'triangles': index_count // 3})
                    if node['name'] not in definitions:
                        continue
                    center_voxel, radii, color = definitions[node['name']]
                    center_ras = (split.affine @ np.r_[center_voxel, 1])[:3]
                    center = center_ras[[0, 2, 1]] * [-1, 1, 1]
                    expected_radii = (np.asarray(radii) * [2, 3, 4])[[0, 2, 1]]
                    np.testing.assert_allclose(
                        (positions.min(axis=0) + positions.max(axis=0)) / 2, center, atol=2)
                    np.testing.assert_allclose(
                        (positions.max(axis=0) - positions.min(axis=0)) / 2,
                        expected_radii, atol=4)
                    self.assert_outward(positions, normals, faces, center)
                    for item in (node, mesh):
                        self.assertFalse(item['extras']['measurement'])
                        self.assertEqual(item['extras']['kind'], 'threshold_anatomy_surface')
                    material = document['materials'][primitive['material']]
                    expected_color = [int(color[start:start + 2], 16) / 255
                                      for start in (1, 3, 5)]
                    self.assertEqual(material['pbrMetallicRoughness']['baseColorFactor'][:3],
                                     expected_color)
                    self.assertEqual(
                        stats['provenance']['layers'][node['name']]['surface_status'], 'emitted')
                self.assertEqual(stats['lung']['meshes'], serialized_stats)
                self.assertEqual(stats['lung']['nodes'], 5)
                self.assertEqual(stats['lung']['bytes'], (output / 'lung.glb').stat().st_size)
                for key in ('vertices', 'triangles'):
                    self.assertEqual(stats['lung'][key], sum(item[key] for item in serialized_stats))

    def test_absent_rejected_and_smoothed_away_masks_do_not_create_placeholder_nodes(self):
        split = synthetic_split()
        empty = np.zeros(split.labels.shape, dtype=bool)
        tiny = empty.copy()
        tiny[12, 15, 19] = True
        masks = {'airways': None, 'vessels': empty, 'skeleton': tiny}
        audit = {'layers': {
            'airways': {'status': 'rejected', 'reason': 'rejected_leak_over_400ml'},
            'vessels': {'status': 'absent', 'reason': 'no_components_over_0_3ml'},
            'skeleton': {'status': 'present', 'reason': 'synthetic_tiny_mask'}}}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with patch('sparkmd.imaging.meshes.build_layers', return_value=(masks, audit)):
                render_meshes(split, [], output, 'missing', volume=synthetic_volume(split))
            document, binary = read_glb(output / 'lung.glb')
            self.assertEqual([node['name'] for node in document['nodes']],
                             ['lung_right', 'lung_left'])
            stats = json.loads((output / 'mesh_stats.json').read_text())
            reasons = {
                'airways': 'mask_absent_or_rejected', 'vessels': 'empty_mask',
                'skeleton': 'no_surface_at_level_0_5_after_smoothing'}
            for name, reason in reasons.items():
                self.assertEqual(stats['provenance']['layers'][name]['surface_status'], 'omitted')
                self.assertEqual(stats['provenance']['layers'][name]['surface_reason'], reason)
            counts = []
            for node in document['nodes']:
                positions, _, faces = geometry(document, binary, node)
                counts.append({'name': node['name'], 'vertices': len(positions),
                               'triangles': len(faces)})
            self.assertEqual(stats['lung']['meshes'], counts)


if __name__ == '__main__':
    unittest.main()
