"""Authors only: measure data/forest_stats.json from the game's own forests, so the Map Creator never reads a game map's
forest when it builds a map (it plants its own; trees.forest).

Measured from the baked obstacles (DA_BakedObstacles_*) of Mad River Glen (the 'mrg' look) and Sugar Bowl ('sb'):
  * density: trees per m2 where trees grow on the game's maps (75th percentile of 30 m cells, Mad River Glen);
  * per look: the forest header's last 4 floats (the trees' scale range) and the trees' scale (u16, width = height) as
    a SCALE_BINS-bin histogram per height band (BANDS, over the forest's own 1-99 % height range) and size class (0-3).
Yaw is near uniform on both maps, so it is drawn uniformly.
Extract the two forests first (retoc to-legacy -f DA_BakedObstacles_Map_mad_river_glen_real.
-f DA_BakedObstacles_Map_sugar_bowl_real.), then:
usage: python packaging/make_forest_stats.py <extracted Content folder>"""
import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from skieo_creator import trees  # noqa: E402

LOOKS = {'mrg': 'Map_mad_river_glen_real', 'sb': 'Map_sugar_bowl_real'}
SCALE_BINS = 32


def look(skob):
    rec = np.frombuffer(skob['records'], np.uint8).reshape(-1, trees.STRIDE)
    ents = trees.table_entries(skob['table'])
    z = rec[:, 8:12].copy().view('<i4').ravel().astype(np.float64)
    lo, hi = np.percentile(z, [1, 99])
    band = np.clip(((z - lo) / max(hi - lo, 1.0) * trees.BANDS).astype(int), 0, trees.BANDS - 1)
    size = np.array([e[1] for e in ents], np.int64)[rec[:, 18:20].copy().view('<u2').ravel()]
    w = rec[:, 14:16].copy().view('<u2').ravel()
    h = rec[:, 16:18].copy().view('<u2').ravel()
    assert (w == h).all(), 'trees with width != height'
    b = np.minimum(w.astype(np.int64) * SCALE_BINS // 65536, SCALE_BINS - 1)
    hist = np.zeros((trees.BANDS, 4, SCALE_BINS), np.int64)
    np.add.at(hist, (band, size, b), 1)
    return dict(header=[float(v) for v in struct.unpack('<4f', skob['hdr'][16:])], scale=hist.tolist(),
                trees=int(len(rec)))


def density(skob):
    rec = np.frombuffer(skob['records'], np.uint8).reshape(-1, trees.STRIDE)
    x = rec[:, 0:4].copy().view('<i4').ravel() / 1000.0
    y = rec[:, 4:8].copy().view('<i4').ravel() / 1000.0
    cell = (x // 30).astype(np.int64) * 1000 + (y // 30).astype(np.int64)
    return float(np.percentile(np.unique(cell, return_counts=True)[1], 75) / 900.0)


def main(content):
    skobs = {k: trees.read_skob((Path(content) / 'Generated' / ('DA_BakedObstacles_%s.uexp' % m)).read_bytes())
             for k, m in LOOKS.items()}
    out = dict(source='baked obstacles of %s (density: %s)' % (', '.join(LOOKS.values()), LOOKS['mrg']),
               density=density(skobs['mrg']), scale_bins=SCALE_BINS,
               looks={k: look(v) for k, v in skobs.items()})
    (ROOT / 'data' / 'forest_stats.json').write_text(json.dumps(out), encoding='utf-8')
    print('forest_stats.json: density %.5f trees/m2; %s' % (
        out['density'], ', '.join('%s %d trees, scale %s' % (k, v['trees'], v['header'][2:]) for k, v in out['looks'].items())))


if __name__ == '__main__':
    main(sys.argv[1])
