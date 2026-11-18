"""Runs a lab: each step's command is either local (virtual shell) or remote (our server)."""
import json
import os

from .remote import Remote
from .sim_shell import SimShell


def bundled_dir(*parts: str) -> str:
    # Works from source and inside a Nuitka build (data files sit next to the code).
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parts)


def load_lab(name_or_path: str) -> dict:
    path = name_or_path if os.path.isfile(name_or_path) else bundled_dir("labs", name_or_path + ".json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_labs() -> list:
    d = bundled_dir("labs")
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json")) if os.path.isdir(d) else []


class LabSession:
    def __init__(self, lab: dict, remote: Remote):
        self.lab, self.remote = lab, remote
        self.shell = SimShell(lab.get("files"))
        self.remote_cmds = set(lab.get("remote_commands", []))

    def run_command(self, line: str, step_id: str = "free"):
        """Returns (output, where) where is 'local' | 'server' | 'simulated'."""
        head = line.split(None, 1)[0] if line.strip() else ""
        if head in self.remote_cmds:
            sim = self.lab.get("simulated", {}).get(head, f"{head}: ok (simulated server reply)")
            real, out = self.remote.execute(self.lab["id"], step_id, line, sim)
            return out, ("server" if real else "simulated")
        _, out = self.shell.run(line)
        return out, "local"

    @staticmethod
    def check(step: dict, line: str, output: str) -> bool:
        exp, want = step.get("expect_command"), step.get("expect_output")
        return (exp is None or line.strip().startswith(exp)) and (want is None or want in output)


TAGS = {"local": "", "server": "[server] ",
        "simulated": "[SIMULATED - server unreachable; will sync later] "}


def play(lab: dict, remote: Remote, inp=input, out=print) -> int:
    s = LabSession(lab, remote)
    out(f"== {lab['title']} ==")
    for step in lab["steps"]:
        out(f"\nStep {step['id']}: {step['task']}")
        while True:
            try:
                line = inp(f"{s.shell.cwd} $ ")
            except EOFError:
                return 1
            line = line.lstrip("﻿")  # piped input from Windows shells may start with a BOM
            if line.strip() in ("quit", "exit"):
                out("Lab paused. Run again to continue.")
                return 0
            res, where = s.run_command(line, step["id"])
            if res or TAGS[where]:
                out(TAGS[where] + res)
            if s.check(step, line, res):
                out("OK - step complete.")
                break
            out("Not quite - try again (type 'exit' to stop).")
    pend = remote.pending()
    out("\nLab complete." + (f" {pend} action(s) waiting to sync - run: siraugga-lab sync" if pend else ""))
    return 0
