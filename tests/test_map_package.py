"""Self-check that a map package holds only a map (install.Game.only_a_map): IoStore containers of the map folders yes;
the build menu's table (or any game asset outside the map folders), a .pak without its container, or a .pak holding
files of its own, no. Stand-in containers made from the game's own files; skipped without the game. Writes only to
temporary folders (one inside the game folder, for hard links). usage: python tests/test_map_package.py"""
import shutil
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skieo_creator import install, paths  # noqa: E402

found = install.find_game()
if not found or not found[0]:
    print('map package: skipped (Ski-E-O not found)')
    sys.exit(0)
sim = Path(found[0]) / 'SkiResortSimulator'
paks = sim / 'Content' / 'Paks'
work = Path(tempfile.mkdtemp(prefix='.skimap_test_', dir=sim))           # hard links: on the game's drive
tmp = Path(tempfile.mkdtemp(prefix='skieo_maptest_'))
EXTS = ('.pak', '.ucas', '.utoc')
try:
    for d in ('t', 'm'):
        (work / d).mkdir()
    ua, ue, so = install.extract_data_asset(paks, work / 't', 'DT_BuildingEconomy', 'building list')
    mua, mue, _ = install.extract_data_asset(paks, work / 'm', 'DA_LevelRegistry', 'map list')

    def container(folder, stem, files):
        """an IoStore container made from legacy assets {Content/...: bytes}, like a map's"""
        legacy = work / ('legacy_' + stem)
        for rel, data in files.items():
            p = legacy / 'SkiResortSimulator' / 'Content' / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        (legacy / 'scriptobjects.bin').write_bytes(so)
        folder.mkdir(parents=True, exist_ok=True)
        install.run_retoc(['to-zen', '--version', install.ENGINE, str(legacy), str(folder / (stem + '.utoc'))])
        return folder

    def with_files(pak, n):
        """a copy of an IoStore .pak whose index says it holds n files of its own"""
        b = bytearray(Path(pak).read_bytes())
        i = b.rfind(struct.pack('<I', 0x5A6F12E1))
        off = struct.unpack_from('<q', b, i + 8)[0]
        struct.pack_into('<i', b, off + 4 + struct.unpack_from('<i', b, off)[0], n)
        return bytes(b)

    g = install.Game(found[0])
    triple = ['ZZZ_MapOk_P' + e for e in EXTS]
    mapdir = container(tmp / 'map_ok', 'ZZZ_MapOk_P', {'Maps/Generated/Map_test_ok_real.uasset': mua,
                                                       'Maps/Generated/Map_test_ok_real.uexp': mue})
    g.only_a_map(dict(name='Ok', files=triple), mapdir)

    def not_a_map(files, folder, why):
        try:
            g.only_a_map(dict(name='Bad', files=files), folder)
            raise AssertionError('accepted: ' + why)
        except install.InstallError as e:
            assert 'not only a map' in str(e) and why in str(e), e
    bad = container(tmp / 'map_bad', 'ZZZ_MapBad_P', {'Data/DT_BuildingEconomy.uasset': ua,
                                                      'Data/DT_BuildingEconomy.uexp': ue})
    not_a_map(['ZZZ_MapBad_P' + e for e in EXTS], bad, 'DT_BuildingEconomy')
    not_a_map(['ZZZ_MapOk_P.pak'], mapdir, 'not a map container')
    (mapdir / 'ZZZ_MapOk_P.pak').write_bytes(with_files(mapdir / 'ZZZ_MapOk_P.pak', 1))
    not_a_map(triple, mapdir, 'not a map container')
finally:
    paths.remove_tree(work)                                 # (it holds hard links to the game's files)
    shutil.rmtree(tmp, ignore_errors=True)
print('map package: all checks passed')
