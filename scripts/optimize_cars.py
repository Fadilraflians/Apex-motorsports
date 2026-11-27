"""Membuat versi ringan dari model mobil agar cepat tampil.

Sumber : "Mobil Sport/*.glb" (tidak diubah)
Hasil  : "public/cars/*.glb"
Pakai  : python scripts/optimize_cars.py     (butuh numpy)

Yang dilakukan:
  * menggabungkan ribuan potongan mesh menjadi satu per material (draw call jauh berkurang)
  * membuang data yang tidak dipakai (tangent, UV cadangan, warna vertex putih)
  * memadatkan posisi dan normal (KHR_mesh_quantization)
  * mengganti kaca "transmission" yang berat dengan transparansi biasa
Tekstur disalin apa adanya.
"""
import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'Mobil Sport'
TARGET = ROOT / 'public' / 'cars'

DTYPES = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}


def read_glb(path):
    data = path.read_bytes()
    json_length = struct.unpack('<I', data[12:16])[0]
    document = json.loads(data[20:20 + json_length])
    binary = data[20 + json_length + 8:]
    return document, binary


def read_accessor(document, binary, index):
    accessor = document['accessors'][index]
    view = document['bufferViews'][accessor['bufferView']]
    dtype = np.dtype(DTYPES[accessor['componentType']])
    width = WIDTHS[accessor['type']]
    count = accessor['count']
    offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
    item = dtype.itemsize * width
    stride = view.get('byteStride', item)
    raw = np.frombuffer(binary, np.uint8, count=(count - 1) * stride + item, offset=offset)
    if stride != item:
        raw = np.lib.stride_tricks.as_strided(raw, (count, item), (stride, 1))
    values = np.ascontiguousarray(raw).reshape(-1).view(dtype).reshape(count, width)
    if accessor.get('normalized') and dtype.kind in 'iu':
        values = values.astype(np.float32) / np.iinfo(dtype).max
    return values


def node_matrix(node):
    if 'matrix' in node:
        return np.array(node['matrix'], np.float64).reshape(4, 4).T
    x, y, z, w = node.get('rotation', [0, 0, 0, 1])
    rotation = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    matrix = np.eye(4)
    matrix[:3, :3] = rotation * np.array(node.get('scale', [1, 1, 1]))
    matrix[:3, 3] = node.get('translation', [0, 0, 0])
    return matrix


