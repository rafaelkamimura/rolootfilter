"""apply / revert / preview / status for a filter.toml against the RO client."""
import os, sys, json, shutil, tomllib, hashlib, subprocess
from . import grf as grfmod, sprite, iteminfo
from .rules import Rule, evaluate

FROZEN = bool(getattr(sys, 'frozen', False))
HERE = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', HERE), 'RoLootFilter') if FROZEN else HERE
CACHE = os.path.join(DATA_DIR, 'cache'); PREVIEW = os.path.join(DATA_DIR, 'preview')
STATE = os.path.join(CACHE, 'state.json')
LOG = print          # replaced by the GUI with a queue writer


def _p(*a):
    LOG(' '.join(str(x) for x in a))


def load_filter(path):
    cfg = tomllib.load(open(path, 'rb'))
    s = cfg.get('settings', {})
    s.setdefault('client', r'C:\Gravity\Ragnarok'); s.setdefault('glow_alpha', 200); s.setdefault('glow_scale', 1.9)
    s.setdefault('patch_iteminfo', False)
    rules = [Rule(r, i + 1) for i, r in enumerate(cfg.get('rule', []))]
    return s, rules


def _client_running():
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Ragexe.exe'], capture_output=True, text=True).stdout
        return 'Ragexe.exe' in out
    except Exception:
        return False


def _state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def _save_state(st):
    os.makedirs(CACHE, exist_ok=True); json.dump(st, open(STATE, 'w'), indent=1)


def _lub_paths(settings):
    live = os.path.join(settings['client'], 'System', 'iteminfo_new.lub')
    return live, os.path.join(CACHE, 'iteminfo_new.lub.pristine')


def ensure_pristine(settings, g):
    """Make sure cache/state.json describes a pristine GRF we can always return to.

    If the GRF currently carries our own append (header/size recorded under 'applied'), revert it first.
    If the GRF changed in some other way (patcher), the old snapshot is discarded and the current file
    becomes the new pristine baseline.
    """
    st = _state(); size = os.path.getsize(g.path)
    pr = st.get('pristine')
    if pr and g.table_intact_at(pr['tbl_off'], pr['tbl_csz']) and size >= pr['size']:
        if size != pr['size'] or g.header.hex() != pr['header']:
            g.restore(bytes.fromhex(pr['header']), pr['size'])
            g.close(); g.__init__(g.path)
            _p('reverted previous apply -> pristine GRF (%d bytes)' % pr['size'])
        return st
    if pr: _p('GRF changed externally (patch?); taking a fresh pristine snapshot')
    st = {'pristine': {'size': size, 'header': g.header.hex(), 'tbl_off': g.tbl_off, 'tbl_csz': g.tbl_csz}}
    # sprite originals cached earlier belong to the old GRF; drop them
    shutil.rmtree(os.path.join(CACHE, 'orig'), ignore_errors=True)
    _save_state(st); return st


def ensure_pristine_lub(settings):
    live, pristine = _lub_paths(settings); st = _state()
    h = hashlib.sha1(open(live, 'rb').read()).hexdigest()
    if st.get('lub_applied_sha1') == h and os.path.exists(pristine):
        return pristine                     # live file is ours; pristine copy is the real one
    shutil.copyfile(live, pristine)        # live file is Gravity's (fresh or patched) -> snapshot it
    st.pop('lub_applied_sha1', None); _save_state(st)
    return pristine


def plan(settings, rules, tbl):
    return evaluate(rules, tbl)


def apply(filter_path, dry=False, preview=True):
    settings, rules = load_filter(filter_path)
    if _client_running(): raise SystemExit('Ragexe.exe is running; close the client first')
    os.makedirs(CACHE, exist_ok=True)
    pristine_lub = ensure_pristine_lub(settings)
    tbl = iteminfo.load_cached(pristine_lub, os.path.join(CACHE, 'iteminfo.json'))
    actions = plan(settings, rules, tbl)
    g = grfmod.Grf(os.path.join(settings['client'], 'data.grf'))
    try:
        ensure_pristine(settings, g)
        files = {}; built = []; missing = []; effect_edits = {}; preid = []
        orig_dir = os.path.join(CACHE, 'orig'); os.makedirs(orig_dir, exist_ok=True)
        if preview: os.makedirs(PREVIEW, exist_ok=True)
        for iid, act in sorted(actions.items()):
            e = tbl[iid]; names = [e['identifiedResourceName']]
            if act['unidentified'] and e.get('unidentifiedResourceName') not in names: names.append(e['unidentifiedResourceName'])
            if act['effect_id'] is not None: effect_edits[iid] = act['effect_id']
            if act['preidentify'] and e.get('unidentifiedResourceName') != e['identifiedResourceName']: preid.append(iid)
            for rn in names:
                ks = g.item_path(rn, '.spr'); ka = g.item_path(rn, '.act')
                if not (g.has(ks) and g.has(ka)): missing.append((iid, rn)); continue
                if ks in files: continue
                try:
                    spr = _cached(g, orig_dir, rn + '.spr', ks); actb = _cached(g, orig_dir, rn + '.act', ka)
                    nspr, nact, info = sprite.transform(spr, actb, size=act['size'], glow=act['glow'],
                                                         glow_alpha=settings['glow_alpha'], glow_scale=settings['glow_scale'], hide=act['hide'])
                except ValueError as ex:
                    missing.append((iid, rn + ' (%s)' % ex)); continue
                files[ks] = nspr; files[ka] = nact
                built.append((iid, e['identifiedDisplayName'], rn, act['rule'].name, act['size'], act['glow'], act['hide'], info.get('frames')))
                if preview:
                    W, H, img = sprite.render(nspr, nact); sprite.png_write(os.path.join(PREVIEW, rn + '.png'), W, H, img)
        for b in built: _p('  %-8d %-36s %-26s %-24s x%d glow=%s%s' % (b[0], b[1][:36], b[2][:26], b[3][:24], b[4], b[5], ' HIDE' if b[6] else ''))
        for m in missing: _p('  skipped %s: %s' % m)
        _p('%d items -> %d files; %d effect edits; %d pre-identified; %d skipped' % (len(built), len(files), len(effect_edits), len(preid), len(missing)))
        if dry: _p('dry run, nothing written'); return
        new_size = g.append_files(files) if files else os.path.getsize(g.path)
        st = _state(); st['applied'] = {'size': new_size, 'header': g.header.hex() if False else open(g.path, 'rb').read(46).hex(), 'files': len(files)}
        _save_state(st)
        _p('GRF: wrote %d files, size %d' % (len(files), new_size))
    finally:
        g.close()
    _verify(settings, files)
    if effect_edits or preid:
        if not settings['patch_iteminfo']:
            _p('NOTE: %d effect_id / %d preidentify edits ignored (set patch_iteminfo = true in [settings])' % (len(effect_edits), len(preid)))
        else:
            for iid, eff in effect_edits.items(): tbl[iid]['EffectID'] = eff
            for iid in preid:
                e = tbl[iid]
                for k in ('ResourceName', 'DisplayName', 'DescriptionName'):
                    if 'identified' + k in e: e['unidentified' + k] = e['identified' + k]
            lub = iteminfo.compile_lub(tbl); live, _ = _lub_paths(settings)
            tmp = live + '.tmp'; open(tmp, 'wb').write(lub)
            back = iteminfo.load_tbl(tmp)
            if back != tbl: os.remove(tmp); raise SystemExit('iteminfo round-trip mismatch; not installing')
            os.replace(tmp, live)
            st = _state(); st['lub_applied_sha1'] = hashlib.sha1(lub).hexdigest(); _save_state(st)
            _p('iteminfo_new.lub: installed with %d EffectID edits, %d items pre-identified (%d bytes)' % (len(effect_edits), len(preid), len(lub)))


