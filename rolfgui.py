"""RO Loot Filter — desktop manager (customtkinter). Works from source and as a PyInstaller exe.

  python rolfgui.py [filter.toml]
"""
import os, sys, re, threading, tomllib, queue, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image
from rolfcore import engine, iteminfo, sprite, rules as rulesmod, tomlout, __version__
from rolfcore import grf as grfmod

FROZEN = engine.FROZEN; HERE = engine.HERE
BUNDLE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
ACCENT = '#f0a830'; ACCENT_DIM = '#8a5f1a'; BG0 = '#121417'; BG1 = '#1a1d22'; BG2 = '#23272e'; FG_DIM = '#8b93a1'
GLOW_SWATCH = {'auto': '#9bd', 'none': '#555'}
DEFAULT_CLIENTS = [r'C:\Gravity\Ragnarok', r'C:\Program Files (x86)\Gravity\Ragnarok', r'D:\Gravity\Ragnarok']

ctk.set_appearance_mode('dark'); ctk.set_default_color_theme('dark-blue')


def resolve_filter():
    """filter.toml next to the exe/script, else in AppData, else a copy of the bundled default."""
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith('.toml'): return os.path.abspath(sys.argv[1])
    local = os.path.join(HERE, 'filter.toml')
    if os.path.exists(local) and os.access(HERE, os.W_OK): return local
    os.makedirs(engine.DATA_DIR, exist_ok=True); appdata = os.path.join(engine.DATA_DIR, 'filter.toml')
    if not os.path.exists(appdata):
        src = local if os.path.exists(local) else os.path.join(BUNDLE, 'filter.toml')
        if os.path.exists(src): shutil.copyfile(src, appdata)
        else: open(appdata, 'w', encoding='utf-8').write(tomlout.dumps({'client': DEFAULT_CLIENTS[0]}, []))
    return appdata


FILTER = resolve_filter()


