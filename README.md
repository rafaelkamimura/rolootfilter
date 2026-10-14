**English** · **[Português (BR)](README.pt-BR.md)**

# RO Loot Filter

A Path-of-Exile-style loot filter for **Ragnarok Online LATAM**, done entirely on the client side.
It makes the drops you care about big and glowing and makes vendor trash invisible, by rewriting
the ground-drop sprites inside `data.grf` according to rules you control.

![icon](assets/rolf.png)

| action        | what you see in game                                                      |
|---------------|---------------------------------------------------------------------------|
| `size = 4`    | the drop sprite pixel-doubled 4x (any factor 1-6)                         |
| `glow`        | a colored halo behind the drop; `auto` picks the item's own hue           |
| `hide`        | a 1x1 transparent sprite, the drop is effectively invisible on the ground |
| `effect_id`   | sets the item's `EffectID` in `iteminfo_new.lub` (the server-flagged drop effect Aether Dust has) |

Everything is reversible with one click, and the tool re-baselines itself after official patches.

---

## For players: the exe

1. Download `RO Loot Filter.exe` from the [latest release](../../releases/latest).
2. **Close the game.** Apply and Revert refuse to run while `Ragexe.exe` is open.
3. Run the exe. Windows SmartScreen may warn about an unknown publisher; choose *More info →
   Run anyway*. (It is an unsigned single-file PyInstaller build; nothing is installed.)
4. Check the **Client folder** at the top. `C:\Gravity\Ragnarok` is detected automatically;
   otherwise click *Browse…* and pick the folder that contains `data.grf`.
5. Press **APPLY**. The first run takes about a minute: it snapshots your untouched `data.grf`,
   reads the item table, builds the sprites and writes them. The log at the bottom shows progress
   and ends with `verify: N/N files read back identical`.
6. Start the game. Runes, Éter materials and the other highlighted items are now large and glowing;
   Jellopy and friends are gone from the ground.

**Revert** restores the original `data.grf` and `iteminfo_new.lub` exactly. Do this before
reporting any client bug to support, and whenever you want the stock look back.

### Editing rules in the GUI

* **Rules** (left): evaluated top to bottom, the first matching rule decides. Reorder with ▲▼,
  select one to edit it, `+ new` adds one.
* **Rule** (middle): match by item IDs (`909, 1000636-1000643`), a regex on the resource name,
  the pt-BR display name or the description, or by an existing EffectID. Set size, glow, hide,
  "continue to later rules", and whether the rule is enabled. Press **Update rule** to store it.
  The list under *Matches* shows exactly which items the rule currently catches.
* **Preview** (right): before/after render of the selected item. Search items by name, resource
  or id; the `+` button adds that id to the current rule.
* **Save** writes `filter.toml`; **Dry run** shows the plan without touching the client.

### Where things live

| | |
|---|---|
| your rules       | `filter.toml` next to the exe if present, else `%LOCALAPPDATA%\RoLootFilter\filter.toml` |
| snapshots/cache  | `%LOCALAPPDATA%\RoLootFilter\cache` (pristine GRF header, pristine iteminfo, extracted originals) |
| previews         | `%LOCALAPPDATA%\RoLootFilter\preview\*.png` |

Shipping a `filter.toml` next to the exe is the easy way to give your guild a shared, tuned filter.

### After an official patch

The patcher rewrites `data.grf`, which drops the modifications. Just open the tool and press
**APPLY** again; it notices the file changed, takes a fresh snapshot and re-applies the rules.

---

## For developers: running from source

Requirements: Python 3.11+ (3.14 tested), Windows.

```
pip install lupa customtkinter pillow      # lupa = Lua 5.1 VM used to execute iteminfo_new.lub
python rolfgui.py                           # the GUI
python rolf.py apply [filter.toml] [--dry] [--no-preview]
python rolf.py revert
python rolf.py status
python rolf.py search "Éter|Runa"           # find ids / resource names to write rules against
```

