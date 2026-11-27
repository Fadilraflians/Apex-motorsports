"""Membuat GLB sirkuit yang ringan untuk browser.

* geometri dipotong per petak (TILE meter) dan per material, sehingga three.js
  hanya menggambar petak yang terlihat kamera (frustum culling)
* posisi dan normal dipadatkan (KHR_mesh_quantization)
* tekstur dikecilkan dan diubah ke WebP (EXT_texture_webp)
* material transparan berbasis tekstur (pohon, pagar) memakai alpha test, bukan blending
* ekstensi material yang berat (specular, clearcoat) dibuang
"""
import io
import json
import struct

import numpy as np
from PIL import Image

TILE = 600.0
HEAVY_EXTENSIONS = {'KHR_materials_specular', 'KHR_materials_clearcoat', 'KHR_materials_transmission',
                    'KHR_materials_volume', 'KHR_materials_ior', 'KHR_materials_sheen'}


def _texture_users(material):
    """Semua (slot, info) tekstur yang dipakai material."""
    found = []
    pbr = material.get('pbrMetallicRoughness', {})
    for key in ('baseColorTexture', 'metallicRoughnessTexture'):
        if key in pbr:
            found.append((key, pbr[key]))
    for key in ('normalTexture', 'occlusionTexture', 'emissiveTexture'):
        if key in material:
            found.append((key, material[key]))
    return found


def _uv_slot(info):
    transform = info.get('extensions', {}).get('KHR_texture_transform', {})
    return transform.get('texCoord', info.get('texCoord', 0))


def prepare_materials(track, max_size):
    """Material ringan + tekstur WebP. Mengembalikan (materials, textures, images_bytes, uv_slots per material)."""
    document = track.document
    source_textures = document.get('textures', [])
    image_cache = {}
    images, textures = [], []

    def texture_for(texture_index, colour):
        source = source_textures[texture_index].get('source')
        if source is None:
            return None, False
        key = (source, colour)
        if key not in image_cache:
            image = track.open_image(source)
            has_alpha = False
            if colour and image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGBA')
                alpha = np.asarray(image.getchannel('A'))
                has_alpha = alpha.min() < 250
            image = image.convert('RGBA' if has_alpha else 'RGB')
            scale = min(1.0, max_size / max(image.size))
            width = max(4, 2 ** int(round(np.log2(max(1, image.size[0] * scale)))))
            height = max(4, 2 ** int(round(np.log2(max(1, image.size[1] * scale)))))
            width, height = min(width, max_size), min(height, max_size)
            if (width, height) != image.size:
                image = image.resize((width, height), Image.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, 'WEBP', quality=80 if colour else 88, method=4)
            images.append(buffer.getvalue())
            alpha_kind = None
            if has_alpha:
                values = np.asarray(image.getchannel('A'), np.float32) / 255
                middle = ((values > 0.08) & (values < 0.92)).mean()
                alpha_kind = 'blend' if middle > 0.25 else 'mask'
            textures.append({'sampler': 0, 'extensions': {'EXT_texture_webp': {'source': len(images) - 1}}})
            image_cache[key] = (len(textures) - 1, alpha_kind)
        return image_cache[key]

    materials, uv_slots = [], []
    for material in track.materials:
        material = json.loads(json.dumps(material))
        for name in list(material.get('extensions', {})):
            if name in HEAVY_EXTENSIONS:
                del material['extensions'][name]
        if not material.get('extensions'):
            material.pop('extensions', None)
        alpha_kind = None
        slots = set()
        for key, info in _texture_users(material):
            index, kind = texture_for(info['index'], key == 'baseColorTexture')
            if index is None:
                container = material['pbrMetallicRoughness'] if key in ('baseColorTexture', 'metallicRoughnessTexture') else material
                del container[key]
                continue
            info['index'] = index
            slots.add(_uv_slot(info))
            if key == 'baseColorTexture':
                alpha_kind = kind
        if material.get('alphaMode') == 'BLEND':
            factor = material.get('pbrMetallicRoughness', {}).get('baseColorFactor', [1, 1, 1, 1])[3]
            if alpha_kind == 'mask' or (alpha_kind is None and factor >= 0.98):
                # Pohon, pagar, kawat: alpha test jauh lebih murah dan tidak perlu diurutkan.
                material['alphaMode'] = 'MASK' if alpha_kind == 'mask' else 'OPAQUE'
                if alpha_kind == 'mask':
                    material['alphaCutoff'] = 0.5
        materials.append(material)
        uv_slots.append(slots)
    return materials, textures, images, uv_slots


