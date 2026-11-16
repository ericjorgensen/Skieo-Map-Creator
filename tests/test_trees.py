"""Self-check of the forest (skieo_creator/trees.py, ecology.py) on a made-up mountain: no game, no downloads
(the species patterns come from data/tree_patterns.json).
usage: python tests/test_trees.py"""
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skieo_creator import trees  # noqa: E402

G, SP, HMIN, TOP = trees.G, 5.0, 400.0, 1250.0
SC = 1000.0 / 65535
rng = np.random.default_rng(3)

# a 10 km map: a mountain in the middle (1,250 m) over rolling ground with valleys (400-650 m)
yy, xx = np.mgrid[0:G, 0:G] * SP
r = np.hypot(xx - 5000, yy - 5000)
E = HMIN + 120 + 100 * np.sin(xx / 900.0) * np.cos(yy / 1300.0) + 730 * np.exp(-(r / 1900.0) ** 2)
H = (np.rint((E - HMIN) / SC) - 32768).astype(np.int64)

# a donor forest: 20,000 trees on 1 km2 (the stock density), every size and condition of the game's tables
ents = [('DA_TreeSpecies_Spruce', s, c, 'SM_Spruce_%d_%d' % (s, c)) for s in range(4) for c in (0, 1, 2)] + \
       [('DA_TreeSpecies_Spruce', 0, 3, 'SM_Spruce_krummholz')]
n = 20000
kind = rng.choice(len(ents), n, p=np.r_[[0.08] * 12, [0.04]] / np.sum(np.r_[[0.08] * 12, [0.04]]))
rec = np.zeros((n, trees.STRIDE), np.uint8)
rec[:, 0:4] = (rng.uniform(0, 1000, n) * 1000).astype('<i4').view(np.uint8).reshape(-1, 4)
rec[:, 4:8] = (rng.uniform(0, 1000, n) * 1000).astype('<i4').view(np.uint8).reshape(-1, 4)
rec[:, 8:12] = (rng.uniform(0, 600, n) * 1000).astype('<i4').view(np.uint8).reshape(-1, 4)
rec[:, 12:18] = rng.integers(0, 256, (n, 6))
rec[:, 18:20] = kind.astype('<u2').view(np.uint8).reshape(-1, 2)
donor = dict(hdr=bytes(32), table=trees.encode_table(ents), records=rec.tobytes())
names = ['Spruce', 'Fir', 'Maple', 'Birch', 'Oak']
variants = {s: [(z, c, 'SM_%s_%d_%d' % (s, z, c)) for z in range(4) for c in (0, 2)] for s in names}
for s in ('Spruce', 'Fir', 'Birch'):
    variants[s].append((0, 3, 'SM_%s_krummholz' % s))


def plant(seed):
    return trees.forest(H, HMIN, SP, SC, 'Northeast', TOP, 0.0, {'mrg': donor, 'sb': donor}, variants, names, seed,
                        max_trees=400000, lat=44.0)


recs, table, _, counts = plant(11)
out = np.frombuffer(recs, np.uint8).reshape(-1, trees.STRIDE)
x = out[:, 0:4].copy().view('<i4').ravel() / 1000.0
y = out[:, 4:8].copy().view('<i4').ravel() / 1000.0
z = out[:, 8:12].copy().view('<i4').ravel() / 1000.0 + HMIN
v = out[:, 18:20].copy().view('<u2').ravel()
tab = trees.table_entries(table)
sp = np.array([e[0].replace('DA_TreeSpecies_', '') for e in tab])[v]
assert len(out) > 300000 and set(counts) == set(names), counts

# few kinds of tree per 164 m square: the game makes an instanced component per square per kind (broadleaf: two)
broad = np.array([e[0].replace('DA_TreeSpecies_', '') in trees.BROADLEAF and e[2] != 2 for e in tab])
cells = (x // 163.84).astype(np.int64) * 100 + (y // 163.84).astype(np.int64)
pairs = np.unique(cells * 4096 + v)
per_square = (1 + broad[pairs % 4096]).sum() / len(np.unique(cells))
assert per_square < 12, per_square                                   # the game's own maps: ~22

# no maple, oak or birch near the top of the forest (past the summit rule's fade): the upper mountain is conifers
t = trees._relief(H, SP, SC, HMIN, x, y, z, TOP)
near_top = t > trees.SUMMIT_TO + trees.SUMMIT_FADE
assert near_top.sum() > 1000 and not np.isin(sp[near_top], ['Maple', 'Oak', 'Birch']).any(), \
    np.unique(sp[near_top], return_counts=True)
fade = (t > trees.SUMMIT_FROM) & (t < trees.SUMMIT_TO)                # broadleaf thin out on the way up, not at a line
assert 0 < np.isin(sp[fade], ['Maple', 'Oak', 'Birch']).mean() < np.isin(sp[t < trees.SUMMIT_FROM], ['Maple', 'Oak', 'Birch']).mean()

# as on the game's Northeast maps (data/tree_patterns.json): maple and oak on the low ground, spruce and fir most of
# the forest and more of it up high
low, mid = z < HMIN + 0.25 * (TOP - HMIN), (z > HMIN + 0.5 * (TOP - HMIN)) & (z < HMIN + 0.7 * (TOP - HMIN))
share = lambda sel, s: float((sp[sel] == s).mean())
assert share(low, 'Maple') > 3 * share(mid, 'Maple'), (share(low, 'Maple'), share(mid, 'Maple'))
assert share(mid, 'Spruce') + share(mid, 'Fir') > share(low, 'Spruce') + share(low, 'Fir')
assert (counts['Spruce'] + counts['Fir']) / len(out) > 0.6, counts

# the same seed, the same forest
assert plant(11)[0] == recs

print('trees: all checks passed (%.1f kinds per square, %d trees)' % (per_square, len(out)))
