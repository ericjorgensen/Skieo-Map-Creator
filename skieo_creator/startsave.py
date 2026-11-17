"""A starting save written from scratch, for maps with the real resort in them (OpenStreetMap import).

The game's own maps have no starting save: New Game sets the resort up. A map with the real resort's lifts and trails
starts from this one. It holds only what such a map needs -- the ticket office on the base area and its hub, the camera
over it, the trail map's bounds, the ground cleared round the office -- and resort.add_to_save puts the lifts, trails
and their cleared zones in. Everything else a resort has (weather, snow, staff, the calendar, money, the date) is left
to the game, as for any new game.
Records: data/save_template.bin (packaging/make_save_template.py), blank records of the game's save format.
"""
import datetime
import json
import math

from . import paths
from .engine import gvas_tree as G

OFFICE_COST = 286000          # what the game charges for its ticket office (DT_BuildingEconomy); came free: no refund
OFFICE_CLEAR_CM = 2500.0      # ground cleared of trees round the office
CAMERA_BACK_M, CAMERA_PITCH, CAMERA_YAW = 1400.0, -15.0, 45.0     # looking at the base area from the south-west
_tpl = None


def template():
    """{'gvas': bytes, 'version': (major, minor)}"""
    global _tpl
    if _tpl is None:
        _tpl = dict(gvas=paths.resource('data', 'save_template.bin').read_bytes(),
                    version=tuple(json.loads(paths.resource('data', 'save_template.json').read_text())['version']))
    return _tpl


def _set(tags, name, value):
    t = G.get(tags, name)
    if t is None:
        raise ValueError('save template field %s missing' % name)
    t.value = value


def _text(s):
    return {'flags': 2, 'history': -1, 'text': s}


def build(fr, terrain_gen, base_row, base_col, base_h, names, camera_distance):
    """the GVAS of a starting save with the ticket office at the base area (row, col, height of the landscape grid)"""
    head, tags, tail = G.parse(template()['gvas'])
    ox, oy = (base_col * fr.sp - fr.half) * 100.0, (base_row * fr.sp - fr.half) * 100.0
    oz = (base_h + 32768) * fr.sc * 100.0
    ticks = int((datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                 - datetime.datetime(1, 1, 1)).total_seconds() * 10_000_000)
    _set(tags, 'SlotName', '')
    _set(tags, 'SaveDisplayName', 'Initial Save')
    _set(tags, 'SaveTimestamp', {'Ticks': ticks})
    back, pitch, yaw = CAMERA_BACK_M * 100.0, math.radians(CAMERA_PITCH), math.radians(CAMERA_YAW)
    _set(tags, 'CameraLocation', {'X': ox - back * math.cos(pitch) * math.cos(yaw),
                                  'Y': oy - back * math.cos(pitch) * math.sin(yaw), 'Z': oz - back * math.sin(pitch)})
    _set(tags, 'CameraRotation', {'Pitch': CAMERA_PITCH, 'Yaw': CAMERA_YAW, 'Roll': 0.0})
    _set(tags, 'CameraDistance', float(camera_distance))

    hub = G.new_guid()
    office = G.get(tags, 'Buildings').value[0]
    bd = G.get(office, 'BaseData').value
    _set(bd, 'ID', G.new_guid())
    xf = G.get(bd, 'Transform').value
    _set(xf, 'Rotation', {'X': 0.0, 'Y': 0.0, 'Z': 0.0, 'W': 1.0})
    _set(xf, 'Translation', {'X': ox, 'Y': oy, 'Z': oz})
    _set(xf, 'Scale3D', {'X': 1.0, 'Y': 1.0, 'Z': 1.0})
    _set(bd, 'DisplayName', _text('Ticket Office'))
    _set(bd, 'ConstructionCost', OFFICE_COST)
    _set(bd, 'HubId', hub)
    _set(G.get(bd, 'DesignLocks').value, 'bNoRefund', True)
    for k, v in (('bIsOpen', True), ('OpenHour', 7.0), ('CloseHour', 24.0), ('Condition', 100.0), ('BuiltSeasonIndex', 1)):
        _set(office, k, v)

    name = G.get(G.get(tags, 'HubData').value, 'HubNames').value[0]
    _set(name, 'HubId', hub)
    _set(name, 'Name', _text('Base Area'))
    _set(tags, 'MapPath', names.p_map)
    _set(tags, 'TerrainGeneration', int(terrain_gen))

    lvl = G.get(tags, 'ClearedObstaclesByLevel')
    zones = lvl.value[0][1]
    zone = G.get(zones, 'Zones').value[0]
    _set(zone, 'Center', {'X': ox, 'Y': oy})
    _set(zone, 'Radius', OFFICE_CLEAR_CM)
    lvl.value = [(names.mapn, zones)]

    tm = G.get(tags, 'TrailMapData').value
    e = fr.half * 100.0
    _set(tm, 'CurrentTrailId', 0)
    _set(tm, 'WorldBounds', {'MinX': -e, 'MinY': -e, 'MinZ': 0.0, 'MaxX': e, 'MaxY': e, 'MaxZ': fr.top_z_cm(), 'IsValid': 1})
    _set(tm, 'NavRngSeed', int(terrain_gen) & 0x7FFFFFFF)
    return G.build(head, tags, tail)
