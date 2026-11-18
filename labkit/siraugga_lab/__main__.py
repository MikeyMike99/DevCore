import argparse
import os
import sys

from siraugga_lab import __version__
from siraugga_lab.engine import list_labs, load_lab, play
from siraugga_lab.remote import Remote, load_config, save_config


def state_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "SirauggaLab")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="siraugga-lab", description="Siraugga lab runner")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="show available labs")
    r = sub.add_parser("run", help="run a lab (resumes where you stopped)")
    r.add_argument("lab")
    r.add_argument("--restart", action="store_true", help="start the lab from step 1")
    sub.add_parser("sync", help="send queued server actions")
    lg = sub.add_parser("login", help="save your learner id and key (from your Siraugga account)")
    lg.add_argument("learner")
    lg.add_argument("key")
    sub.add_parser("status", help="show who you are and what is waiting to sync")
    args = ap.parse_args(argv)
    sd = state_dir()

    if args.cmd == "login":
        cfg = load_config(sd)
        cfg.update(learner=args.learner, key=args.key)
        save_config(sd, cfg)
        print(f"Saved. Signed in as {args.learner}.")
        return 0
    remote = Remote(sd)
    if args.cmd == "list":
        print("\n".join(list_labs()) or "no labs bundled")
    elif args.cmd == "run":
        if not remote.learner:
            print("(not signed in - server steps will be simulated. Use: siraugga-lab login <id> <key>)")
        return play(load_lab(args.lab), remote, progress_dir=os.path.join(sd, "progress"),
                    restart=args.restart)
    elif args.cmd == "sync":
        sent, left = remote.sync()
        print(f"sent {sent}, still waiting {left}")
    elif args.cmd == "status":
        print(f"learner: {remote.learner or '(not signed in)'}\nserver:  {remote.base}\n"
              f"waiting to sync: {remote.pending()}")
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