def texture_slots(value, found):
    """Mengumpulkan nomor set UV dari semua referensi tekstur di dalam material."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key.endswith('Texture') and isinstance(child, dict) and 'index' in child:
                transform = child.get('extensions', {}).get('KHR_texture_transform', {})
                found.add(transform.get('texCoord', child.get('texCoord', 0)))
            texture_slots(child, found)
    elif isinstance(value, list):
        for child in value:
            texture_slots(child, found)
    return found


def simplify_glass(material):
    extensions = material.get('extensions', {})
    transmission = extensions.pop('KHR_materials_transmission', None)
    extensions.pop('KHR_materials_volume', None)
    if transmission is None:
        return
    amount = transmission.get('transmissionFactor', 0)
    if amount <= 0 and 'transmissionTexture' not in transmission:
        return
    pbr = material.setdefault('pbrMetallicRoughness', {})
    color = pbr.get('baseColorFactor', [1, 1, 1, 1])
    alpha = min(color[3], max(0.18, 1 - 0.75 * amount))
    pbr['baseColorFactor'] = color[:3] + [alpha]
    material['alphaMode'] = 'BLEND'


def optimize(source, target):
    document, binary = read_glb(source)
    materials = document.get('materials', [])

    # Material yang isinya persis sama digabung.
    unique, remap, seen = [], {}, {}
    for index, material in enumerate(materials):
        key = json.dumps(material, sort_keys=True)
        if key not in seen:
            seen[key] = len(unique)
            unique.append(json.loads(key))
        remap[index] = seen[key]

    instances = []

    def visit(index, parent):
        node = document['nodes'][index]
        matrix = parent @ node_matrix(node)
        if 'mesh' in node:
            instances.extend((p, matrix) for p in document['meshes'][node['mesh']]['primitives'])
        for child in node.get('children', []):
            visit(child, matrix)

    for root in document['scenes'][document.get('scene', 0)]['nodes']:
        visit(root, np.eye(4))

    groups = {}
    for primitive, matrix in instances:
        if primitive.get('mode', 4) != 4:
            continue
        material_index = remap.get(primitive.get('material'), None)
        material = unique[material_index] if material_index is not None else {}
        attributes = primitive['attributes']
        position = read_accessor(document, binary, attributes['POSITION']).astype(np.float64)
        position = position @ matrix[:3, :3].T + matrix[:3, 3]
        part = {'POSITION': position}

        if 'NORMAL' in attributes:
            normal_matrix = np.linalg.pinv(matrix[:3, :3]).T
            normal = read_accessor(document, binary, attributes['NORMAL']) @ normal_matrix.T
            normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
            part['NORMAL'] = normal

        for slot in sorted(texture_slots(material, set())):
            name = f'TEXCOORD_{slot}'
            if name in attributes:
                part[name] = read_accessor(document, binary, attributes[name]).astype(np.float32)

        if 'COLOR_0' in attributes:
            color = read_accessor(document, binary, attributes['COLOR_0']).astype(np.float32)
            if color.min() < 0.996:
                if color.shape[1] == 3:
                    color = np.column_stack([color, np.ones(len(color))])
                part['COLOR_0'] = color

        if 'indices' in primitive:
            indices = read_accessor(document, binary, primitive['indices']).reshape(-1).astype(np.int64)
        else:
            indices = np.arange(len(position))
        indices = indices[:len(indices) // 3 * 3]
        if np.linalg.det(matrix[:3, :3]) < 0:  # cermin: balik arah segitiga
            indices = indices.reshape(-1, 3)[:, ::-1].reshape(-1)

        key = (material_index, tuple(sorted(part)))
        groups.setdefault(key, []).append((part, indices))

    everything = np.concatenate([part['POSITION'] for group in groups.values() for part, _ in group])
    low, high = everything.min(0), everything.max(0)
    center = (low + high) / 2
    half = float((high - low).max() / 2) or 1.0

    out_binary = bytearray()
    views, accessors, primitives = [], [], []

    def add_view(blob, view_target=None, stride=None):
        while len(out_binary) % 4:
            out_binary.append(0)
        view = {'buffer': 0, 'byteOffset': len(out_binary), 'byteLength': len(blob)}
        if view_target:
            view['target'] = view_target
        if stride:
            view['byteStride'] = stride
        out_binary.extend(blob)
        views.append(view)
        return len(views) - 1

    for (material_index, names), parts in groups.items():
        columns = {}
        for name in names:
            values = np.concatenate([part[name] for part, _ in parts])
            if name == 'POSITION':
                packed = np.zeros((len(values), 4), np.int16)
                packed[:, :3] = np.round((values - center) / half * 32767)
            elif name == 'NORMAL':
                packed = np.zeros((len(values), 4), np.int8)
                packed[:, :3] = np.round(np.clip(values, -1, 1) * 127)
            elif name == 'COLOR_0':
                packed = np.round(np.clip(values, 0, 1) * 255).astype(np.uint8)
            else:
                packed = np.ascontiguousarray(values, np.float32)
            columns[name] = np.ascontiguousarray(packed)

        offsets = np.cumsum([0] + [len(part['POSITION']) for part, _ in parts[:-1]])
        indices = np.concatenate([index + offset for (_, index), offset in zip(parts, offsets)])

        # Satukan vertex yang identik dan buang yang tidak dipakai.
        rows = np.concatenate([columns[n].reshape(len(columns[n]), -1).view(np.uint8) for n in names], axis=1)
        keys = np.ascontiguousarray(rows).view(np.dtype((np.void, rows.shape[1]))).reshape(-1)
        _, first, inverse = np.unique(keys, return_index=True, return_inverse=True)
        indices = inverse.reshape(-1)[indices]
        used, indices = np.unique(indices, return_inverse=True)
        # Urutkan vertex sesuai urutan pemakaian agar ramah cache GPU.
        _, first_use = np.unique(indices, return_index=True)
        order = np.argsort(first_use)
        rank = np.empty_like(order)
        rank[order] = np.arange(len(order))
        indices = rank[indices.reshape(-1)]
        source_rows = first[used][order]

        attributes = {}
        for name in names:
            data = columns[name][source_rows]
            count = len(data)
            stride = data.dtype.itemsize * data.shape[1]
            accessor = {'bufferView': add_view(data.tobytes(), 34962, stride), 'count': count}
            if name == 'POSITION':
                accessor.update(componentType=5122, type='VEC3', normalized=True,
                                min=data[:, :3].min(0).tolist(), max=data[:, :3].max(0).tolist())
            elif name == 'NORMAL':
                accessor.update(componentType=5120, type='VEC3', normalized=True)
            elif name == 'COLOR_0':
                accessor.update(componentType=5121, type='VEC4', normalized=True)
            else:
                accessor.update(componentType=5126, type='VEC2')
            accessors.append(accessor)
            attributes[name] = len(accessors) - 1

        short = len(source_rows) <= 65535
        blob = indices.astype(np.uint16 if short else np.uint32).tobytes()
        accessors.append({'bufferView': add_view(blob, 34963), 'componentType': 5123 if short else 5125,
                          'count': int(len(indices)), 'type': 'SCALAR'})
        primitive = {'attributes': attributes, 'indices': len(accessors) - 1}
        if material_index is not None:
            primitive['material'] = material_index
        primitives.append(primitive)

    images = []
    for image in document.get('images', []):
        image = dict(image)
        if 'bufferView' in image:
            view = document['bufferViews'][image['bufferView']]
            start = view.get('byteOffset', 0)
            image['bufferView'] = add_view(binary[start:start + view['byteLength']])
        images.append(image)

    for material in unique:
        simplify_glass(material)
        if not material.get('extensions', True):
            del material['extensions']

    dropped = {'KHR_materials_transmission', 'KHR_materials_volume'}
    used_extensions = sorted(set(document.get('extensionsUsed', [])) - dropped | {'KHR_mesh_quantization'})

    result = {
        'asset': document['asset'],
        'extensionsUsed': used_extensions,
        'extensionsRequired': sorted(set(document.get('extensionsRequired', [])) - dropped | {'KHR_mesh_quantization'}),
        'scene': 0,
        'scenes': [{'nodes': [0]}],
        'nodes': [{'mesh': 0, 'translation': center.tolist(), 'scale': [half, half, half]}],
        'meshes': [{'primitives': primitives}],
        'materials': unique,
        'accessors': accessors,
        'bufferViews': views,
    }
    for key in ('textures', 'samplers'):
        if key in document:
            result[key] = document[key]
    if images:
        result['images'] = images

    while len(out_binary) % 4:
        out_binary.append(0)
    result['buffers'] = [{'byteLength': len(out_binary)}]
    text = json.dumps(result, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    total = 12 + 8 + len(text) + 8 + len(out_binary)
    target.write_bytes(
        struct.pack('<4sII', b'glTF', 2, total)
        + struct.pack('<I4s', len(text), b'JSON') + text
        + struct.pack('<I4s', len(out_binary), b'BIN\0') + bytes(out_binary)
    )
    return len(instances), len(primitives)


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    wanted = sys.argv[1:]
    before = after = 0
    for source in sorted(SOURCE.glob('*.glb')):
        if wanted and source.stem not in wanted:
            continue
        target = TARGET / source.name
        parts, merged = optimize(source, target)
        size_in, size_out = source.stat().st_size, target.stat().st_size
        before += size_in
        after += size_out
        print(f'{source.stem[:44]:44} {size_in / 1e6:5.1f} -> {size_out / 1e6:5.1f} MB   potongan {parts:4} -> {merged}', flush=True)
    print(f'TOTAL {before / 1e6:.0f} -> {after / 1e6:.0f} MB')


if __name__ == '__main__':
    main()
