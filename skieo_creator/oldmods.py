"""What the Mod Library of versions 1.2 to 1.8 put into the game, taken out once (mods come from Z's Mod Loader now, and
its installer won't install over that UE4SS): its UE4SS where its marker says it put it there and nothing else uses it,
its Lua mods, its lift and building packs (only a version it shipped, by the hash of its .utoc) and the build menu pak
it merged them into (with its stamp). Never touches maps, the map list, Z's Mod Loader, files the Asset Pack Combiner
manages or anything else of the player's, and never follows a link out of the game folder. The game must be closed
(it holds UE4SS and the paks)."""
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import sys
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

MARKER = 'installed-by-skieo-map-creator.txt'           # in Binaries/Win64/ue4ss: the app put this UE4SS there
MANIFEST = 'installed-by-skieo-map-creator.json'        # in a Lua mod's folder: the app put the mod there
LUA = ('OofsCheatMenu', 'OofsAnarchy', 'OofsSpeed', 'SkiWeather')     # its Lua mods (SkiWeather: 1.2 to 1.4)
LIBS = ('shared', 'BPModLoaderMod', 'BPML_GenericFunctions')          # what it put in ue4ss/Mods with UE4SS
DWMAPI = {'93b9431a5a4f32c675d269c5da1c9b3ec6f88552ec20c282ab435f411e9271fb'}       # the UE4SS (3.0.1) it shipped
UE4SS_DLL = {'ce5e3c46a920cc00b2817ac61e438c9162830290379d0b5b9c4dfc2b29459290'}
PAKS = {                                                # its packs: the .utoc of every version it shipped
    'ZZZ_DoppelmayrR2Six_P': {'90381b3a5f937a9aa3f5f0a9f9c1493e705f68e97984131788f9ac83e0f727e1',
                              'c6525da119e9ae32dcb8c994ee9415ed7f8137aa163ead0229b3ee6b46c42b4a',
                              'fc92fe5bfb19a2cbb5b1d90592cd7b930a5c0987cbb1c1720b008ea87384850a'},
    'ZZZ_DoppelmayrR2Gondola_P': {'9a29bf49e236e901163865273aea1575b287cd75f6de81239c7e34018be437ba',
                                  'da9ba5946582d45f4229c0b3b185e20dc3d5db6853b161f70101f36d71436630',
                                  'f8501fdfd4e4f4216336527a1f0af366d781ec5ed28c086f059c31ca1f2dbf39'},
    'ZZZ_AlpineBuildings_P': {'0c0f8a2b13e00598ac3d7e8722131f24385e6d6bd9d835916356ab9df6cbe06e',
                              '286b99d361ae6e89979730f6387c315a8e788a0c437bb6ec25c0fc094b0433c4',
                              '2f8d1b5bed230fecdf22f09445dd6f1c1d6e03d8f69e0c5b694a2dc8af56f9d5',
                              '669b8e2c88d13e102efaf82bcb6e5e4ad1d3149537e37e8fdd42d6810ef3eed1',
                              '87ed5d2f65370a54434ccf2fe9ad247f19b29635da565c9f9af186f81143cdd7',
                              'e62756b9260419901cccc1db901983cf12e5ce1b43e05ccf4e55c24309f03ae3'},
}
STOCK, STAMP = 'ZZZ_LiftStock_9_P', 'skieo_lift_stock.json'     # the merged build menu and snow caps (made on the PC)
PAK_EXTS = ('.pak', '.ucas', '.utoc')                   # the .pak first: without it the game doesn't load the rest
RMTREE_ERRORS = 'onexc' if sys.version_info >= (3, 12) else 'onerror'


def _sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _is_link(p):
    """a symbolic link or a junction: only the link itself is ever removed, never what it points at"""
    try:
        return p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
    except OSError:
        return False


def _drop_link(p):
    try:
        os.rmdir(p)                                     # a link to a folder, or a junction
    except OSError:
        os.unlink(p)


def _writable(func, path, *_):
    """shutil.rmtree's error handler: a read-only file is made writable and tried again"""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _drop_file(p):
    try:
        p.unlink()
    except PermissionError:                             # (read-only)
        os.chmod(p, stat.S_IWRITE)
        p.unlink()


def _unlink(files, gone, left):
    """remove these files in order, stopping at one that won't go"""
    for p in files:
        try:
            if _is_link(p):
                _drop_link(p)
            else:
                _drop_file(p)
            gone.append(p)
        except FileNotFoundError:
            pass
        except OSError as e:
            left.append('%s (%s)' % (p, e))
            return


def _rmtree(d, gone, left, last=None):
    """folder d and all in it; the file `last` in it goes after everything else (a marker stays till the rest is gone)"""
    try:
        if _is_link(d):
            _drop_link(d)
            gone.append(d)
            return
        if not d.is_dir():
            return
    except OSError as e:
        left.append('%s (%s)' % (d, e))
        return
    failed = []
    for c in d.iterdir():
        if last is not None and c.name == last:
            continue
        try:
            if _is_link(c):
                _drop_link(c)
            elif c.is_dir():
                shutil.rmtree(c, **{RMTREE_ERRORS: _writable})
            else:
                _drop_file(c)
        except OSError as e:
            failed.append('%s (%s)' % (c, e))
    if not failed:
        try:
            if last is not None and (d / last).exists():
                _drop_file(d / last)
            d.rmdir()
            gone.append(d)
            return
        except OSError as e:
            failed.append('%s (%s)' % (d, e))
    left.extend(failed)


