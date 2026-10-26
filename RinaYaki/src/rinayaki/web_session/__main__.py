"""Command-line entry point for one isolated site login window."""
import argparse
import sys

from .model import session_target
from .runner import run_window


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Open a RinaYaki site login window')
    parser.add_argument('--source', required=True)
    args = parser.parse_args(argv)
    try:
        run_window(session_target(args.source))
    except (RuntimeError, ValueError):
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
