import argparse
import os
import sys

from siraugga_lab import __version__
from siraugga_lab.engine import list_labs, load_lab, play
from siraugga_lab.remote import Remote


def state_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "SirauggaLab")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="siraugga-lab", description="Siraugga lab runner")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="show available labs")
    r = sub.add_parser("run", help="run a lab")
    r.add_argument("lab")
    sub.add_parser("sync", help="send queued server actions")
    args = ap.parse_args(argv)
    remote = Remote(state_dir(), os.environ.get("SIRAUGGA_LAB_TOKEN", ""))
    if args.cmd == "list":
        print("\n".join(list_labs()) or "no labs bundled")
    elif args.cmd == "run":
        return play(load_lab(args.lab), remote)
    elif args.cmd == "sync":
        sent, left = remote.sync()
        print(f"sent {sent}, still waiting {left}")
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
