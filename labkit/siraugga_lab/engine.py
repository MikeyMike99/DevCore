"""Runs a lab: each step's command is either local (virtual shell) or remote (our server)."""
import json
import os
import re

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


def _progress_path(progress_dir, lab_id):
    return os.path.join(progress_dir, re.sub(r"[^A-Za-z0-9_.-]", "_", lab_id) + ".json")


def play(lab: dict, remote: Remote, inp=input, out=print, progress_dir=None, restart=False) -> int:
    s = LabSession(lab, remote)
    steps = lab["steps"]
    idx = 0
    ppath = _progress_path(progress_dir, lab["id"]) if progress_dir else None
    if ppath and os.path.isfile(ppath):
        if restart:
            os.remove(ppath)
        else:
            try:
                with open(ppath, encoding="utf-8") as f:
                    saved = json.load(f)
                s.shell.import_state(saved["shell"])
                idx = min(int(saved["step"]), len(steps))
                out(f"(resuming at step {idx + 1} of {len(steps)})")
            except (OSError, ValueError, KeyError):
                idx = 0

    def save():
        if ppath:
            os.makedirs(progress_dir, exist_ok=True)
            with open(ppath, "w", encoding="utf-8") as f:
                json.dump({"step": idx, "shell": s.shell.export_state()}, f)

    out(f"== {lab['title']} ==  (commands: hint, exit)")
    while idx < len(steps):
        step = steps[idx]
        out(f"\nStep {step['id']} of {len(steps)}: {step['task']}")
        fails = 0
        while True:
            try:
                line = inp(f"{s.shell.cwd} $ ")
            except EOFError:
                save()
                return 1
            line = line.lstrip("﻿")  # piped input from Windows shells may start with a BOM
            cmd = line.strip()
            if cmd in ("quit", "exit"):
                save()
                out("Lab paused - your progress is saved. Run it again to continue.")
                return 0
            if cmd == "hint":
                hints = step.get("hints") or ["No hint for this step - re-read the task."]
                out("Hint: " + hints[min(fails, len(hints) - 1)])
                continue
            res, where = s.run_command(line, step["id"])
            if res or TAGS[where]:
                out(TAGS[where] + res)
            if s.check(step, line, res):
                out("OK - step complete.")
                idx += 1
                save()
                break
            fails += 1
            out("Not quite - try again (type 'hint' for help, 'exit' to stop).")
    if ppath and os.path.isfile(ppath):
        os.remove(ppath)
    pend = remote.pending()
    out("\nLab complete." + (f" {pend} action(s) waiting to sync - run: siraugga-lab sync" if pend else ""))
    return 0
