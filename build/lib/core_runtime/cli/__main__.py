"""CLI entry point for core_runtime.tool commands."""

from __future__ import annotations

import sys

from core_runtime.cli.main import build_parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return 2

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())