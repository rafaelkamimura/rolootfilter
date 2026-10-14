# rolootfilter

A Path-of-Exile-style loot filter for Ragnarok Online LATAM, implemented purely client-side.

RO's client cannot be told to hide or recolor drops, but it draws every ground drop from a
sprite inside `data.grf`. This tool rewrites those sprites according to rules in `filter.toml`:

| action      | what the client shows                                              |
|-------------|--------------------------------------------------------------------|
| `size = N`  | pixel-doubled drop sprite, N times bigger                          |
| `glow`      | a colored halo layer behind the sprite (`auto` picks the item hue) |
| `hide`      | 1x1 transparent sprite, the drop is effectively invisible          |
| `effect_id` | sets the item's `EffectID` in `iteminfo_new.lub` (Aether Dust's 1870 drop effect) — only visible when the server flags the drop |

## Usage

```
python rolf.py apply            # evaluate filter.toml, patch data.grf (+ iteminfo), write preview/*.png
python rolf.py apply --dry      # show the plan only
python rolf.py revert           # restore pristine data.grf and iteminfo_new.lub
python rolf.py status
python rolf.py search "Éter"    # find item ids / resource names to write rules against
```

Close the game client before `apply` or `revert`.

## How it stays safe

* First run snapshots the pristine GRF (header + size) in `cache/state.json`. Patching is
  append-only: new sprite blobs and a rebuilt file table go after the old end of file and the
  8-byte table pointer in the header is repointed. `revert` = restore header + truncate.
* Every `apply` first reverts to pristine, so rule edits never stack.
* If the official patcher rewrites `data.grf`, the old snapshot no longer validates and the new
  file becomes the baseline automatically. Just run `apply` again after a patch.
* `iteminfo_new.lub` is rebuilt from a pristine copy (`cache/iteminfo_new.lub.pristine`) and
  round-trip verified before it is installed.

## Rule reference

```toml
[[rule]]
name = "label"
ids = [1000405, "1000636-1000643"]   # any of: ids, resource, name_match, description, effect, min_id, max_id
resource = "^Etel_"                   # regex on identifiedResourceName
name_match = "Runa"                   # regex on identifiedDisplayName (pt-BR)
description = "Varmunt"               # regex on the description text
effect = 1870                         # item already has this EffectID
size = 4
glow = "auto"                         # or "#rrggbb" or "none"
hide = false
effect_id = 1870
continue = false                      # true = keep evaluating later rules (PoE Continue)
unidentified = false                  # also patch the unidentified sprite (shared by many equips, careful)
```

## Requirements

Python 3.11+ and `pip install lupa` (bundled Lua 5.1 VM used to execute the lub).

## Internals worth knowing

* `data.grf` is GRF 0x300 ("Event Horizon" signature, 64-bit offsets, table in the middle of the file).
* Item sprites live in `data\sprite\아이템\` (CP949; shows as `¾ÆÀÌÅÛ` in Latin-1 tools). Resource
  names are lowercase inside the GRF.
* `iteminfo_new.lub` is 32-bit Lua 5.1 bytecode with UTF-8 strings; it only defines `tbl`.
  `iteminfo_f.lub` holds `main()`, which calls `AddItemEffectInfo(id, EffectID)`.
* SPR v2.1 (RLE palette frames + ABGR frames), ACT v2.5 (layers: x, y, sprIndex, mirror, color,
  scaleX, scaleY, rot, sprType, w, h). The halo is an extra ABGR frame drawn as layer 0.
