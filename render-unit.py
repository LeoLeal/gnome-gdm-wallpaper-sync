"""Render the user unit with a separately installed runtime path."""

import argparse
import os
from pathlib import Path
import tempfile


def quote_argument(value):
    if any(ord(character) < 32 for character in value):
        raise ValueError('Control characters in the runtime path are unsupported')
    escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$')
    return '"' + escaped + '"'


def render(template, script):
    if template.count('@SCRIPT@') != 1:
        raise ValueError('Expected exactly one script placeholder')
    return template.replace('@SCRIPT@', quote_argument(str(script)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('template', type=Path)
    parser.add_argument('script', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    text = render(args.template.read_text(), args.script)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=args.output.parent, prefix='.wallpaper-unit-', delete=False) as output:
            temporary = Path(output.name)
            output.write(text.encode())
            os.fchmod(output.fileno(), 0o644)
        os.replace(temporary, args.output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
