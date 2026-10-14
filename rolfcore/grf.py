"""GRF 0x300 ("Event Horizon") reader + append-only writer.

Only flag-1 (plain zlib) entries are extracted; that covers every modern item sprite.
Writes never touch existing bytes: new blobs and a rebuilt file table are appended and the
8-byte table pointer in the header is repointed, so a revert is header-restore + truncate.
"""
import struct, zlib, os

HEADER_LEN = 46
ITEM_FOLDER = ('data/sprite/아이템/'.replace('/', chr(92))).encode('cp949')

# ---------------- Gravity's GRF encryption (flags 2 = mixed, 4 = header-only) ----------------
# Blocks use a single keyless DES round (rAthena des.c), implemented in grfdes.py.
_SUBST = {0x00: 0x2B, 0x2B: 0x00, 0x6C: 0x80, 0x01: 0x68, 0x68: 0x01, 0x48: 0x77, 0x60: 0xFF,
          0x77: 0x48, 0xB9: 0xC0, 0xC0: 0xB9, 0xFE: 0xEB, 0xEB: 0xFE, 0x80: 0x6C, 0xFF: 0x60}


class _des:
    @staticmethod
    def decrypt(block):
        from .grfdes import gravity_decrypt_block
        return gravity_decrypt_block(block)


def _shuffle_dec(b):
    return bytes((b[3], b[4], b[6], b[0], b[1], b[2], b[5], _SUBST.get(b[7], b[7])))


def grf_decode_header(buf):
    d = _des; out = bytearray(buf); n = min(20, len(buf) // 8)
    for i in range(n): out[i * 8:i * 8 + 8] = d.decrypt(bytes(buf[i * 8:i * 8 + 8]))
    return bytes(out)


def grf_decode_full(buf, compressed_len):
    digits = len(str(compressed_len))
    cycle = 1 if digits < 3 else digits + 1 if digits < 5 else digits + 9 if digits < 7 else digits + 15
    d = _des; out = bytearray(buf); nblocks = len(buf) // 8
    for i in range(min(20, nblocks)): out[i * 8:i * 8 + 8] = d.decrypt(bytes(buf[i * 8:i * 8 + 8]))
    j = -1
    for i in range(20, nblocks):
        blk = bytes(buf[i * 8:i * 8 + 8])
        if i % cycle == 0: out[i * 8:i * 8 + 8] = d.decrypt(blk); continue
        j += 1
        if j % 7 == 0 and j != 0: out[i * 8:i * 8 + 8] = _shuffle_dec(blk)
    return bytes(out)


class Grf:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'r+b')
        self.header, self.tbl_off, self.t0, self.tbl_csz, self.entries = self._read_table()
        self.index = {e[0].lower(): e for e in self.entries}

    def close(self):
        self.f.close()

    def _read_table(self):
        f = self.f; f.seek(0); h = f.read(HEADER_LEN)
        if h[:13] != b'Event Horizon' or struct.unpack_from('<I', h, 42)[0] != 0x300:
            raise ValueError('not a GRF 0x300 file')
        tbl_off = struct.unpack_from('<Q', h, 30)[0]; count = struct.unpack_from('<I', h, 38)[0]
        f.seek(tbl_off + HEADER_LEN); t0, csz, usz = struct.unpack('<III', f.read(12))
        data = zlib.decompress(f.read(csz))
        if len(data) != usz: raise ValueError('table size mismatch')
        ents = []; p = 0
        while p < len(data):
            e = data.index(b'\0', p); name = data[p:e]; p = e + 1
            c, ca, r, fl, off = struct.unpack_from('<IIIBQ', data, p); p += 21
            ents.append([name, c, ca, r, fl, off])
        if len(ents) != count: raise ValueError('entry count mismatch')
        return h, tbl_off, t0, csz, ents

    @staticmethod
    def item_path(resource, ext):
        return (ITEM_FOLDER + (resource + ext).encode('cp949')).lower()

    def has(self, key): return key in self.index

    def read(self, key):
        e = self.index[key]; name, c, ca, r, fl, off = e
        if not fl & 1: raise ValueError('entry %r is not a file (flag %d)' % (name, fl))
        self.f.seek(off + HEADER_LEN); buf = self.f.read(ca)
        if fl & 2: buf = grf_decode_full(buf, c)
        elif fl & 4: buf = grf_decode_header(buf)
        raw = zlib.decompress(buf[:c])
        if len(raw) != r: raise ValueError('bad size for %r' % name)
        return raw

    def table_intact_at(self, tbl_off, csz):
        """True if a valid table header + zlib stream sits at tbl_off (used to validate a snapshot)."""
        try:
            self.f.seek(tbl_off + HEADER_LEN); t0, c, u = struct.unpack('<III', self.f.read(12))
            if c != csz: return False
            return len(zlib.decompress(self.f.read(c))) == u
        except Exception:
            return False

    def append_files(self, files):
        """files: {key(bytes): raw bytes}. Appends blobs + new table; returns new size."""
        size = os.path.getsize(self.path); f = self.f; f.seek(size); pos = size
        for key, raw in files.items():
            comp = zlib.compress(raw, 9); e = self.index[key]
            e[1] = e[2] = len(comp); e[3] = len(raw); e[4] = 1; e[5] = pos - HEADER_LEN
            f.write(comp); pos += len(comp)
        tdata = bytearray()
        for name, c, ca, r, fl, off in self.entries:
            tdata += name + b'\0' + struct.pack('<IIIBQ', c, ca, r, fl, off)
        tcomp = zlib.compress(bytes(tdata), 9); new_tbl = pos
        f.write(struct.pack('<III', self.t0, len(tcomp), len(tdata)) + tcomp)
        f.seek(30); f.write(struct.pack('<Q', new_tbl - HEADER_LEN)); f.flush()
        self.tbl_off = new_tbl - HEADER_LEN; self.tbl_csz = len(tcomp)
        return os.path.getsize(self.path)

    def restore(self, header, size):
        self.f.seek(0); self.f.write(header); self.f.truncate(size); self.f.flush()