def build_model(track, target, max_texture=1024):
    materials, textures, images, uv_slots = prepare_materials(track, max_texture)

    groups = {}
    for part in track.parts:
        material = part['material']
        names = ['POSITION', 'NORMAL'] if 'NORMAL' in part else ['POSITION']
        slots = uv_slots[material] if material is not None else set()
        names += [f'TEXCOORD_{s}' for s in sorted(slots) if f'TEXCOORD_{s}' in part]
        tri = part['indices']
        centre = part['POSITION'][tri].mean(1)
        tile_x = np.floor(centre[:, 0] / TILE).astype(np.int64)
        tile_z = np.floor(centre[:, 2] / TILE).astype(np.int64)
        tiles = tile_x * 100003 + tile_z
        for tile in np.unique(tiles):
            chosen = tri[tiles == tile]
            key = (int(tile), material, tuple(names))
            groups.setdefault(key, []).append((part, chosen))

    out = bytearray()
    views, accessors, meshes, nodes = [], [], [], []

    def add_view(blob, view_target=None, stride=None):
        while len(out) % 4:
            out.append(0)
        view = {'buffer': 0, 'byteOffset': len(out), 'byteLength': len(blob)}
        if view_target:
            view['target'] = view_target
        if stride:
            view['byteStride'] = stride
        out.extend(blob)
        views.append(view)
        return len(views) - 1

    triangles = 0
    for (tile, material, names), pieces in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1] or 0)):
        columns = {name: [] for name in names}
        indices, offset = [], 0
        for part, chosen in pieces:
            used, local = np.unique(chosen.reshape(-1), return_inverse=True)
            for name in names:
                columns[name].append(part[name][used])
            indices.append(local.reshape(-1) + offset)
            offset += len(used)
        data = {name: np.concatenate(values) for name, values in columns.items()}
        index = np.concatenate(indices)
        position = data['POSITION']
        low, high = position.min(0), position.max(0)
        centre = (low + high) / 2
        # skala seragam: skala node yang tidak seragam akan membengkokkan normal
        half = float(max((high - low).max() / 2, 1e-3))
        packed = {}
        q = np.zeros((len(position), 4), np.int16)
        q[:, :3] = np.round((position - centre) / half * 32767)
        packed['POSITION'] = q
        if 'NORMAL' in data:
            nq = np.zeros((len(position), 4), np.int8)
            nq[:, :3] = np.round(np.clip(data['NORMAL'], -1, 1) * 127)
            packed['NORMAL'] = nq
        for name in names:
            if name.startswith('TEXCOORD'):
                packed[name] = np.ascontiguousarray(data[name], np.float32)

        # vertex identik digabung
        rows = np.concatenate([packed[n].reshape(len(position), -1).view(np.uint8) for n in names], axis=1)
        keys = np.ascontiguousarray(rows).view(np.dtype((np.void, rows.shape[1]))).reshape(-1)
        _, first, inverse = np.unique(keys, return_index=True, return_inverse=True)
        index = inverse.reshape(-1)[index]
        _, first_use = np.unique(index, return_index=True)
        order = np.argsort(first_use)
        rank = np.empty_like(order)
        rank[order] = np.arange(len(order))
        index = rank[index]
        source_rows = first[order]

        attributes = {}
        for name in names:
            values = packed[name][source_rows]
            stride = values.dtype.itemsize * values.shape[1]
            accessor = {'bufferView': add_view(values.tobytes(), 34962, stride), 'count': len(values)}
            if name == 'POSITION':
                accessor.update(componentType=5122, type='VEC3', normalized=True,
                                min=(values[:, :3].min(0) / 32767).tolist(), max=(values[:, :3].max(0) / 32767).tolist())
            elif name == 'NORMAL':
                accessor.update(componentType=5120, type='VEC3', normalized=True)
            else:
                accessor.update(componentType=5126, type='VEC2')
            accessors.append(accessor)
            attributes[name] = len(accessors) - 1
        short = len(source_rows) <= 65535
        blob = index.astype(np.uint16 if short else np.uint32).tobytes()
        accessors.append({'bufferView': add_view(blob, 34963), 'componentType': 5123 if short else 5125,
                          'count': int(len(index)), 'type': 'SCALAR'})
        primitive = {'attributes': attributes, 'indices': len(accessors) - 1}
        if material is not None:
            primitive['material'] = material
        meshes.append({'primitives': [primitive]})
        nodes.append({'mesh': len(meshes) - 1, 'translation': centre.tolist(), 'scale': [half, half, half]})
        triangles += len(index) // 3

    image_entries = []
    for blob in images:
        image_entries.append({'bufferView': add_view(blob), 'mimeType': 'image/webp'})

    while len(out) % 4:
        out.append(0)
    used = {'KHR_mesh_quantization', 'EXT_texture_webp'}
    for material in materials:
        used |= set(material.get('extensions', {}))
        for _, info in _texture_users(material):
            used |= set(info.get('extensions', {}))
    document = {
        'asset': {**track.document['asset'], 'generator': 'apex build_track_models.py'},
        'extensionsUsed': sorted(used),
        'extensionsRequired': ['EXT_texture_webp', 'KHR_mesh_quantization'],
        'scene': 0,
        'scenes': [{'nodes': [len(nodes)]}],
        'nodes': nodes + [{'name': 'track', 'children': list(range(len(nodes)))}],
        'meshes': meshes,
        'materials': materials,
        'accessors': accessors,
        'bufferViews': views,
        'buffers': [{'byteLength': len(out)}],
        'samplers': [{'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497}],
    }
    if textures:
        document['textures'] = textures
        document['images'] = image_entries
    text = json.dumps(document, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    total = 12 + 8 + len(text) + 8 + len(out)
    target.write_bytes(
        struct.pack('<4sII', b'glTF', 2, total)
        + struct.pack('<I4s', len(text), b'JSON') + text
        + struct.pack('<I4s', len(out), b'BIN\0') + bytes(out)
    )
    return {'meshes': len(meshes), 'triangles': triangles, 'images': len(images)}