Running from source keeps state in `cache/` and `preview/` inside the project (both gitignored).

### Building the exe

```
pip install pyinstaller
.\build.ps1                                  # -> dist\RO Loot Filter.exe
```

### Rule file reference

```toml
[settings]
client = 'C:\Gravity\Ragnarok'
glow_alpha = 200          # halo peak opacity 0-255
glow_scale = 1.9          # halo diameter relative to the enlarged sprite
patch_iteminfo = true     # allow effect_id rules to rewrite System\iteminfo_new.lub

[[rule]]
name = "Barmund rune fragments"
ids = ["1000636-1000639"]           # ints or "a-b" ranges
size = 6
glow = "auto"                       # "auto" | "#rrggbb" | "none"
effect_id = 1870

[[rule]]
name = "Aether family"
resource = "^(HD_|Blessed_)?Etel_"  # regex on identifiedResourceName
size = 4
glow = "auto"

[[rule]]
name = "Hide vendor trash"
ids = [909, 914, 705, 916, 938]
hide = true

# other match keys: name_match (pt-BR display name regex), description (regex),
#                   effect (item already has this EffectID), min_id, max_id
# other actions:    continue = true (keep evaluating), unidentified = true (also patch the
#                   unidentified sprite; shared by many equips, use with care), enabled = false
```

Rules with several match keys require all of them to match. A rule with no match keys is an error.

### How it works

* `data.grf` is GRF **0x300** ("Event Horizon" signature, 64-bit offsets, file table in the
  middle of the archive). Patching is append-only: new sprite blobs and a rebuilt table are written
  after the old end of file and the 8-byte table pointer in the header is repointed. Revert is
  "restore the 46-byte header and truncate". Nothing pre-existing is ever overwritten.
* Classic entries are encrypted (flag 3 mixed, flag 5 header-only). Gravity's cipher is a single
  keyless DES round (IP, L ^= F(R), FP) on the first 20 blocks, then one block every `cycle` blocks
  plus a byte shuffle on every 7th remaining block. See `rolfcore/grfdes.py` and `grf.py`.
* Item sprites are `data\sprite\아이템\<resource>.spr/.act` (CP949 folder name, which shows as
  `¾ÆÀÌÅÛ` in Latin-1 tools; names are lowercase inside the GRF). SPR v2.1 (RLE palette frames,
  ABGR frames) and ACT 2.0-2.5 (always written back as 2.5). The halo is an extra ABGR frame
  inserted as layer 0.
* `iteminfo_new.lub` is 32-bit Lua 5.1 bytecode with UTF-8 strings that only defines `tbl`.
  It is executed by transcoding `size_t` 4→8 and running it in lupa's Lua 5.1 VM with every
  global stubbed; rebuilt with `string.dump` and transcoded back, then round-trip verified before
  install. `iteminfo_f.lub` holds `main()`, which calls `AddItemEffectInfo(id, EffectID)`.
* `EffectID 1870` is what gives Aether Dust its drop glow. The server decides per drop whether the
  effect plays, so `effect_id` is best-effort; the baked halo is the part that always shows.

### Layout

```
rolf.py            CLI
rolfgui.py         GUI (customtkinter)
rolfcore/engine.py apply / revert / status, snapshot logic
rolfcore/grf.py    GRF 0x300 reader + append writer      rolfcore/grfdes.py  Gravity cipher
rolfcore/sprite.py SPR/ACT parsing, transforms, renderer  rolfcore/iteminfo.py lub load/rebuild
rolfcore/rules.py  rule matching                          rolfcore/tomlout.py  filter writer
filter.toml        the rules                              build.ps1            exe build
```

## Status

Tested on RO LATAM (client of 2026-10-01, Episode 18 + Ecosfera de Varmundt content). The
included filter highlights the Varmunt runes, the Éter family, Episode 18 materials and the
Lágrima Temporal exchange items, and hides 28 vendor-trash drops.
