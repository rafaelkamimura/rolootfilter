"""RO loot filter CLI.

  python rolf.py apply   [filter.toml] [--dry] [--no-preview]
  python rolf.py revert  [filter.toml]
  python rolf.py status  [filter.toml]
  python rolf.py search  <regex> [filter.toml]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rolfcore import engine

DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'filter.toml')


def main(argv):
    if not argv or argv[0] in ('-h', '--help'): print(__doc__); return 0
    cmd, rest = argv[0], argv[1:]
    flags = {a for a in rest if a.startswith('--')}; args = [a for a in rest if not a.startswith('--')]
    if cmd == 'apply':
        engine.apply(args[0] if args else DEFAULT, dry='--dry' in flags, preview='--no-preview' not in flags)
    elif cmd == 'revert': engine.revert(args[0] if args else DEFAULT)
    elif cmd == 'status': engine.status(args[0] if args else DEFAULT)
    elif cmd == 'search': engine.search(args[1] if len(args) > 1 else DEFAULT, args[0])
    else: print(__doc__); return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
