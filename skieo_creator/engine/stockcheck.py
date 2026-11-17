"""Does the player's game still lay its maps out the way the Map Creator's template was made for?

The template (data/map_template.zip, made from scratch in the mod kit by mod-loader-upload/kit/maptemplate.py) was cooked
against the game's classes as they were then. Cooked properties are unversioned -- stored by position in each class's
property list -- so a game update that changes those classes would make the template unreadable for the game. All of
the game's own maps are laid out alike; the fingerprint of one of them (export counts and the unversioned property
headers of its exports, by class) taken when the template was made is compared with the same map in the player's game.
"""
import struct
from collections import defaultdict

from . import legacy_header as lh


def unversioned_header(d):
    """the unversioned property header at the start of an export's data: 16-bit fragments (skip 7 bits, has-zeroes
    bit 7, is-last bit 8, value count bits 9-15) up to the last one, then the zero mask (8, 16 or 32*n bits over the
    values of the zero-flagged fragments)"""
    o, zeros = 0, 0
    while True:
        f = struct.unpack_from('<H', d, o)[0]
        o += 2
        if f & 0x80:
            zeros += f >> 9
        if f & 0x100:
            break
    if zeros:
        o += 1 if zeros <= 8 else 2 if zeros <= 16 else 4 * ((zeros + 31) // 32)
    return bytes(d[:o])


def exports(umap):
    """[(class name, object name, size, offset in the .uexp)] of a legacy package header"""
    f, names, _, _ = lh.parse(umap)
    th = f['total_header_size'][1]
    io_, ni = f['imports_offset'][1], f['imports_count'][1]
    imps = [names[struct.unpack_from('<8i', umap, io_ + 32 * i)[5]] for i in range(ni)]
    eo, ne = f['exports_offset'][1], f['exports_count'][1]
    nxt = f['cell_imports_offset'][1] if f['cell_imports_offset'][1] > 0 else f['depends_offset'][1]
    st = (nxt - eo) // ne
    out = []
    for i in range(ne):
        p = eo + i * st
        cls = struct.unpack_from('<i', umap, p)[0]
        ni_, nn = struct.unpack_from('<ii', umap, p + 16)
        size, off = struct.unpack_from('<qq', umap, p + 28)
        name = names[ni_] + ('_%d' % (nn - 1) if nn else '')
        out.append((imps[-cls - 1] if cls < 0 else 'export%d' % cls, name, size, off - th))
    return out


def fingerprint(umap, uexp):
    """{class: [export count, [distinct unversioned headers, hex]]}"""
    heads = defaultdict(set)
    count = defaultdict(int)
    for cls, _name, size, off in exports(umap):
        count[cls] += 1
        heads[cls].add(unversioned_header(uexp[off:off + size]).hex())
    return {c: [count[c], sorted(heads[c])] for c in sorted(count)}


def differences(want, got):
    """what differs between two fingerprints, as readable lines (empty: the same)"""
    out = []
    for c in sorted(set(want) | set(got)):
        a, b = want.get(c), got.get(c)
        if a is None or b is None:
            out.append('%s: %s in the game, %s expected' % (c, 'missing' if b is None else 'new', 'none' if a is None else 'some'))
        elif a != b:
            out.append('%s: %d exports with %d layouts in the game, %d with %d expected' % (c, b[0], len(b[1]), a[0], len(a[1])))
    return out
