from __future__ import annotations

import argparse
import json
from pathlib import Path

from .manager import _load_file, _dump_file


def _cmd_show(args: argparse.Namespace) -> None:
    data = _load_file(Path(args.file))
    print(json.dumps(data, indent=4))


def _cmd_set(args: argparse.Namespace) -> None:
    path = Path(args.file)
    data = _load_file(path)
    keys = args.key.split(".")
    cur = data
    for k in keys[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[keys[-1]] = args.value
    _dump_file(path, data)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Dynamic Config Manager CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show", help="Display configuration file")
    p_show.add_argument("file")
    p_show.set_defaults(func=_cmd_show)

    p_set = sub.add_parser("set", help="Set a value in configuration file")
    p_set.add_argument("file")
    p_set.add_argument("key")
    p_set.add_argument("value")
    p_set.set_defaults(func=_cmd_set)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover - manual use
    main()

