"""The one piece of a map the Map Creator cannot make from scratch: the compiled terrain material.

The game's maps draw their landscape with M_Terrain through a "combination" material instance that the editor compiles
from M_Terrain's node graph -- which only the game's developer has; the game holds only the compiled result. Every one
of the game's maps carries an identical copy of it. The Map Creator's template (made from scratch, data/map_template.zip)
points its landscape at a package of each map's own, /Game/Materials/Terrain/Generated/<slug>/MI_<slug>_Terrain; this
module makes that package out of the copy in one of the game's maps, read from the player's game when a map is built,
never shipped.

The instance's data is used as it is (its compiled shader maps carry their own name table): only the package round it
is new. It keeps the stock map's name and import tables, so every index in the data stays valid; imports the instance
does not use become references to /Script/Engine (no other game package is loaded with it); one export.
"""
import struct

from . import legacy_header as lh

RF_PUBLIC_STANDALONE_TRANSACTIONAL = 0x1 | 0x2 | 0x8
PKG_CONTAINS_MAP, PKG_LOAD_UNCOOKED = 0x00020000, 0x00080000
EXPORT_SIZE, IMPORT_SIZE = 96, 32


class Summary:
    """a legacy package summary (the 5.7 layout retoc reads and writes), every field kept for writing it back"""

    def __init__(self, b):
        r = lh.Reader(b)
        self.head = b[:24]                                   # magic, legacy version, UE versions, licensee
        r.o = 24
        self.saved_hash = b[24:44]
        r.o = 44
        r.i32()                                              # total header size: computed
        ncv = r.i32()
        self.custom_versions = b[r.o:r.o + 20 * ncv]
        self.ncv = ncv
        r.o += 20 * ncv
        self.name = r.fstr()
        self.flags = r.u32()
        assert self.flags & 0x80000000, 'expected a cooked (editor-only data filtered) package'
        f = [r.i32() for _ in range(4)]                     # names count / offset, soft objects count / offset
        self.gatherable = (r.i32(), r.i32())
        f += [r.i32() for _ in range(10)]                   # exports, imports, cell exports, cell imports, metadata, depends
        self.soft_package_refs = (r.i32(), r.i32())
        self.searchable_names, self.thumbnails = r.i32(), r.i32()
        ngen = r.i32()
        r.o += ngen * 8
        start = r.o
        for _ in range(2):                                   # saved-by / compatible-with engine version
            r.u16(); r.u16(); r.u16(); r.u32(); r.fstr()
        self.engine_versions = b[start:r.o]
        self.compression, self.num_chunks, self.source = r.u32(), r.i32(), r.u32()
        nadd = r.i32()
        assert nadd == 0, 'additional packages to cook'
        r.i32()                                              # asset registry offset
        r.i64()                                              # bulk data start
        self.world_tile_info = r.i32()
        nchunk = r.i32()
        assert nchunk == 0, 'chunk ids'
        r.i32(); r.i32(); r.i32()                            # preload count / offset, names referenced
        self.payload_toc = r.i64()
        r.i32()                                              # data resources offset
        assert r.o == f[1], 'summary ends at %d, names start at %d' % (r.o, f[1])

    def write(self, name, flags, names_count, names_off, imports, exports, depends, asset_registry, preload, total,
              bulk_start):
        """names_off .. total are offsets / counts of the new package"""
        p = lh.fstring_bytes(name)
        o = (self.head + self.saved_hash + struct.pack('<ii', total, self.ncv) + self.custom_versions + p
             + struct.pack('<I', flags) + struct.pack('<4i', names_count, names_off, 0, imports[1])
             + struct.pack('<2i', *self.gatherable)
             + struct.pack('<10i', exports[0], exports[1], imports[0], imports[1], 0, depends, 0, depends, 0, depends)
             + struct.pack('<2i', *self.soft_package_refs) + struct.pack('<2i', self.searchable_names, self.thumbnails)
             + struct.pack('<i2i', 1, exports[0], names_count) + self.engine_versions
             + struct.pack('<IiI', self.compression, self.num_chunks, self.source) + struct.pack('<i', 0)
             + struct.pack('<iqi', asset_registry, bulk_start, self.world_tile_info) + struct.pack('<i', 0)
             + struct.pack('<3i', preload[0], preload[1], names_count) + struct.pack('<q', self.payload_toc)
             + struct.pack('<i', -1))
        return o


def _summary_size(s, name):
    return len(s.write(name, 0, 0, 0, (0, 0), (0, 0), 0, 0, (0, 0), 0, 0))


