"""Alat bersama untuk membaca GLB sirkuit dari folder Track (dipakai build_track_models.py)."""
import io
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from optimize_cars import node_matrix, read_accessor, read_glb, texture_slots  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load_layouts():
    """Denah lintasan (x, z, tinggi) dari lib/track-layouts.ts, sesuai arah balap."""
    text = (ROOT / 'lib' / 'track-layouts.ts').read_text(encoding='utf-8')
    result = {}
    for match in re.finditer(r'(\d+): \{ width: ([\d.]+), points: \[([^\]]*)\]', text):
        values = np.array([float(v) for v in match.group(3).split(',') if v.strip()]).reshape(-1, 3)
        result[int(match.group(1))] = (float(match.group(2)), values)
    return result


class Track:
    """Semua segitiga GLB dalam koordinat dunia (Y ke atas), dikelompokkan per primitive."""

    def __init__(self, path):
        self.path = Path(path)
        self.document, self.binary = read_glb(self.path)
        self.materials = self.document.get('materials', [])
        self.parts = []
        document = self.document

        def visit(index, parent):
            node = document['nodes'][index]
            matrix = parent @ node_matrix(node)
            if 'mesh' in node:
                for primitive in document['meshes'][node['mesh']]['primitives']:
                    if primitive.get('mode', 4) == 4:
                        self.parts.append(self._read(primitive, matrix))
            for child in node.get('children', []):
                visit(child, matrix)

        for root in document['scenes'][document.get('scene', 0)]['nodes']:
            visit(root, np.eye(4))

    def _read(self, primitive, matrix):
        document, binary = self.document, self.binary
        attributes = primitive['attributes']
        material_index = primitive.get('material')
        material = self.materials[material_index] if material_index is not None else {}
        position = read_accessor(document, binary, attributes['POSITION']).astype(np.float64)
        position = position @ matrix[:3, :3].T + matrix[:3, 3]
        part = {'material': material_index, 'POSITION': position}
        if 'NORMAL' in attributes:
            normal_matrix = np.linalg.pinv(matrix[:3, :3]).T
            normal = read_accessor(document, binary, attributes['NORMAL']) @ normal_matrix.T
            normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
            part['NORMAL'] = normal.astype(np.float32)
        for slot in sorted(texture_slots(material, set())):
            name = f'TEXCOORD_{slot}'
            if name in attributes:
                part[name] = read_accessor(document, binary, attributes[name]).astype(np.float32)
        if 'indices' in primitive:
            indices = read_accessor(document, binary, primitive['indices']).reshape(-1).astype(np.int64)
        else:
            indices = np.arange(len(position))
        indices = indices[:len(indices) // 3 * 3].reshape(-1, 3)
        if np.linalg.det(matrix[:3, :3]) < 0:
            indices = indices[:, ::-1]
        part['indices'] = indices
        return part

    def image_bytes(self, image_index):
        image = self.document['images'][image_index]
        view = self.document['bufferViews'][image['bufferView']]
        start = view.get('byteOffset', 0)
        return self.binary[start:start + view['byteLength']]

    def open_image(self, image_index):
        return Image.open(io.BytesIO(self.image_bytes(image_index)))

    def triangles(self, parts=None):
        """(a, b, c, material) untuk semua segitiga."""
        parts = self.parts if parts is None else parts
        a, b, c, m = [], [], [], []
        for part in parts:
            tri = part['POSITION'][part['indices']]
            a.append(tri[:, 0]); b.append(tri[:, 1]); c.append(tri[:, 2])
            m.append(np.full(len(tri), -1 if part['material'] is None else part['material']))
        return np.concatenate(a), np.concatenate(b), np.concatenate(c), np.concatenate(m)
