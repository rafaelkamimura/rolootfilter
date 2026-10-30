"""Minimal TOML writer for filter files (settings table + [[rule]] array). Comments are not preserved."""

HEADER = """# RO LATAM loot filter — rules are evaluated top to bottom, first match wins (unless `continue = true`).
# Match keys : ids, resource, name_match, description, effect, min_id, max_id
# Actions    : size, glow ("auto" | "#rrggbb" | "none"), hide, effect_id, preidentify, continue, unidentified, enabled
"""

RULE_KEYS = ['name', 'enabled', 'ids', 'resource', 'name_match', 'description', 'effect', 'min_id', 'max_id',
             'size', 'glow', 'hide', 'effect_id', 'preidentify', 'continue', 'unidentified']


def _val(v):
    if isinstance(v, bool): return 'true' if v else 'false'
    if isinstance(v, int): return str(v)
    if isinstance(v, float): return repr(v)
    if isinstance(v, str):
        if '\\' in v and '\'' not in v and '\n' not in v: return "'" + v + "'"
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    if isinstance(v, (list, tuple)): return '[' + ', '.join(_val(x) for x in v) + ']'
    raise TypeError(type(v))


def dumps(settings, rules):
    out = [HEADER, '[settings]']
    for k, v in settings.items(): out.append('%s = %s' % (k, _val(v)))
    for r in rules:
        out.append(''); out.append('[[rule]]')
        for k in RULE_KEYS + [x for x in r if x not in RULE_KEYS]:
            if k not in r: continue
            v = r[k]
            if k == 'enabled' and v is True: continue
            if v is None or v == '' or v == [] : continue
            out.append('%s = %s' % (k, _val(v)))
    return '\n'.join(out) + '\n'
