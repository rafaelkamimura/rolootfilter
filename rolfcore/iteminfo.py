"""iteminfo_new.lub: load (via lupa's Lua 5.1 VM after a 32->64-bit bytecode transcode) and rebuild."""
import struct, json, os

FIELD_ORDER = ['unidentifiedDisplayName', 'unidentifiedResourceName', 'unidentifiedDescriptionName',
               'identifiedDisplayName', 'identifiedResourceName', 'identifiedDescriptionName',
               'slotCount', 'ClassNum', 'costume', 'EffectID']


def transcode(d, src_sz, dst_sz):
    """Rewrite a Lua 5.1 chunk changing sizeof(size_t)."""
    p = 0; out = bytearray()
    def rd(n):
        nonlocal p; v = d[p:p + n]; p += n; return v
    hdr = bytearray(rd(12))
    if hdr[:4] != b'\x1bLua' or hdr[4] != 0x51 or hdr[8] != src_sz: raise ValueError('unexpected Lua header %r' % bytes(hdr))
    hdr[8] = dst_sz; out += hdr
    sf = '<I' if src_sz == 4 else '<Q'; df = '<I' if dst_sz == 4 else '<Q'
    def xstr():
        n = struct.unpack(sf, rd(src_sz))[0]; out.extend(struct.pack(df, n)); out.extend(rd(n))
    def func():
        xstr(); out.extend(rd(12))
        n = struct.unpack('<I', rd(4))[0]; out.extend(struct.pack('<I', n)); out.extend(rd(4 * n))
        n = struct.unpack('<I', rd(4))[0]; out.extend(struct.pack('<I', n))
        for _ in range(n):
            t = rd(1); out.extend(t)
            if t[0] == 1: out.extend(rd(1))
            elif t[0] == 3: out.extend(rd(8))
            elif t[0] == 4: xstr()
        n = struct.unpack('<I', rd(4))[0]; out.extend(struct.pack('<I', n))
        for _ in range(n): func()
        n = struct.unpack('<I', rd(4))[0]; out.extend(struct.pack('<I', n)); out.extend(rd(4 * n))
        n = struct.unpack('<I', rd(4))[0]; out.extend(struct.pack('<I', n))
        for _ in range(n): xstr(); out.extend(rd(8))
        n = struct.unpack('<I', rd(4))[0]; out.extend(struct.pack('<I', n))
        for _ in range(n): xstr()
    func()
    if p != len(d): raise ValueError('trailing bytes in chunk')
    return bytes(out)


def _runtime():
    import lupa.lua51 as L
    return L.LuaRuntime(encoding=None)


def load_tbl(path):
    """Execute the lub in a sandbox (every global call is a no-op) and return {id: {field: value}}."""
    bc = transcode(open(path, 'rb').read(), 4, 8); rt = _runtime()
    rt.execute(b'setmetatable(_G,{__index=function(_,k) return function() return true end end})')
    rt.eval(b'function(bc) local f=assert(loadstring(bc)); f() end')(bc)
    out = {}
    for k, v in rt.globals()[b'tbl'].items():
        e = {}
        for fk, fv in v.items():
            fk = fk.decode()
            if isinstance(fv, bytes): e[fk] = fv.decode('utf-8', 'replace')
            elif hasattr(fv, 'items'): e[fk] = [x.decode('utf-8', 'replace') if isinstance(x, bytes) else x for x in fv.values()]
            else: e[fk] = fv
        out[int(k)] = e
    return out


def load_cached(lub_path, cache_path):
    """JSON cache keyed on the lub's mtime+size."""
    st = os.stat(lub_path); stamp = '%d:%d' % (st.st_mtime_ns, st.st_size)
    if os.path.exists(cache_path):
        c = json.load(open(cache_path, encoding='utf-8'))
        if c.get('stamp') == stamp: return {int(k): v for k, v in c['tbl'].items()}
    tbl = load_tbl(lub_path)
    json.dump({'stamp': stamp, 'tbl': tbl}, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)
    return tbl


# ---------------- rebuild ----------------
def _lua_str(s):
    b = s.encode('utf-8'); out = bytearray(b'"')
    for ch in b:
        if ch == 0x22: out += b'\\"'
        elif ch == 0x5c: out += b'\\\\'
        elif ch == 0x0a: out += b'\\n'
        elif ch == 0x0d: out += b'\\r'
        elif ch < 0x20: out += b'\\%03d' % ch
        else: out.append(ch)
    return bytes(out + b'"')


def _lua_val(v):
    if isinstance(v, bool): return b'true' if v else b'false'
    if isinstance(v, (int, float)): return str(int(v) if float(v).is_integer() else v).encode()
    if isinstance(v, str): return _lua_str(v)
    if isinstance(v, list): return b'{ ' + b', '.join(_lua_val(x) for x in v) + b' }'
    raise TypeError(v)


def gen_source(tbl):
    out = bytearray(b'tbl = {\n')
    for k in sorted(tbl, key=int):
        e = tbl[k]; out += b'\t[%d] = {\n' % int(k)
        for fk in FIELD_ORDER + [x for x in e if x not in FIELD_ORDER]:
            if fk in e: out += b'\t\t' + fk.encode() + b' = ' + _lua_val(e[fk]) + b',\n'
        out += b'\t},\n'
    return bytes(out + b'}\n')


def _strip_debug(bc):
    p = 12; d = bc
    def u32():
        nonlocal p; v = struct.unpack_from('<I', d, p)[0]; p += 4; return v
    out = bytearray(d[:12])
    n = u32(); out += struct.pack('<I', 2) + b'=\0'; p += n
    out += d[p:p + 12]; p += 12
    n = u32(); out += struct.pack('<I', n) + d[p:p + 4 * n]; p += 4 * n
    n = u32(); out += struct.pack('<I', n)
    for _ in range(n):
        t = d[p]; out.append(t); p += 1
        if t == 1: out.append(d[p]); p += 1
        elif t == 3: out += d[p:p + 8]; p += 8
        elif t == 4:
            l = u32(); out += struct.pack('<I', l) + d[p:p + l]; p += l
    n = u32()
    if n: raise ValueError('nested functions not supported')
    out += struct.pack('<I', 0) + struct.pack('<III', 0, 0, 0)
    return bytes(out)


def compile_lub(tbl):
    """tbl -> 32-bit Lua 5.1 bytecode identical in layout to Gravity's iteminfo_new.lub."""
    rt = _runtime()
    f = rt.eval(b'function(s) local fn, err = loadstring(s, "=iteminfo"); assert(fn, err); return string.dump(fn) end')
    return _strip_debug(transcode(f(gen_source(tbl)), 8, 4))
