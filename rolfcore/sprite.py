"""SPR v2.1 / ACT v2.5 parsing, transforms (scale, glow halo, hide) and a PNG renderer."""
import struct, zlib, math, colorsys


# ---------------- SPR ----------------
def rle_decode(buf, n):
    out = bytearray(); i = 0
    while i < len(buf):
        b = buf[i]; i += 1
        if b == 0:
            cnt = buf[i]; i += 1; out += b'\0' * (cnt if cnt else 1)
        else:
            out.append(b)
    if len(out) != n: raise ValueError('RLE length %d != %d' % (len(out), n))
    return bytes(out)


def rle_encode(px):
    out = bytearray(); i = 0; n = len(px)
    while i < n:
        if px[i] == 0:
            j = i
            while j < n and px[j] == 0 and j - i < 255: j += 1
            out += bytes([0, j - i]); i = j
        else:
            out.append(px[i]); i += 1
    return bytes(out)


def spr_parse(d):
    if d[:2] != b'SP' or d[2:4] != b'\x01\x02': raise ValueError('only SPR v2.1 supported, got %r' % d[:4])
    npal, nrgba = struct.unpack_from('<HH', d, 4); p = 8; pal = []; rgba = []
    for _ in range(npal):
        w, h, sz = struct.unpack_from('<HHH', d, p); p += 6
        pal.append((w, h, rle_decode(d[p:p + sz], w * h))); p += sz
    for _ in range(nrgba):
        w, h = struct.unpack_from('<HH', d, p); p += 4
        rgba.append((w, h, d[p:p + w * h * 4])); p += w * h * 4
    palette = d[p:]
    if len(palette) != 1024: raise ValueError('palette size %d' % len(palette))
    return pal, rgba, palette


def spr_write(pal, rgba, palette):
    out = bytearray(b'SP\x01\x02') + struct.pack('<HH', len(pal), len(rgba))
    for w, h, px in pal:
        enc = rle_encode(px)
        if len(enc) >= 65536: raise ValueError('frame too large for SPR v2.1 RLE (%d bytes)' % len(enc))
        out += struct.pack('<HHH', w, h, len(enc)) + enc
    for w, h, px in rgba:
        out += struct.pack('<HH', w, h) + px
    return bytes(out + palette)


def upscale(px, w, h, bpp, k):
    out = bytearray()
    for y in range(h):
        row = bytearray()
        for x in range(w): row += px[(y * w + x) * bpp:(y * w + x + 1) * bpp] * k
        out += row * k
    return bytes(out)


def dominant_color(pal, palette):
    r = g = b = n = 0.0
    for w, h, px in pal:
        for idx in px:
            if idx == 0: continue
            R, G, B = palette[idx * 4], palette[idx * 4 + 1], palette[idx * 4 + 2]
            wgt = 0.2 + colorsys.rgb_to_hsv(R / 255, G / 255, B / 255)[1]
            r += R * wgt; g += G * wgt; b += B * wgt; n += wgt
    if not n: return (255, 255, 255)
    hsv = colorsys.rgb_to_hsv(r / n / 255, g / n / 255, b / n / 255)
    s = max(hsv[1], 0.55) if hsv[1] > 0.12 else hsv[1]
    R, G, B = colorsys.hsv_to_rgb(hsv[0], s, 1.0)
    return (int(R * 255), int(G * 255), int(B * 255))


def make_glow(w, h, color, alpha):
    """ABGR radial halo: full alpha out to ~45% radius, then fades to the edge."""
    R, G, B = color; out = bytearray(); cx, cy = w / 2, h / 2
    for y in range(h):
        for x in range(w):
            d = math.hypot((x + .5 - cx) / cx, (y + .5 - cy) / cy)
            a = 0 if d >= 1 else int(alpha * min(1.0, (1 - d) / 0.55) ** 1.3)
            out += bytes((a, B, G, R))
    return bytes(out)


# ---------------- ACT ----------------
def act_parse(d):
    """Reads ACT 2.0 .. 2.5 into one structure (layers normalised to the v2.5 11-field layout)."""
    if d[:2] != b'AC' or d[3] != 2 or d[2] > 5: raise ValueError('unsupported ACT version %r' % d[:4])
    v = 20 + d[2]
    nanim = struct.unpack_from('<H', d, 4)[0]; p = 16; anims = []
    for _ in range(nanim):
        nfr = struct.unpack_from('<I', d, p)[0]; p += 4; frames = []
        for _ in range(nfr):
            rng = d[p:p + 32]; p += 32
            nl = struct.unpack_from('<I', d, p)[0]; p += 4; layers = []
            for _ in range(nl):
                x, y, idx, mir = struct.unpack_from('<iiii', d, p); p += 16
                color = struct.unpack_from('<I', d, p)[0]; p += 4
                sx = struct.unpack_from('<f', d, p)[0]; p += 4
                if v >= 24: sy = struct.unpack_from('<f', d, p)[0]; p += 4
                else: sy = sx
                rot, st = struct.unpack_from('<ii', d, p); p += 8
                if v >= 25: w, h = struct.unpack_from('<ii', d, p); p += 8
                else: w = h = 0
                layers.append([x, y, idx, mir, color, sx, sy, rot, st, w, h])
            ev = struct.unpack_from('<i', d, p)[0]; p += 4
            anchors = []
            if v >= 23:
                na = struct.unpack_from('<I', d, p)[0]; p += 4
                anchors = [d[p + 16 * i:p + 16 * (i + 1)] for i in range(na)]; p += 16 * na
            frames.append({'range': rng, 'layers': layers, 'event': ev, 'anchors': anchors})
        anims.append(frames)
    nev = struct.unpack_from('<I', d, p)[0]; p += 4
    events = [d[p + 40 * i:p + 40 * (i + 1)] for i in range(nev)]; p += 40 * nev
    if v >= 22: intervals = list(struct.unpack_from('<%df' % nanim, d, p)); p += 4 * nanim
    else: intervals = [4.0] * nanim
    if p != len(d): raise ValueError('ACT trailing bytes (v%d)' % v)
    return {'anims': anims, 'events': events, 'intervals': intervals, 'hdr': d[6:16], 'version': v}


