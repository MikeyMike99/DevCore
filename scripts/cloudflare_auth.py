#!/usr/bin/env python3
"""Cloudflare credential finder and API caller that never reveals secret values.

Discovery order (first match wins per field):
  1. Process environment variables.
  2. Env files: $CLOUDFLARE_ENV_FILE, <DevCore>/.env.cloudflare, ~/.config/devcore/cloudflare.env,
     ~/.config/siraugga/cloudflare.env.
  3. Bitwarden (only if a session is already unlocked): items named by $BW_CLOUDFLARE_TOKEN_ITEM
     (default "Cloudflare API Token") and $BW_CLOUDFLARE_KEY_ITEM (default "Cloudflare Global API Key").
     For the global key item, the login username is used as the account email.

Recognised fields:
  token       CLOUDFLARE_API_TOKEN | CF_API_TOKEN
  global_key  CLOUDFLARE_GLOBAL_API_KEY | CLOUDFLARE_API_KEY | CF_API_KEY
  email       CLOUDFLARE_EMAIL | CLOUDFLARE_API_EMAIL | CF_API_EMAIL
  account_id  CLOUDFLARE_ACCOUNT_ID | CF_ACCOUNT_ID
  zone_id     CLOUDFLARE_ZONE_ID | CF_ZONE_ID
  zone        CLOUDFLARE_ZONE | CF_ZONE

Auth preference: global key + email (X-Auth-Key) when both exist, else the API token (Bearer).
Use auth="token" or auth="global" to force one.

Import usage:
    from cloudflare_auth import CloudflareClient
    cf = CloudflareClient()
    cf.api("GET", f"/zones/{cf.creds.zone_id}")
    cf.graphql(query, variables)

CLI usage (output is always scrubbed of secret values):
    python3 cloudflare_auth.py status
    python3 cloudflare_auth.py verify
    python3 cloudflare_auth.py get /zones
    python3 cloudflare_auth.py graphql '<query>' '{"zoneTag": "..."}'
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API_BASE = "https://api.cloudflare.com/client/v4"
GRAPHQL_URL = f"{API_BASE}/graphql"
DEVCORE_ROOT = Path(__file__).resolve().parent.parent

FIELD_VARS = {
    "token": ("CLOUDFLARE_API_TOKEN", "CF_API_TOKEN"),
    "global_key": ("CLOUDFLARE_GLOBAL_API_KEY", "CLOUDFLARE_API_KEY", "CF_API_KEY"),
    "email": ("CLOUDFLARE_EMAIL", "CLOUDFLARE_API_EMAIL", "CF_API_EMAIL"),
    "account_id": ("CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT_ID"),
    "zone_id": ("CLOUDFLARE_ZONE_ID", "CF_ZONE_ID"),
    "zone": ("CLOUDFLARE_ZONE", "CF_ZONE"),
}
SECRET_FIELDS = ("token", "global_key")


class CloudflareError(RuntimeError):
    pass


def _env_files() -> list[Path]:
    files = []
    override = os.environ.get("CLOUDFLARE_ENV_FILE", "").strip()
    if override:
        files.append(Path(override).expanduser())
    files += [
        DEVCORE_ROOT / ".env.cloudflare",
        Path.home() / ".config" / "devcore" / "cloudflare.env",
        Path.home() / ".config" / "siraugga" / "cloudflare.env",
    ]
    return files


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return out
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        if s.startswith("export "):
            s = s[7:]
        k, v = s.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            out[k.strip()] = v
    return out


def _bw_session() -> str:
    s = os.environ.get("BW_SESSION", "").strip()
    if s:
        return s
    try:
        return (Path.home() / ".config" / "devcore" / "bw_session").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _bw_get(kind: str, item: str) -> str:
    bw = shutil.which("bw") or str(Path.home() / ".local" / "bin" / "bw")
    session = _bw_session()
    if not session or not os.path.exists(bw):
        return ""
    try:
        env = dict(os.environ, BW_SESSION=session, BW_NOINTERACTION="true")
        r = subprocess.run([bw, "get", kind, item], capture_output=True, text=True, timeout=20, env=env)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


@dataclass
class CloudflareCreds:
    token: str = field(default="", repr=False)
    global_key: str = field(default="", repr=False)
    email: str = ""
    account_id: str = ""
    zone_id: str = ""
    zone: str = ""
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def secrets(self) -> list[str]:
        return [v for v in (self.token, self.global_key) if v]

    def auth_mode(self, prefer: str = "auto") -> str:
        if prefer == "token":
            return "token" if self.token else ""
        if prefer == "global":
            return "global" if (self.global_key and self.email) else ""
        if self.global_key and self.email:
            return "global"
        return "token" if self.token else ""

    def headers(self, prefer: str = "auto") -> dict[str, str]:
        mode = self.auth_mode(prefer)
        if mode == "global":
            return {"X-Auth-Email": self.email, "X-Auth-Key": self.global_key}
        if mode == "token":
            return {"Authorization": f"Bearer {self.token}"}
        raise CloudflareError("No usable Cloudflare credentials found (run: cloudflare_auth.py status).")

    def summary(self) -> dict:
        """Safe description: which fields exist and where they came from. No secret values."""
        return {
            "token": "present" if self.token else "missing",
            "global_key": "present" if self.global_key else "missing",
            "email": "present" if self.email else "missing",
            "account_id": "present" if self.account_id else "missing",
            "zone_id": "present" if self.zone_id else "missing",
            "zone": self.zone or "missing",
            "auth_mode": self.auth_mode() or "none",
            "sources": dict(self.sources),
        }


def find_credentials(use_bitwarden: bool = True) -> CloudflareCreds:
    creds = CloudflareCreds()

    def assign(fname: str, value: str, source: str) -> None:
        if value and not getattr(creds, fname):
            setattr(creds, fname, value)
            creds.sources[fname] = source

    for fname, names in FIELD_VARS.items():
        for n in names:
            assign(fname, os.environ.get(n, "").strip(), f"env:{n}")

    for path in _env_files():
        if not path.is_file():
            continue
        values = _parse_env_file(path)
        for fname, names in FIELD_VARS.items():
            for n in names:
                assign(fname, values.get(n, ""), f"file:{path.name}")

    if use_bitwarden and not (creds.global_key and creds.email):
        key_item = os.environ.get("BW_CLOUDFLARE_KEY_ITEM", "Cloudflare Global API Key")
        if not creds.global_key:
            assign("global_key", _bw_get("password", key_item), "bitwarden")
        if creds.global_key and not creds.email:
            assign("email", _bw_get("username", key_item), "bitwarden")
    if use_bitwarden and not creds.token:
        assign("token", _bw_get("password", os.environ.get("BW_CLOUDFLARE_TOKEN_ITEM", "Cloudflare API Token")), "bitwarden")
    return creds


def scrub(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "[REDACTED]")
    return text


class CloudflareClient:
    def __init__(self, creds: CloudflareCreds | None = None, auth: str = "auto", timeout: int = 20):
        self.creds = creds or find_credentials()
        self.auth = auth
        self.timeout = timeout

    def _request(self, method: str, url: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method.upper())
        for k, v in self.creds.headers(self.auth).items():
            req.add_header(k, v)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "devcore-cloudflare-auth/1.0")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return json.loads(raw)
            except Exception:
                raise CloudflareError(scrub(f"HTTP {e.code}: {raw[:300]}", self.creds.secrets)) from None
        except Exception as e:
            raise CloudflareError(scrub(f"{type(e).__name__}: {e}", self.creds.secrets)) from None

    def api(self, method: str, path: str, body: dict | None = None) -> dict:
        return self._request(method, f"{API_BASE}/{path.lstrip('/')}", body)

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        return self._request("POST", GRAPHQL_URL, {"query": query, "variables": variables or {}})

    def verify(self) -> dict:
        mode = self.creds.auth_mode(self.auth)
        if mode == "token":
            r = self.api("GET", "/user/tokens/verify")
            return {"auth_mode": mode, "ok": bool(r.get("success")),
                    "status": (r.get("result") or {}).get("status"), "errors": r.get("errors")}
        r = self.api("GET", "/user")
        return {"auth_mode": mode, "ok": bool(r.get("success")), "errors": r.get("errors")}

    def resolve_zone_id(self) -> str:
        if self.creds.zone_id:
            return self.creds.zone_id
        if not self.creds.zone:
            raise CloudflareError("No CLOUDFLARE_ZONE_ID or CLOUDFLARE_ZONE configured.")
        r = self.api("GET", f"/zones?name={self.creds.zone}")
        result = r.get("result") or []
        if not result:
            raise CloudflareError(f"Zone '{self.creds.zone}' not visible to these credentials.")
        self.creds.zone_id = result[0]["id"]
        return self.creds.zone_id


def _main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    auth = os.environ.get("CLOUDFLARE_AUTH_MODE", "auto")
    creds = find_credentials()
    client = CloudflareClient(creds, auth=auth)
    try:
        if cmd == "status":
            out = creds.summary()
        elif cmd == "verify":
            out = client.verify()
        elif cmd == "get" and rest:
            out = client.api("GET", rest[0])
        elif cmd == "graphql" and rest:
            out = client.graphql(rest[0], json.loads(rest[1]) if len(rest) > 1 else {})
        else:
            print(__doc__)
            return 2
    except CloudflareError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    print(scrub(json.dumps(out, indent=2), creds.secrets))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
