"""Measures data/tree_meshes.json from the game's tree meshes: for every tree variant of every species, how many meshes
the game draws for one tree (its trunk, and its canopy if it has one: a second instance) and their triangles. The
game's tree meshes have a single LOD and its trees are hardly ever culled by distance; what a forest costs it per frame
goes with the number of tree instances (trees.TREE_BUDGET), hardly with their triangles. Extract the meshes and the
species first (retoc to-legacy with -f Meshes/Mountain/ -f DA_TreeSpecies_, see docs/DEVELOPMENT.md), then:
usage: python packaging/make_tree_meshes.py <extracted Content folder>"""
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from skieo_creator.engine import legacy_header as lh  # noqa: E402


def lod_triangles(ue):
    """(triangles of LOD 0, number of LODs) of a cooked static mesh's .uexp, or (None, None): its render data has int32
    LOD count, strip flags 05 08, int32 section count, then 40-byte sections (MaterialIndex, FirstIndex, NumTriangles,
    MinVertexIndex, MaxVertexIndex, five UBOOLs) that tile the index buffer, in any order"""
    for m in re.finditer(re.escape(b'\x05\x08'), ue):
        p = m.start()
        if p < 4 or p + 6 > len(ue):
            continue
        lods = struct.unpack_from('<i', ue, p - 4)[0]
        count = struct.unpack_from('<i', ue, p + 2)[0]
        if not (1 <= lods <= 8 and 1 <= count <= 16) or p + 6 + 40 * count > len(ue):
            continue
        secs = [struct.unpack_from('<iIIII5I', ue, p + 6 + 40 * k) for k in range(count)]
        if not all(0 <= s[0] < 64 and 0 < s[2] < 5_000_000 and s[3] <= s[4] and all(f in (0, 1) for f in s[5:])
                   for s in secs):
            continue
        at = 0
        for first, n in sorted((s[1], s[2]) for s in secs):
            if first != at:
                break
            at += 3 * n
        else:
            return sum(s[2] for s in secs), lods
    return None, None


def variants(ua, ue):
    """[(size, state, trunk mesh, canopy mesh or None)] of a DA_TreeSpecies_* asset (as trees.species_variants, with
    the CanopyMesh import that follows the trunk unless its zero-mask bit 3 is set)"""
    f, names, _, _ = lh.parse(ua)
    n, off = f['imports_count'][1], f['imports_offset'][1]
    imps = [names[struct.unpack_from('<8i', ua, off + 32 * i)[5]] for i in range(n)]
    out, p = [], 0
    while True:
        p = ue.find(b'\x80\x11', p)
        if p < 0:
            break
        m, q = ue[p + 2], p + 3
        size = 0 if m & 1 else ue[q]
        q += 0 if m & 1 else 1
        state = 0 if m & 2 else ue[q]
        q += 0 if m & 2 else 1
        trunk = struct.unpack_from('<i', ue, q)[0]
        canopy = None
        if not m & 8:
            c = struct.unpack_from('<i', ue, q + 4)[0]
            canopy = imps[-c - 1] if -len(imps) <= c < 0 else None
        if not (-len(imps) <= trunk < 0) or size > 3 or state > 3:
            raise ValueError('unexpected tree species layout')
        out.append((size, state, imps[-trunk - 1], canopy))
        p += 2
    return out


def main():
    content = Path(sys.argv[1])
    tris, more = {}, []
    for ue in sorted((content / 'Meshes').rglob('*.uexp')):
        t, lods = lod_triangles(ue.read_bytes())
        if t:
            tris[ue.stem] = t
            if lods > 1:
                more.append(ue.stem)
    out, missing = {}, set()
    for ua in sorted((content / 'Data/Trees').glob('DA_TreeSpecies_*.uasset')):
        sp = ua.stem.replace('DA_TreeSpecies_', '')
        for size, state, trunk, canopy in variants(ua.read_bytes(), ua.with_suffix('.uexp').read_bytes()):
            meshes = [trunk] + ([canopy] if canopy else [])
            missing |= {m for m in meshes if m not in tris}
            if all(m in tris for m in meshes):
                out['%s|%d|%d|%s' % (sp, size, state, trunk)] = [len(meshes), sum(tris[m] for m in meshes)]
    if not out:
        raise SystemExit('no tree variants measured: is %s an extracted Content folder?' % content)
    vals = sorted(v[1] for v in out.values())
    data = dict(source='measured from the game\'s tree meshes by packaging/make_tree_meshes.py',
                note='per tree of each variant (species|size|state|trunk mesh): [meshes drawn (trunk, and canopy if '
                     'any), triangles of those meshes at LOD 0]',
                default=[1, vals[len(vals) // 2]], variants=out)
    (ROOT / 'data' / 'tree_meshes.json').write_text(json.dumps(data, separators=(',', ':')), encoding='utf-8')
    print('wrote data/tree_meshes.json: %d variants of %d meshes (%d with a canopy), %d-%d triangles per tree (median '
          '%d)' % (len(out), len(tris), sum(v[0] == 2 for v in out.values()), vals[0], vals[-1], data['default'][1]))
    if missing:
        print('  not measured (left out):', ', '.join(sorted(missing)))
    if more:
        print('  meshes with more than one LOD (counted at LOD 0):', ', '.join(more))


if __name__ == '__main__':
    main()