def act_write(a):
    out = bytearray(b'AC\x05\x02') + struct.pack('<H', len(a['anims'])) + a['hdr']
    for frames in a['anims']:
        out += struct.pack('<I', len(frames))
        for fr in frames:
            out += fr['range'] + struct.pack('<I', len(fr['layers']))
            for l in fr['layers']: out += struct.pack('<iiiiIffiiii', *l)
            out += struct.pack('<i', fr['event']) + struct.pack('<I', len(fr['anchors'])) + b''.join(fr['anchors'])
    out += struct.pack('<I', len(a['events'])) + b''.join(a['events'])
    out += struct.pack('<%df' % len(a['intervals']), *a['intervals'])
    return bytes(out)


# ---------------- transforms ----------------
def hex_color(s):
    s = s.lstrip('#'); return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def transform(spr, act, size=1, glow=None, glow_alpha=200, glow_scale=1.9, hide=False):
    """glow: None | 'auto' | '#rrggbb'. Returns (spr_bytes, act_bytes, info)."""
    pal, rgba, palette = spr_parse(spr); a = act_parse(act)
    info = {'frames': [(w, h) for w, h, _ in pal]}
    if hide:
        pal = [(1, 1, b'\0') for _ in pal]; rgba = [(1, 1, b'\0\0\0\0') for _ in rgba]
        for frames in a['anims']:
            for fr in frames:
                for l in fr['layers']: l[9] = l[10] = 1
        return spr_write(pal, rgba, palette), act_write(a), info
    k = max(1, int(size))
    big_pal = [(w * k, h * k, upscale(px, w, h, 1, k)) for w, h, px in pal]
    big_rgba = [(w * k, h * k, upscale(px, w, h, 4, k)) for w, h, px in rgba]
    glow_index = None
    if glow and glow != 'none' and big_pal:
        w0 = max(w for w, h, _ in big_pal); h0 = max(h for w, h, _ in big_pal)
        gw = int(w0 * glow_scale) | 1; gh = int(h0 * glow_scale) | 1
        color = dominant_color(pal, palette) if glow == 'auto' else hex_color(glow)
        big_rgba.append((gw, gh, make_glow(gw, gh, color, glow_alpha))); glow_index = len(big_rgba) - 1
        info['glow'] = (gw, gh, color)
    for frames in a['anims']:
        for fr in frames:
            new = []
            for l in fr['layers']:
                l = list(l); l[0] *= k; l[1] *= k
                if l[8] == 0 and 0 <= l[2] < len(big_pal): l[9], l[10] = big_pal[l[2]][:2]
                elif l[8] == 1 and 0 <= l[2] < len(big_rgba): l[9], l[10] = big_rgba[l[2]][:2]
                new.append(l)
            if glow_index is not None and new:
                b = new[0]; gw, gh = big_rgba[glow_index][:2]
                # lift the halo so its bottom edge meets the item's bottom edge: ground drops sit on the
                # terrain plane and anything drawn below it is clipped by the depth test (a cut-off disc)
                lift = max(0, (gh - b[10]) // 2)
                new.insert(0, [b[0], b[1] - lift, glow_index, 0, 0xFFFFFFFF, 1.0, 1.0, 0, 1, gw, gh])
            fr['layers'] = new
    return spr_write(big_pal, big_rgba, palette), act_write(a), info


# ---------------- preview ----------------
def png_write(path, w, h, rgb):
    raw = b''.join(b'\0' + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    with open(path, 'wb') as fh:
        fh.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def render(spr, act, bg=(70, 110, 50), pad=6):
    """Composite animation 0 / frame 0 onto a flat background; returns (w, h, rgb bytes)."""
    pal, rgba, palette = spr_parse(spr); a = act_parse(act)
    layers = a['anims'][0][0]['layers'] if a['anims'] and a['anims'][0] else []
    def dims(l): return (pal if l[8] == 0 else rgba)[l[2]][:2]
    if not layers: return 1, 1, bytes(bg)
    xs = [l[0] - dims(l)[0] // 2 for l in layers] + [l[0] + dims(l)[0] // 2 for l in layers]
    ys = [l[1] - dims(l)[1] // 2 for l in layers] + [l[1] + dims(l)[1] // 2 for l in layers]
    x0, y0 = min(xs) - pad, min(ys) - pad; W, H = max(xs) - x0 + pad, max(ys) - y0 + pad
    img = bytearray(bytes(bg) * (W * H))
    for l in layers:
        w, h = dims(l); ox, oy = l[0] - w // 2 - x0, l[1] - h // 2 - y0
        for y in range(h):
            for x in range(w):
                if l[8] == 0:
                    idx = pal[l[2]][2][y * w + x]
                    if idx == 0: continue
                    col = palette[idx * 4:idx * 4 + 3]; al = 255
                else:
                    A, B, G, R = rgba[l[2]][2][(y * w + x) * 4:(y * w + x) * 4 + 4]; col = (R, G, B); al = A
                    if not al: continue
                o = ((oy + y) * W + ox + x) * 3
                for c in range(3): img[o + c] = (img[o + c] * (255 - al) + col[c] * al) // 255
    return W, H, bytes(img)