def _loads_other_folders(ini):
    """UE4SS-settings.ini loads mods from more folders than ue4ss/Mods (as Z's Mod Loader sets it up)"""
    try:
        text = ini.read_bytes().decode('utf-8', 'replace')
    except OSError:
        return False
    return any(re.match(r'\s*[+-]?\s*ModsFolderPaths\s*=', line) for line in text.splitlines())


def _foreign(ue4ss, logic):
    """why a UE4SS with the app's marker can't just go, or None: ('taken', why) it is not the app's UE4SS any more
    (another loader took it over, or its files aren't the ones the app put there), ('used', why) other mods use it"""
    if any(ue4ss.glob('.skieo-loader*')) or (ue4ss / 'Mods' / 'SkiEOModsMenu').exists():
        return 'taken', "Z's Mod Loader uses it"
    for p, known in ((ue4ss.parent / 'dwmapi.dll', DWMAPI), (ue4ss / 'UE4SS.dll', UE4SS_DLL)):
        if p.is_file() and _sha(p) not in known:
            return 'taken', p.name + ' is not the one the Map Creator installed'
    if _loads_other_folders(ue4ss / 'UE4SS-settings.ini'):
        return 'used', 'it loads mods from other folders too (ModsFolderPaths)'
    ours = {n.lower() for n in LUA + LIBS}
    mods = ue4ss / 'Mods'
    other = sorted(d.name for d in mods.iterdir() if d.is_dir() and d.name.lower() not in ours) if mods.is_dir() else []
    if other:
        return 'used', 'other mods use it: ' + ', '.join(other)
    if logic.is_dir() and any(logic.iterdir()):
        return 'used', 'Blueprint mods in Content\\Paks\\LogicMods use it'
    return None


def _drop_lines(txt, names, gone, left):
    """mods.txt without the lines of these mods"""
    try:
        text = txt.read_bytes().decode('utf-8-sig')          # (its own line ends kept)
    except FileNotFoundError:
        return
    except (OSError, UnicodeDecodeError) as e:
        left.append('%s (%s)' % (txt, e))
        return
    low = {n.lower() for n in names}
    lines = text.splitlines(keepends=True)
    keep = [x for x in lines if x.split(':')[0].strip().lower() not in low]
    if len(keep) != len(lines):
        try:
            paths.atomic_write(txt, ''.join(keep).encode('utf-8'))
            gone.append('%s: the lines of %s' % (txt, ', '.join(names)))
        except OSError as e:
            left.append('%s (%s)' % (txt, e))


def _lua_mods(ue4ss, gone, left, all_of_ours):
    """the app's Lua mods in ue4ss/Mods with their mods.txt lines: in the app's own UE4SS all of them, in another only
    those with the record the app kept in each"""
    mods = ue4ss / 'Mods'
    names = [n for n in LUA if (mods / n).is_dir() and (all_of_ours or (mods / n / MANIFEST).is_file())]
    for n in names:
        _rmtree(mods / n, gone, left)
    lines = LUA if all_of_ours else names               # (in its own UE4SS, every line of its mods is its own)
    if lines:
        _drop_lines(mods / 'mods.txt', lines, gone, left)


def _stamped(stamp):
    """the app's stamp of the build menu pak it merged: a JSON list, its format (1 to 3) first"""
    try:
        s = json.loads(stamp.read_bytes())
    except (OSError, ValueError):
        return False
    return isinstance(s, list) and bool(s) and s[0] in (1, 2, 3)


def remove(game_folder):
    """-> True when nothing of the old Mod Library is left (a UE4SS it handed over to the player aside)"""
    sim = Path(game_folder) / 'SkiResortSimulator'
    win = sim / 'Binaries' / 'Win64'
    ue4ss = win / 'ue4ss'
    mods = sim / 'Content' / 'Paks' / '~mods'
    gone, left = [], []
    if _is_link(ue4ss):
        log.info('old Mod Library: ue4ss is a link: left alone')
    elif (ue4ss / MARKER).is_file():
        f = _foreign(ue4ss, sim / 'Content' / 'Paks' / 'LogicMods')
        if f is None:                                    # all of it is the app's: UE4SS goes, its mods with it
            _unlink([win / 'dwmapi.dll'], gone, left)    # (first: without it the game doesn't load UE4SS)
            if not left:
                _rmtree(ue4ss, gone, left, last=MARKER)
        else:                                            # it stays, the player's now: only the app's mods go
            log.info('old Mod Library: UE4SS stays (%s); its own mods are removed', f[1])
            _lua_mods(ue4ss, gone, left, f[0] == 'used')
            if not left:
                _unlink([ue4ss / MARKER], gone, left)
    elif (ue4ss / 'Mods').is_dir():                      # the player's own UE4SS, or Z's
        _lua_mods(ue4ss, gone, left, False)
    for stem, versions in PAKS.items():                  # its packs: only a version it shipped; one the Asset Pack
        if (mods / (stem + '.pak.off')).exists():        # Combiner turned off is the combiner's to delete
            continue
        utoc = mods / (stem + '.utoc')
        if utoc.is_file() and not _is_link(utoc) and _sha(utoc) in versions:
            _unlink([mods / (stem + e) for e in PAK_EXTS], gone, left)
    if not (mods / (STOCK + '.pak.off')).exists() and _stamped(mods / STAMP):     # (the stamp last)
        _unlink([mods / (STOCK + e) for e in PAK_EXTS] + [mods / STAMP], gone, left)
    for p in gone:
        log.info('old Mod Library: removed %s', p)
    for p in left:
        log.warning('old Mod Library: could not remove %s (tried again at the next start)', p)
    return not left