def _cached(g, orig_dir, fname, key):
    p = os.path.join(orig_dir, fname)
    if os.path.exists(p): return open(p, 'rb').read()
    raw = g.read(key); open(p, 'wb').write(raw); return raw


def _verify(settings, files):
    g = grfmod.Grf(os.path.join(settings['client'], 'data.grf'))
    try:
        bad = [k for k, raw in files.items() if g.read(k) != raw]
    finally:
        g.close()
    if bad: raise SystemExit('VERIFY FAILED for %d files' % len(bad))
    _p('verify: %d/%d files read back identical' % (len(files), len(files)))


def revert(filter_path):
    settings, _ = load_filter(filter_path)
    if _client_running(): raise SystemExit('Ragexe.exe is running; close the client first')
    st = _state(); pr = st.get('pristine')
    g = grfmod.Grf(os.path.join(settings['client'], 'data.grf'))
    try:
        if pr and g.table_intact_at(pr['tbl_off'], pr['tbl_csz']):
            g.restore(bytes.fromhex(pr['header']), pr['size']); _p('GRF restored to %d bytes' % pr['size'])
        else: _p('no valid GRF snapshot; nothing to revert')
    finally:
        g.close()
    live, pristine = _lub_paths(settings)
    if st.get('lub_applied_sha1') and os.path.exists(pristine):
        shutil.copyfile(pristine, live); _p('iteminfo_new.lub restored')
    st.pop('applied', None); st.pop('lub_applied_sha1', None); _save_state(st)


def status_info(filter_path):
    settings, rules = load_filter(filter_path); st = _state()
    grf_path = os.path.join(settings['client'], 'data.grf')
    if not os.path.exists(grf_path):
        return {'client': settings['client'], 'rules': len(rules), 'grf': 'data.grf not found', 'size': 0, 'iteminfo': '-', 'running': _client_running()}
    size = os.path.getsize(grf_path); pr = st.get('pristine'); ap = st.get('applied')
    grf = 'APPLIED' if ap and size == ap['size'] else 'pristine' if pr and size == pr['size'] else 'unpatched' if not pr else 'changed'
    return {'client': settings['client'], 'rules': len(rules), 'grf': grf, 'size': size, 'pristine': pr['size'] if pr else None,
            'applied': ap['size'] if ap else None, 'iteminfo': 'patched' if st.get('lub_applied_sha1') else 'original', 'running': _client_running()}


def status(filter_path):
    i = status_info(filter_path)
    _p('client     :', i['client']); _p('rules      :', i['rules'])
    _p('GRF size   :', i['size'], '(pristine %s, applied %s)' % (i.get('pristine') or '-', i.get('applied') or '-'))
    _p('GRF state  :', i['grf']); _p('iteminfo   :', i['iteminfo']); _p('client run :', i['running'])


def search(filter_path, pattern):
    import re
    settings, _ = load_filter(filter_path)
    live, pristine = _lub_paths(settings); src = pristine if os.path.exists(pristine) else live
    tbl = iteminfo.load_cached(src, os.path.join(CACHE, 'iteminfo.json')); rx = re.compile(pattern, re.I)
    for iid in sorted(tbl):
        e = tbl[iid]
        if rx.search(e.get('identifiedDisplayName', '')) or rx.search(e.get('identifiedResourceName', '')):
            _p('%-8d %-40s %-30s effect=%s' % (iid, e.get('identifiedDisplayName', '')[:40], e.get('identifiedResourceName', '')[:30], e.get('EffectID')))