def find(umap):
    """(export index 0-based, entry offset) of the stock map's combination material instance: the one
    LandscapeMaterialInstanceConstant with compiled shaders (big; the per-component ones are tiny)"""
    f, names, _, _ = lh.parse(umap)
    io_, ni = f['imports_offset'][1], f['imports_count'][1]
    eo, ne = f['exports_offset'][1], f['exports_count'][1]
    hits = []
    for i in range(ne):
        p = eo + EXPORT_SIZE * i
        cls = struct.unpack_from('<i', umap, p)[0]
        size = struct.unpack_from('<q', umap, p + 28)[0]
        if cls < 0 and names[struct.unpack_from('<i', umap, io_ + IMPORT_SIZE * (-cls - 1) + 20)[0]] == \
                'LandscapeMaterialInstanceConstant' and size > 1000:
            hits.append((i, p))
    if len(hits) != 1:
        raise ValueError('the terrain material: %d compiled landscape material instances in the game\'s map' % len(hits))
    return hits[0]


def extract(umap, uexp, package_name):
    """(uasset, uexp) of a package holding only the stock map's compiled terrain material instance, named after the
    package's last path element"""
    f, names, names_off, names_end = lh.parse(umap)
    th = f['total_header_size'][1]
    io_, ni = f['imports_offset'][1], f['imports_count'][1]
    eo, ne = f['exports_offset'][1], f['exports_count'][1]
    if (f['cell_imports_offset'][1] or f['depends_offset'][1]) - eo != EXPORT_SIZE * ne:
        raise ValueError('export table layout changed')
    imports = [bytearray(umap[io_ + IMPORT_SIZE * i:io_ + IMPORT_SIZE * (i + 1)]) for i in range(ni)]
    _i, ep = find(umap)
    entry = bytearray(umap[ep:ep + EXPORT_SIZE])
    cls, sup, tpl, outer = struct.unpack_from('<4i', entry, 0)
    size, off = struct.unpack_from('<qq', entry, 28)
    data = uexp[off - th:off - th + size]
    first, *counts = struct.unpack_from('<5i', entry, 76)
    pre = list(struct.unpack_from('<%di' % f['preload_count'][1], umap, f['preload_offset'][1]))
    groups, o = [], first
    for c in counts:
        groups.append([d for d in pre[o:o + c] if d < 0])   # its own outer (the landscape actor) is not in the package
        o += c

    # imports it uses, with their outers
    keep = set()
    for d in [cls, tpl] + [d for g in groups for d in g]:
        while d < 0 and -d not in keep:
            keep.add(-d)
            d = struct.unpack_from('<i', imports[-d - 1], 16)[0]
    script = [i for i, e in enumerate(imports) if struct.unpack_from('<i', e, 16)[0] == 0
              and names[struct.unpack_from('<i', e, 20)[0]] == '/Script/Engine']
    if not script:
        raise ValueError('the game\'s map imports nothing from /Script/Engine')
    neutral = bytes(imports[script[0]])
    for i in range(ni):
        if i + 1 not in keep:
            imports[i][:] = neutral

    short = package_name.rsplit('/', 1)[1]
    new_names = list(names) + [n for n in (package_name, short) if n not in names]
    name_index = new_names.index(short)
    names_blob = b''.join(lh.fstring_bytes(n) + b'\0\0\0\0' for n in new_names)

    s = Summary(umap)
    flags = s.flags & ~(PKG_CONTAINS_MAP | PKG_LOAD_UNCOOKED)
    n_off = _summary_size(s, package_name)
    i_off = n_off + len(names_blob)
    e_off = i_off + IMPORT_SIZE * ni
    d_off = e_off + EXPORT_SIZE
    a_off = d_off + 4
    p_off = a_off + 4
    preload = [d for g in groups for d in g]
    total = p_off + 4 * len(preload)

    struct.pack_into('<i', entry, 12, 0)                                     # outer: the package
    struct.pack_into('<ii', entry, 16, name_index, 0)
    struct.pack_into('<I', entry, 24, RF_PUBLIC_STANDALONE_TRANSACTIONAL)
    struct.pack_into('<qq', entry, 28, size, total)
    struct.pack_into('<8i', entry, 44, 0, 0, 0, 0, 0, 0, 1, 0)              # ..., bIsAsset
    struct.pack_into('<5i', entry, 76, 0, *[len(g) for g in groups])

    head = s.write(package_name, flags, len(new_names), n_off, (ni, i_off), (1, e_off), d_off, a_off,
                   (len(preload), p_off), total, total + size)
    assert len(head) == n_off
    ua = (head + names_blob + b''.join(bytes(e) for e in imports) + bytes(entry) + struct.pack('<i', 0)
          + struct.pack('<i', 0) + struct.pack('<%di' % len(preload), *preload))
    assert len(ua) == total
    lh.parse(ua)                                                             # reads back
    return ua, bytes(data)
