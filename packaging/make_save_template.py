"""Authors only: make data/save_template.bin, the blank records the Map Creator writes a starting save from
(skieo_creator/startsave.py; maps with the real resort only -- the others start empty, like the game's own maps).

The record layouts (type trees, flags, field order) come from a save of the current game version with a ticket office,
its hub and cleared ground; every value is blanked here and only the structure ships, as for resort_templates.bin.
The save version numbers come from the game's own starting-save asset (InitialSaveAsset: SaveMajorVersion /
SaveMinorVersion), extracted with retoc (-f InitialSaves/).
usage: python packaging/make_save_template.py <a .sav with a ticket office> <an extracted InitialSaves/IS_*.uexp>"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'packaging'))
from skieo_creator.engine import gvas_tree as G  # noqa: E402
from make_resort_templates import blank, field  # noqa: E402

ROOT_PROPS = ['SlotName', 'SaveDisplayName', 'SaveTimestamp', 'CameraLocation', 'CameraRotation', 'CameraDistance', 'Buildings',
              'HubData', 'MapPath', 'TerrainGeneration', 'ClearedObstaclesByLevel', 'TrailMapData']


def plain_texts(tags):
    """texts the reader keeps raw (formatted / localized histories) -> plain ones, before blanking"""
    for t in tags:
        if t.tree[0] == 'TextProperty' and isinstance(t.value, G.Raw):
            t.value = {'flags': 2, 'history': -1, 'text': 'x'}
        elif isinstance(t.value, list):
            for v in t.value:
                if isinstance(v, list):
                    plain_texts(v)
                elif isinstance(v, G.Tag):
                    plain_texts([v])
                elif isinstance(v, tuple) and isinstance(v[1], list):
                    plain_texts(v[1])
    return tags


def one(tag, pick=lambda e: True):
    """an array tag cut to one element (the first that pick() likes), blanked"""
    e = next(e for e in tag.value if pick(e))
    tag.value = [blank(plain_texts(e))]


def main(sav, is_uexp):
    head, tags, tail = G.parse(Path(sav).read_bytes())
    by = {n: field(tags, n) for n in ROOT_PROPS}
    one(by['Buildings'], lambda b: 'TicketOffice' in G.get(b, 'BuildingClassPath').value.get('asset', ''))
    one(field(by['HubData'].value, 'HubNames'))
    key, lvl = by['ClearedObstaclesByLevel'].value[0]
    zones = field(lvl, 'Zones')
    circle = next(z for z in zones.value if not G.plain(field(z, 'Outline')) and G.plain(field(z, 'EndOffset'))['X'] == 0)
    blank(plain_texts([t for t in lvl if t.name != 'Zones']))
    zones.value = [blank(circle)]
    by['ClearedObstaclesByLevel'].value = [('', lvl)]
    # RegisteredTrails left out: the importer puts it first in TrailMapData (resort.add_to_save)
    by['TrailMapData'].value = blank(plain_texts([t for t in by['TrailMapData'].value if t.name != 'RegisteredTrails']))
    blank(plain_texts([by[n] for n in ROOT_PROPS if n not in ('Buildings', 'HubData', 'ClearedObstaclesByLevel',
                                                               'TrailMapData')]))
    for n in ROOT_PROPS:
        if by[n].tree[0] == 'StrProperty':
            by[n].value = ''
    out = G.build(head, [by[n] for n in ROOT_PROPS], tail)
    G.parse(out)                                                           # reads back
    ue = Path(is_uexp).read_bytes()
    n = struct.unpack_from('<i', ue, 2)[0]
    major, minor = struct.unpack_from('<ii', ue, 6 + n)
    (ROOT / 'data' / 'save_template.bin').write_bytes(out)
    (ROOT / 'data' / 'save_template.json').write_text(json.dumps({'version': [major, minor]}), encoding='utf-8')
    print('save_template.bin: %d bytes (%s), save version %d.%d' % (len(out), ', '.join(ROOT_PROPS), major, minor))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