class ItemSource:
    """Reads original sprites (cache/orig first, then the GRF) and renders previews."""
    def __init__(self, settings):
        self.settings = settings; self.g = None; self.orig = os.path.join(engine.CACHE, 'orig')

    def grf(self):
        if self.g is None: self.g = grfmod.Grf(os.path.join(self.settings['client'], 'data.grf'))
        return self.g

    def close(self):
        if self.g: self.g.close(); self.g = None

    def original(self, rn, ext):
        p = os.path.join(self.orig, rn + ext)
        if os.path.exists(p): return open(p, 'rb').read()
        g = self.grf(); key = g.item_path(rn, ext)
        return g.read(key) if g.has(key) else None

    def render(self, rn, action=None, settings=None):
        spr = self.original(rn, '.spr'); act = self.original(rn, '.act')
        if spr is None or act is None: return None
        if action:
            spr, act, _ = sprite.transform(spr, act, size=action.get('size', 1), glow=action.get('glow'),
                                           glow_alpha=settings['glow_alpha'], glow_scale=settings['glow_scale'], hide=action.get('hide', False))
        W, H, rgb = sprite.render(spr, act, bg=(38, 48, 32))
        return Image.frombytes('RGB', (W, H), rgb)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('RO Loot Filter v' + __version__); self.geometry('1380x900'); self.minsize(1100, 720); self.configure(fg_color=BG0)
        ico = os.path.join(BUNDLE, 'assets', 'rolf.ico')
        if os.path.exists(ico):
            try: self.iconbitmap(ico)
            except Exception: pass
        self.settings, self.rules = self._load(); self.sel = None; self.dirty = False; self._loading = False
        self.src = ItemSource(self.settings); self.tbl = None; self.q = queue.Queue(); self.busy = False
        self._build(); self._refresh_rules(); self.after(100, self._load_items_async); self.after(200, self._pump)
        self.protocol('WM_DELETE_WINDOW', self._close)

    # ---------- data ----------
    def _load(self):
        cfg = tomllib.load(open(FILTER, 'rb'))
        s = cfg.get('settings', {}); s.setdefault('glow_alpha', 200); s.setdefault('glow_scale', 1.9); s.setdefault('patch_iteminfo', True)
        if not s.get('client') or not os.path.exists(os.path.join(s.get('client', ''), 'data.grf')):
            for c in DEFAULT_CLIENTS:
                if os.path.exists(os.path.join(c, 'data.grf')): s['client'] = c; break
            else: s.setdefault('client', DEFAULT_CLIENTS[0])
        return s, [dict(r) for r in cfg.get('rule', [])]

    def _save(self):
        open(FILTER, 'w', encoding='utf-8').write(tomlout.dumps(self.settings, self.rules)); self.dirty = False
        self._log('saved %s' % FILTER); self._set_title()

    def _set_title(self):
        self.title('RO Loot Filter v' + __version__ + (' •' if self.dirty else ''))

    def _load_items_async(self):
        def work():
            try:
                live, pristine = engine._lub_paths(self.settings); src = pristine if os.path.exists(pristine) else live
                if not os.path.exists(src): self.q.put(('log', 'iteminfo_new.lub not found under %s' % self.settings['client'])); return
                os.makedirs(engine.CACHE, exist_ok=True)
                self.q.put(('tbl', iteminfo.load_cached(src, os.path.join(engine.CACHE, 'iteminfo.json'))))
            except Exception as ex:
                self.q.put(('log', 'iteminfo load failed: %s' % ex))
        threading.Thread(target=work, daemon=True).start()

    # ---------- layout ----------
    def _build(self):
        self.grid_columnconfigure(0, weight=0); self.grid_columnconfigure(1, weight=1); self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=56); top.grid(row=0, column=0, columnspan=3, sticky='ew')
        ctk.CTkLabel(top, text='RO LOOT FILTER', font=('Segoe UI', 20, 'bold'), text_color=ACCENT).pack(side='left', padx=(18, 6), pady=12)
        ctk.CTkLabel(top, text='v' + __version__, text_color=FG_DIM, font=('Consolas', 11)).pack(side='left', padx=(0, 12))
        self.status_lbl = ctk.CTkLabel(top, text='', text_color=FG_DIM, font=('Consolas', 12)); self.status_lbl.pack(side='left', padx=10)
        for txt, cmd, col in (('Revert', lambda: self._run('revert'), BG2), ('Dry run', lambda: self._run('dry'), BG2), ('APPLY', lambda: self._run('apply'), ACCENT)):
            ctk.CTkButton(top, text=txt, width=96, command=cmd, fg_color=col, hover_color=ACCENT_DIM if col == ACCENT else '#2f343c',
                          text_color='#111' if col == ACCENT else '#ddd', font=('Segoe UI', 13, 'bold' if col == ACCENT else 'normal')).pack(side='right', padx=6, pady=10)
        ctk.CTkButton(top, text='Save', width=80, command=self._save, fg_color=BG2, hover_color='#2f343c').pack(side='right', padx=6)
        # client folder row
        crow = ctk.CTkFrame(self, fg_color=BG0, corner_radius=0); crow.grid(row=1, column=0, columnspan=3, sticky='ew', padx=12, pady=(8, 0))
        ctk.CTkLabel(crow, text='Client folder', text_color=FG_DIM).pack(side='left', padx=(6, 8))
        self.client_entry = ctk.CTkEntry(crow, fg_color=BG2, border_width=0, width=420); self.client_entry.pack(side='left')
        self.client_entry.insert(0, self.settings['client']); self.client_entry.bind('<Return>', lambda _e: self._set_client(self.client_entry.get()))
        ctk.CTkButton(crow, text='Browse…', width=90, fg_color=BG2, hover_color='#2f343c', command=self._browse_client).pack(side='left', padx=8)
        ctk.CTkLabel(crow, text='filter: ' + FILTER, text_color=FG_DIM, font=('Consolas', 11)).pack(side='right', padx=6)

        left = ctk.CTkFrame(self, fg_color=BG1, corner_radius=12, width=330); left.grid(row=2, column=0, sticky='nsw', padx=(12, 6), pady=10)
        left.grid_propagate(False); left.grid_rowconfigure(1, weight=1); left.grid_columnconfigure(0, weight=1)
        hdr = ctk.CTkFrame(left, fg_color='transparent'); hdr.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 4))
        ctk.CTkLabel(hdr, text='RULES', font=('Segoe UI', 13, 'bold'), text_color=FG_DIM).pack(side='left')
        ctk.CTkButton(hdr, text='+ new', width=64, height=26, command=self._add_rule, fg_color=BG2, hover_color='#2f343c').pack(side='right')
        self.rule_list = ctk.CTkScrollableFrame(left, fg_color='transparent'); self.rule_list.grid(row=1, column=0, sticky='nsew', padx=4)
        self.rule_list.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(left, text='first match wins · reorder with ▲▼', text_color=FG_DIM, font=('Segoe UI', 11)).grid(row=2, column=0, pady=(2, 8))

        mid = ctk.CTkFrame(self, fg_color=BG1, corner_radius=12); mid.grid(row=2, column=1, sticky='nsew', padx=6, pady=10)
        mid.grid_columnconfigure(1, weight=1); mid.grid_rowconfigure(20, weight=1)
        self.ed = {}; r = 0
        ctk.CTkLabel(mid, text='RULE', font=('Segoe UI', 13, 'bold'), text_color=FG_DIM).grid(row=r, column=0, sticky='w', padx=14, pady=(12, 2)); r += 1
        self._field(mid, r, 'name', 'Name'); r += 1
        ctk.CTkLabel(mid, text='MATCH  (all given criteria must match)', font=('Segoe UI', 12, 'bold'), text_color=FG_DIM).grid(row=r, column=0, columnspan=2, sticky='w', padx=14, pady=(14, 2)); r += 1
        self._field(mid, r, 'ids', 'Item IDs', 'e.g. 909, 1000636-1000643'); r += 1
        self._field(mid, r, 'resource', 'Resource regex', 'e.g. ^Etel_'); r += 1
        self._field(mid, r, 'name_match', 'Name regex', 'pt-BR display name, e.g. Runa'); r += 1
        self._field(mid, r, 'description', 'Description regex'); r += 1
        row = ctk.CTkFrame(mid, fg_color='transparent'); row.grid(row=r, column=0, columnspan=2, sticky='ew', padx=14); r += 1
        for key, lab in (('effect', 'has EffectID'), ('min_id', 'min id'), ('max_id', 'max id')):
            ctk.CTkLabel(row, text=lab, text_color=FG_DIM).pack(side='left', padx=(0, 4))
            e = ctk.CTkEntry(row, width=90, fg_color=BG2, border_width=0); e.pack(side='left', padx=(0, 14)); self.ed[key] = e
            e.bind('<KeyRelease>', lambda _e: self._mark())
        ctk.CTkLabel(mid, text='ACTION', font=('Segoe UI', 12, 'bold'), text_color=FG_DIM).grid(row=r, column=0, columnspan=2, sticky='w', padx=14, pady=(14, 2)); r += 1
        srow = ctk.CTkFrame(mid, fg_color='transparent'); srow.grid(row=r, column=0, columnspan=2, sticky='ew', padx=14); r += 1
        ctk.CTkLabel(srow, text='Size', text_color=FG_DIM, width=60, anchor='w').pack(side='left')
        self.size_lbl = ctk.CTkLabel(srow, text='x1', width=36, font=('Consolas', 13, 'bold'), text_color=ACCENT); self.size_lbl.pack(side='right')
        self.ed['size'] = ctk.CTkSlider(srow, from_=1, to=6, number_of_steps=5, command=self._size_changed, progress_color=ACCENT, button_color=ACCENT, button_hover_color='#ffc866')
        self.ed['size'].pack(side='left', fill='x', expand=True, padx=8)
        grow = ctk.CTkFrame(mid, fg_color='transparent'); grow.grid(row=r, column=0, columnspan=2, sticky='ew', padx=14, pady=4); r += 1
        ctk.CTkLabel(grow, text='Glow', text_color=FG_DIM, width=60, anchor='w').pack(side='left')
        self.ed['glow_mode'] = ctk.CTkSegmentedButton(grow, values=['none', 'auto', 'color'], command=lambda _v: (self._mark(), self._preview()),
                                                      selected_color=ACCENT, selected_hover_color='#ffc866', text_color='#ddd')
        self.ed['glow_mode'].pack(side='left', padx=8)
        self.ed['glow_color'] = ctk.CTkEntry(grow, width=90, placeholder_text='#ff8800', fg_color=BG2, border_width=0); self.ed['glow_color'].pack(side='left')
        self.ed['glow_color'].bind('<KeyRelease>', lambda _e: (self._mark(), self._preview()))
        for pair in ((('hide', 'Hide (invisible drop)'), ('continue', 'Continue to later rules')), (('unidentified', 'Also patch unidentified sprite'), ('enabled', 'Rule enabled')),
                     (('preidentify', 'Show unidentified drops as identified (iteminfo)'),)):
            trow = ctk.CTkFrame(mid, fg_color='transparent'); trow.grid(row=r, column=0, columnspan=2, sticky='ew', padx=14, pady=3); r += 1
            for key, lab in pair:
                sw = ctk.CTkSwitch(trow, text=lab, width=250, command=lambda: (self._mark(), self._preview()), progress_color=ACCENT); sw.pack(side='left', padx=(0, 16)); self.ed[key] = sw
        erow = ctk.CTkFrame(mid, fg_color='transparent'); erow.grid(row=r, column=0, columnspan=2, sticky='ew', padx=14, pady=4); r += 1
        ctk.CTkLabel(erow, text='EffectID to write into iteminfo (1870 = Aether Dust glow, needs server flag)', text_color=FG_DIM).pack(side='left')
        e = ctk.CTkEntry(erow, width=80, fg_color=BG2, border_width=0); e.pack(side='left', padx=8); self.ed['effect_id'] = e; e.bind('<KeyRelease>', lambda _e: self._mark())
        brow = ctk.CTkFrame(mid, fg_color='transparent'); brow.grid(row=r, column=0, columnspan=2, sticky='ew', padx=14, pady=(10, 4)); r += 1
        ctk.CTkButton(brow, text='Update rule', command=self._commit_rule, fg_color=ACCENT, hover_color=ACCENT_DIM, text_color='#111', font=('Segoe UI', 13, 'bold')).pack(side='left')
        ctk.CTkButton(brow, text='Delete', command=self._delete_rule, fg_color='#5a2a2a', hover_color='#7a3a3a', width=80).pack(side='left', padx=8)
        self.match_lbl = ctk.CTkLabel(brow, text='', text_color=FG_DIM); self.match_lbl.pack(side='right')
        ctk.CTkLabel(mid, text='MATCHES', font=('Segoe UI', 12, 'bold'), text_color=FG_DIM).grid(row=r, column=0, columnspan=2, sticky='w', padx=14, pady=(12, 2)); r += 1
        self.match_box = ctk.CTkTextbox(mid, fg_color=BG2, font=('Consolas', 12), height=150); self.match_box.grid(row=20, column=0, columnspan=2, sticky='nsew', padx=14, pady=(0, 12))

        right = ctk.CTkFrame(self, fg_color=BG1, corner_radius=12, width=360); right.grid(row=2, column=2, sticky='nse', padx=(6, 12), pady=10)
        right.grid_propagate(False); right.grid_columnconfigure(0, weight=1); right.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(right, text='PREVIEW', font=('Segoe UI', 13, 'bold'), text_color=FG_DIM).grid(row=0, column=0, sticky='w', padx=14, pady=(10, 2))
        self.prev_frame = ctk.CTkFrame(right, fg_color='#263020', corner_radius=10, height=230); self.prev_frame.grid(row=1, column=0, sticky='ew', padx=12); self.prev_frame.grid_propagate(False)
        self.prev_img = ctk.CTkLabel(self.prev_frame, text='select an item', text_color=FG_DIM); self.prev_img.place(relx=.5, rely=.5, anchor='center')
        self.prev_cap = ctk.CTkLabel(right, text='', text_color=FG_DIM, font=('Consolas', 11)); self.prev_cap.grid(row=2, column=0, sticky='w', padx=14)
        srch = ctk.CTkFrame(right, fg_color='transparent'); srch.grid(row=3, column=0, sticky='nsew', padx=12, pady=(8, 10)); srch.grid_rowconfigure(1, weight=1); srch.grid_columnconfigure(0, weight=1)
        self.search = ctk.CTkEntry(srch, placeholder_text='search items: name, resource or id  (Enter)', fg_color=BG2, border_width=0); self.search.grid(row=0, column=0, sticky='ew')
        self.search.bind('<Return>', lambda _e: self._do_search())
        self.results = ctk.CTkScrollableFrame(srch, fg_color='transparent'); self.results.grid(row=1, column=0, sticky='nsew', pady=(6, 0)); self.results.grid_columnconfigure(0, weight=1)
        self.log = ctk.CTkTextbox(self, fg_color=BG1, font=('Consolas', 11), height=150); self.log.grid(row=3, column=0, columnspan=3, sticky='ew', padx=12, pady=(0, 12))

    def _field(self, parent, r, key, label, ph=''):
        ctk.CTkLabel(parent, text=label, text_color=FG_DIM, anchor='w', width=130).grid(row=r, column=0, sticky='w', padx=14, pady=3)
        e = ctk.CTkEntry(parent, placeholder_text=ph, fg_color=BG2, border_width=0); e.grid(row=r, column=1, sticky='ew', padx=(0, 14), pady=3)
        e.bind('<KeyRelease>', lambda _e: self._mark()); self.ed[key] = e

    # ---------- client folder ----------
    def _browse_client(self):
        d = filedialog.askdirectory(title='Select the Ragnarok client folder (contains data.grf)', initialdir=self.settings['client'])
        if d: self.client_entry.delete(0, 'end'); self.client_entry.insert(0, os.path.normpath(d)); self._set_client(d)

    def _set_client(self, path):
        path = os.path.normpath(path.strip())
        if not os.path.exists(os.path.join(path, 'data.grf')): self._log('no data.grf in %s' % path); return
        self.settings['client'] = path; self.src.close(); self.src = ItemSource(self.settings); self.tbl = None
        self._mark(); self._save(); self._log('client folder: %s' % path); self._load_items_async()

    # ---------- rules list ----------
    def _refresh_rules(self):
        for w in self.rule_list.winfo_children(): w.destroy()
        for i, r in enumerate(self.rules):
            on = r.get('enabled', True); selected = (i == self.sel)
            row = ctk.CTkFrame(self.rule_list, fg_color=BG2 if selected else 'transparent', corner_radius=8); row.grid(row=i, column=0, columnspan=2, sticky='ew', pady=2, padx=2)
            row.grid_columnconfigure(1, weight=1)
            dot = ACCENT if r.get('hide') else GLOW_SWATCH.get(r.get('glow') or 'none', r.get('glow') or '#555')
            ctk.CTkLabel(row, text='■', text_color=dot if on else '#444', width=18).grid(row=0, column=0, padx=(6, 0))
            desc = ('HIDE' if r.get('hide') else 'x%s %s' % (r.get('size', 1), r.get('glow') or '')) + ('  ·  off' if not on else '')
            ctk.CTkButton(row, text='%s\n%s' % (r.get('name', 'rule'), desc), anchor='w', fg_color='transparent', hover_color='#2f343c',
                          text_color='#eee' if on else '#777', command=lambda i=i: self._select(i), font=('Segoe UI', 12)).grid(row=0, column=1, sticky='ew')
            ctk.CTkButton(row, text='▲', width=24, height=22, fg_color='transparent', hover_color='#2f343c', command=lambda i=i: self._move(i, -1)).grid(row=0, column=2)
            ctk.CTkButton(row, text='▼', width=24, height=22, fg_color='transparent', hover_color='#2f343c', command=lambda i=i: self._move(i, 1)).grid(row=0, column=3, padx=(0, 4))

    def _select(self, i):
        self.sel = i; r = self.rules[i]; self._refresh_rules(); self._loading = True
        for k in ('name', 'resource', 'name_match', 'description', 'effect', 'min_id', 'max_id', 'effect_id'):
            self.ed[k].delete(0, 'end'); self.ed[k].insert(0, '' if r.get(k) is None else str(r.get(k)))
        self.ed['ids'].delete(0, 'end'); self.ed['ids'].insert(0, ', '.join(str(x) for x in r.get('ids', [])))
        self.ed['size'].set(r.get('size', 1)); self._size_changed(r.get('size', 1))
        g = r.get('glow'); self.ed['glow_color'].delete(0, 'end')
        if not g or g == 'none': self.ed['glow_mode'].set('none')
        elif g == 'auto': self.ed['glow_mode'].set('auto')
        else: self.ed['glow_mode'].set('color'); self.ed['glow_color'].insert(0, g)
        for k in ('hide', 'continue', 'unidentified', 'preidentify'):
            (self.ed[k].select if r.get(k) else self.ed[k].deselect)()
        (self.ed['enabled'].select if r.get('enabled', True) else self.ed['enabled'].deselect)()
        self._loading = False; self.prev_rn = None; self._update_matches()

    def _size_changed(self, v):
        self.size_lbl.configure(text='x%d' % int(float(v))); self._mark(); self._preview()

    def _mark(self):
        if self._loading: return
        self.dirty = True; self._set_title()

    def _read_editor(self):
        r = {'name': self.ed['name'].get().strip() or 'rule'}
        ids = self.ed['ids'].get().strip()
        if ids:
            parts = [p.strip() for p in re.split(r'[,\s]+', ids) if p.strip()]
            r['ids'] = [int(p) if p.isdigit() else p for p in parts]
        for k in ('resource', 'name_match', 'description'):
            v = self.ed[k].get().strip()
            if v: re.compile(v); r[k] = v
        for k in ('effect', 'min_id', 'max_id', 'effect_id'):
            v = self.ed[k].get().strip()
            if v: r[k] = int(v)
        size = int(float(self.ed['size'].get()))
        if size > 1: r['size'] = size
        gm = self.ed['glow_mode'].get()
        if gm == 'auto': r['glow'] = 'auto'
        elif gm == 'color':
            c = self.ed['glow_color'].get().strip()
            if not re.fullmatch(r'#?[0-9a-fA-F]{6}', c): raise ValueError('glow color must be #rrggbb')
            r['glow'] = '#' + c.lstrip('#')
        for k in ('hide', 'continue', 'unidentified', 'preidentify'):
            if self.ed[k].get(): r[k] = True
        if not self.ed['enabled'].get(): r['enabled'] = False
        return r

    def _commit_rule(self):
        if self.sel is None: return
        try: r = self._read_editor()
        except Exception as ex: self._log('rule error: %s' % ex); return
        self.rules[self.sel] = r; self._mark(); self._refresh_rules(); self._update_matches(); self._log('updated rule "%s"' % r['name'])

    def _add_rule(self):
        self.rules.append({'name': 'new rule', 'ids': [], 'size': 3, 'glow': 'auto'}); self.sel = len(self.rules) - 1; self._mark(); self._select(self.sel)

    def _delete_rule(self):
        if self.sel is None: return
        del self.rules[self.sel]; self.sel = None; self._mark(); self._refresh_rules()

    def _move(self, i, d):
        j = i + d
        if 0 <= j < len(self.rules):
            self.rules[i], self.rules[j] = self.rules[j], self.rules[i]
            if self.sel == i: self.sel = j
            elif self.sel == j: self.sel = i
            self._mark(); self._refresh_rules()

    # ---------- matches / preview ----------
    def _current_action(self):
        try: r = self._read_editor()
        except Exception: return None
        return {'size': r.get('size', 1), 'glow': r.get('glow'), 'hide': r.get('hide', False)}

    def _update_matches(self):
        if self.tbl is None or self.sel is None: return
        try: rd = self._read_editor()
        except Exception as ex: self.match_lbl.configure(text=str(ex)); return
        rule = rulesmod.Rule(rd, 0); rule.enabled = True
        hits = sorted((i, e) for i, e in self.tbl.items() if rule.matches(i, e))
        self.match_lbl.configure(text='%d item(s) match' % len(hits)); self.match_box.delete('1.0', 'end')
        for i, e in hits[:200]:
            self.match_box.insert('end', '%-8d %-34s %s\n' % (i, e.get('identifiedDisplayName', '')[:34], e.get('identifiedResourceName', '')))
        if len(hits) > 200: self.match_box.insert('end', '... %d more\n' % (len(hits) - 200))
        if hits and not getattr(self, 'prev_rn', None): self._show_item(hits[0][0])

    def _show_item(self, iid):
        if self.tbl is None: return
        e = self.tbl[iid]; self.prev_rn = e['identifiedResourceName']; self.prev_iid = iid; self._preview()

    def _preview(self):
        rn = getattr(self, 'prev_rn', None)
        if not rn or self.busy: return
        action = self._current_action()
        def work():
            try: self.q.put(('preview', (rn, self.src.render(rn), self.src.render(rn, action, self.settings))))
            except Exception as ex: self.q.put(('log', 'preview failed for %s: %s' % (rn, ex)))
        threading.Thread(target=work, daemon=True).start()

    def _set_preview(self, rn, before, after):
        if before is None or after is None: self.prev_img.configure(image=None, text='no sprite for %s' % rn); return
        gap = 16; scale = min(1.0, 210.0 / max(after.height, 1), 320.0 / max(before.width + after.width + gap, 1))
        b = before.resize((max(1, int(before.width * scale)), max(1, int(before.height * scale))), Image.NEAREST)
        a = after.resize((max(1, int(after.width * scale)), max(1, int(after.height * scale))), Image.NEAREST)
        W = b.width + a.width + gap; H = max(b.height, a.height)
        canvas = Image.new('RGB', (W, H), (38, 48, 32)); canvas.paste(b, (0, (H - b.height) // 2)); canvas.paste(a, (b.width + gap, (H - a.height) // 2))
        self._ctkimg = ctk.CTkImage(light_image=canvas, dark_image=canvas, size=(W, H)); self.prev_img.configure(image=self._ctkimg, text='')
        e = self.tbl.get(getattr(self, 'prev_iid', 0), {})
        self.prev_cap.configure(text='%s  %s   before %dx%d -> after %dx%d' % (getattr(self, 'prev_iid', ''), e.get('identifiedDisplayName', rn)[:26], before.width, before.height, after.width, after.height))

    def _do_search(self):
        if self.tbl is None: return
        q = self.search.get().strip()
        for w in self.results.winfo_children(): w.destroy()
        if not q: return
        rx = re.compile(re.escape(q), re.I)
        hits = sorted((i, e) for i, e in self.tbl.items() if (q.isdigit() and i == int(q)) or rx.search(e.get('identifiedDisplayName', '')) or rx.search(e.get('identifiedResourceName', '')))
        for n, (i, e) in enumerate(hits[:80]):
            row = ctk.CTkFrame(self.results, fg_color='transparent'); row.grid(row=n, column=0, sticky='ew'); row.grid_columnconfigure(0, weight=1)
            ctk.CTkButton(row, text='%d  %s' % (i, e.get('identifiedDisplayName', '')[:30]), anchor='w', fg_color='transparent', hover_color='#2f343c',
                          font=('Segoe UI', 11), command=lambda i=i: self._show_item(i)).grid(row=0, column=0, sticky='ew')
            ctk.CTkButton(row, text='+', width=28, fg_color=BG2, hover_color=ACCENT_DIM, command=lambda i=i: self._add_id(i)).grid(row=0, column=1, padx=2)
        if len(hits) > 80: ctk.CTkLabel(self.results, text='... %d more, refine the search' % (len(hits) - 80), text_color=FG_DIM).grid(row=81, column=0)

    def _add_id(self, iid):
        if self.sel is None: self._log('select a rule first'); return
        cur = self.ed['ids'].get().strip()
        self.ed['ids'].delete(0, 'end'); self.ed['ids'].insert(0, (cur + ', ' if cur else '') + str(iid)); self._mark(); self._update_matches()

    # ---------- engine (in-process, background thread) ----------
    def _run(self, what):
        if self.busy: self._log('busy'); return
        if self.dirty: self._save()
        self.busy = True; self.src.close(); self._log('> ' + what)
        def work():
            engine.LOG = lambda s: self.q.put(('log', s))
            try:
                if what == 'revert': engine.revert(FILTER)
                else: engine.apply(FILTER, dry=(what == 'dry'), preview=True)
                self.q.put(('log', '[done]'))
            except SystemExit as ex: self.q.put(('log', '[aborted] %s' % ex))
            except Exception as ex: self.q.put(('log', '[error] %r' % ex))
            finally:
                engine.LOG = print; self.q.put(('done', None))
        threading.Thread(target=work, daemon=True).start()

    def _status(self):
        def work():
            try:
                i = engine.status_info(FILTER)
                self.q.put(('statusline', 'GRF %s · iteminfo %s%s' % (i['grf'], i['iteminfo'], ' · GAME RUNNING' if i['running'] else '')))
            except Exception as ex: self.q.put(('log', 'status failed: %s' % ex))
        threading.Thread(target=work, daemon=True).start()

    def _log(self, s):
        self.log.insert('end', s + '\n'); self.log.see('end')

    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == 'log': self._log(payload)
                elif kind == 'tbl':
                    self.tbl = payload; self._log('iteminfo: %d items loaded' % len(payload)); self._status()
                    if self.sel is None and self.rules: self._select(0)
                    else: self._update_matches()
                elif kind == 'preview': self._set_preview(*payload)
                elif kind == 'done': self.busy = False; self._status(); self._preview()
                elif kind == 'statusline': self.status_lbl.configure(text=payload)
        except queue.Empty:
            pass
        self.after(120, self._pump)

    def _close(self):
        if self.dirty: self._save()
        self.src.close(); self.destroy()


if __name__ == '__main__':
    App().mainloop()
