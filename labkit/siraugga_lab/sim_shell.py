"""A tiny sandboxed shell over an in-memory virtual filesystem.

Nothing here touches the learner's real disk: every command works on the lab's
virtual files, so it behaves the same on Windows, Mac and Linux.
Supports `cmd > file` and `cmd >> file` redirection.
"""
import base64
import hashlib
import posixpath
import shlex


class SimShell:
    def __init__(self, files=None, home: str = "/home/learner"):
        self.files: dict = {}
        self.dirs: set = {"/", "/home", home}
        self.home = home
        self.cwd = home
        for path, text in (files or {}).items():
            self._write(self._abs(path), text)

    # -- path helpers
    def _abs(self, p: str) -> str:
        if p.startswith("~"):
            p = self.home + p[1:]
        return posixpath.normpath(p if p.startswith("/") else posixpath.join(self.cwd, p))

    def _write(self, path: str, text: str) -> None:
        d = posixpath.dirname(path)
        while d and d not in self.dirs:
            self.dirs.add(d)
            d = posixpath.dirname(d)
        self.files[path] = text

    # -- public
    def run(self, line: str):
        try:
            parts = shlex.split(line)
        except ValueError as e:
            return 2, f"sh: {e}"
        if not parts:
            return 0, ""
        target, append = None, False
        for op in (">>", ">"):
            if op in parts:
                i = parts.index(op)
                if i + 1 >= len(parts):
                    return 2, "sh: syntax error near redirect"
                target, append = parts[i + 1], op == ">>"
                parts = parts[:i] + parts[i + 2:]
                break
        if not parts:
            return 0, ""
        fn = getattr(self, "cmd_" + parts[0].replace("-", "_"), None)
        if fn is None:
            return 127, f"{parts[0]}: command not found"
        try:
            rc, out = fn(parts[1:])
        except Exception as e:  # a bad command must never crash the lab
            return 1, f"{parts[0]}: {e}"
        if target is not None and rc == 0:
            p = self._abs(target)
            self._write(p, (self.files.get(p, "") + out) if append else out)
            return 0, ""
        return rc, out

    # -- commands
    def cmd_pwd(self, a): return 0, self.cwd
    def cmd_whoami(self, a): return 0, "learner"
    def cmd_echo(self, a): return 0, " ".join(a)
    def cmd_clear(self, a): return 0, ""

    def cmd_cd(self, a):
        t = self._abs(a[0] if a else "~")
        if t not in self.dirs:
            return 1, f"cd: {a[0]}: No such file or directory"
        self.cwd = t
        return 0, ""

    def cmd_ls(self, a):
        args = [x for x in a if not x.startswith("-")]
        t = self._abs(args[-1] if args else ".")
        if t in self.files:
            return 0, posixpath.basename(t)
        if t not in self.dirs:
            return 2, f"ls: cannot access '{t}': No such file or directory"
        names = {posixpath.basename(x) + ("/" if x in self.dirs else "")
                 for x in list(self.files) + list(self.dirs)
                 if x != t and posixpath.dirname(x) == t}
        return 0, "  ".join(sorted(names))

    def cmd_cat(self, a):
        out = []
        for f in a:
            p = self._abs(f)
            if p not in self.files:
                return 1, f"cat: {f}: No such file or directory"
            out.append(self.files[p])
        return 0, "\n".join(out)

    def cmd_mkdir(self, a):
        for d in [x for x in a if not x.startswith("-")]:
            self.dirs.add(self._abs(d))
        return 0, ""

    def cmd_touch(self, a):
        for f in a:
            self.files.setdefault(self._abs(f), "")
        return 0, ""

    def cmd_rm(self, a):
        for f in [x for x in a if not x.startswith("-")]:
            if self.files.pop(self._abs(f), None) is None:
                return 1, f"rm: cannot remove '{f}': No such file or directory"
        return 0, ""

    def cmd_head(self, a):
        rc, text = self.cmd_cat([x for x in a if not x.startswith("-")])
        return (rc, text) if rc else (0, "\n".join(text.splitlines()[:10]))

    def cmd_grep(self, a):
        if len(a) < 2:
            return 2, "usage: grep PATTERN FILE"
        rc, text = self.cmd_cat(a[1:])
        if rc:
            return rc, text
        hits = [ln for ln in text.splitlines() if a[0] in ln]
        return (0 if hits else 1), "\n".join(hits)

    def cmd_wc(self, a):
        rc, text = self.cmd_cat([x for x in a if not x.startswith("-")])
        return (rc, text) if rc else (0, str(len(text.splitlines())))

    def cmd_sha256sum(self, a):
        rc, text = self.cmd_cat(a)
        return (rc, text) if rc else (0, hashlib.sha256(text.encode()).hexdigest() + "  " + a[0])

    def cmd_md5sum(self, a):
        rc, text = self.cmd_cat(a)
        return (rc, text) if rc else (0, hashlib.md5(text.encode()).hexdigest() + "  " + a[0])

    def cmd_base64(self, a):
        dec = "-d" in a or "--decode" in a
        rc, text = self.cmd_cat([x for x in a if not x.startswith("-")])
        if rc:
            return rc, text
        data = text.strip().encode()
        return 0, (base64.b64decode(data).decode(errors="replace") if dec
                   else base64.b64encode(data).decode())
