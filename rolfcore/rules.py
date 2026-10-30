"""Rule evaluation. Rules are ordered; the first matching rule decides what happens to an item (PoE style).

Rule keys (all optional, all must match when present):
  ids         list of ints or "a-b" range strings
  resource    regex on identifiedResourceName (case-insensitive)
  name        regex on identifiedDisplayName
  description regex on the joined description lines
  effect      int EffectID the item must already have (1186 = cards/valuables, 1870 = special drops)
  min_id / max_id
Actions:
  size   int scale factor (default 1)
  glow   "auto" | "#rrggbb" | "none"
  effect_id  int -> write this EffectID into iteminfo (needs patch_iteminfo = true in [settings])
  hide   true -> replace the ground sprite with a 1x1 transparent frame
  continue  true -> keep evaluating later rules (PoE "Continue")
  unidentified  true -> also patch unidentifiedResourceName when it differs (equipment drops)
  preidentify   true -> copy the identified sprite/name/description over the unidentified fields in iteminfo,
                        so an unidentified ground drop shows the item's own sprite (needs patch_iteminfo)
"""
import re


def _ids(spec):
    out = set()
    for v in spec or []:
        if isinstance(v, int): out.add(v)
        else:
            s = str(v).strip()
            if '-' in s:
                a, b = s.split('-', 1); out.update(range(int(a), int(b) + 1))
            else: out.add(int(s))
    return out


class Rule:
    def __init__(self, d, n):
        self.name = d.get('name', 'rule %d' % n); self.d = d
        self.enabled = bool(d.get('enabled', True))
        self.ids = _ids(d.get('ids')) if 'ids' in d else None
        self.resource = re.compile(d['resource'], re.I) if 'resource' in d else None
        self.dname = re.compile(d['name_match'], re.I) if 'name_match' in d else None
        self.desc = re.compile(d['description'], re.I) if 'description' in d else None
        self.effect = d.get('effect'); self.min_id = d.get('min_id'); self.max_id = d.get('max_id')
        self.size = int(d.get('size', 1)); self.glow = d.get('glow'); self.hide = bool(d.get('hide', False))
        self.effect_id = d.get('effect_id'); self.cont = bool(d.get('continue', False))
        self.unidentified = bool(d.get('unidentified', False)); self.preidentify = bool(d.get('preidentify', False))
        if 'name' in d and not any(k in d for k in ('ids', 'resource', 'name_match', 'description', 'effect', 'min_id', 'max_id')):
            raise ValueError('rule %r has no match criteria' % self.name)

    def matches(self, iid, e):
        if not self.enabled: return False
        if self.ids is not None and iid not in self.ids: return False
        if self.min_id is not None and iid < self.min_id: return False
        if self.max_id is not None and iid > self.max_id: return False
        if self.resource and not self.resource.search(e.get('identifiedResourceName', '')): return False
        if self.dname and not self.dname.search(e.get('identifiedDisplayName', '')): return False
        if self.desc and not self.desc.search('\n'.join(e.get('identifiedDescriptionName') or [])): return False
        if self.effect is not None and e.get('EffectID') != self.effect: return False
        return True

    def is_noop(self):
        return self.size <= 1 and not self.glow and not self.hide and self.effect_id is None and not self.preidentify


def evaluate(rules, tbl):
    """Returns {item_id: {'rule': Rule, 'size':..., 'glow':..., 'hide':..., 'effect_id':..., 'unidentified':...}}"""
    out = {}
    for iid, e in tbl.items():
        act = None
        for r in rules:
            if not r.matches(iid, e): continue
            if act is None: act = {'rule': r, 'size': 1, 'glow': None, 'hide': False, 'effect_id': None, 'unidentified': False, 'preidentify': False}
            if r.size > 1: act['size'] = max(act['size'], r.size)
            if r.glow: act['glow'] = r.glow
            if r.hide: act['hide'] = True
            if r.effect_id is not None: act['effect_id'] = r.effect_id
            if r.unidentified: act['unidentified'] = True
            if r.preidentify: act['preidentify'] = True
            if not r.cont: break
        if act and not (act['size'] <= 1 and not act['glow'] and not act['hide'] and act['effect_id'] is None and not act['preidentify']):
            out[iid] = act
    return out
