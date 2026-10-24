from mcp.server.mcpserver import MCPServer
import ast
import json
import logging
import os
import py_compile
import re
import shutil
import sys
import traceback
import hashlib

DEVCORE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if DEVCORE_ROOT not in sys.path:
    sys.path.insert(0, DEVCORE_ROOT)

LOG_FILE = os.path.join(DEVCORE_ROOT, "logs", "plugin_raugus_resolver.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] MCP_RAUGUS_RESOLVER: %(message)s",
)
logging.info("Opaque Key-Only Raugus Resolver MCP Server Booting...")

from security.raugus_resolver import RaugusResolver

mcp = MCPServer("Raugus Resolver")

PROTECTED_GUARD_BASENAMES = {
    "raugus_hook.py",
    "hooks.json",
    "settings.json",
    "local_brain_broker.py",
    "raugus_resolver.py",
    "raugus_map.json",
    "generate_raugusmap.py",
    "tool_security_auditor.py",
}

_RESOLVER = None


def _get_resolver() -> RaugusResolver:
    global _RESOLVER
    if _RESOLVER is None:
        _RESOLVER = RaugusResolver()
    return _RESOLVER


def _scrub_paths(text: str) -> str:
    """
    Guarantees that no physical host filesystem paths (/mnt/c/..., C:\\Users\\..., /home/...)
    are ever revealed to the agent in any returned code, digest, or error message.
    """
    if not text or not isinstance(text, str):
        return text
    out = re.sub(
        r"/mnt/[a-zA-Z]/Users/[^/\s\"']+/Documents/DevCore",
        "<RAUGUS_VFS_ROOT>",
        text,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"[a-zA-Z]:\\+Users\\+[^\\\s\"']+\\+Documents\\+DevCore",
        "<RAUGUS_VFS_ROOT>",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"/mnt/[a-zA-Z]/Users/[^\s\"')\]}]+",
        "<REDACTED_HOST_PATH>",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"[a-zA-Z]:\\+Users\\+[^\s\"')\]}]+",
        "<REDACTED_HOST_PATH>",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"/home/[^/\s\"']+/[^\s\"')\]}]+",
        "<REDACTED_HOST_PATH>",
        out,
        flags=re.IGNORECASE,
    )
    return out


def _json_response(payload: dict) -> str:
    """Serializes payload to JSON and scrubs any accidental physical host paths."""
    raw = json.dumps(payload, indent=2)
    return _scrub_paths(raw)


def _extract_ast_nodes(source_code: str) -> dict:
    """
    Parses Python source code and returns a map of symbol names to
    (kind, start_line, end_line) where lines are 1-indexed inclusive.
    Supports functions, async functions, classes, variables, and class methods/attributes (ClassName::method).
    """
    symbols = {}
    try:
        tree = ast.parse(source_code)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                symbols[node.name] = ("function", node.lineno, getattr(node, "end_lineno", node.lineno))
            elif isinstance(node, ast.AsyncFunctionDef):
                symbols[node.name] = ("async_function", node.lineno, getattr(node, "end_lineno", node.lineno))
            elif isinstance(node, ast.ClassDef):
                symbols[node.name] = ("class", node.lineno, getattr(node, "end_lineno", node.lineno))
                for child in node.body:
                    if isinstance(child, ast.FunctionDef):
                        symbols[f"{node.name}::{child.name}"] = ("method", child.lineno, getattr(child, "end_lineno", child.lineno))
                    elif isinstance(child, ast.AsyncFunctionDef):
                        symbols[f"{node.name}::{child.name}"] = ("async_method", child.lineno, getattr(child, "end_lineno", child.lineno))
                    elif isinstance(child, ast.Assign):
                        for target in child.targets:
                            if isinstance(target, ast.Name):
                                symbols[f"{node.name}::{target.id}"] = ("variable", child.lineno, getattr(child, "end_lineno", child.lineno))
                    elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                        symbols[f"{node.name}::{child.target.id}"] = ("variable", child.lineno, getattr(child, "end_lineno", child.lineno))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols[target.id] = ("variable", node.lineno, getattr(node, "end_lineno", node.lineno))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                symbols[node.target.id] = ("variable", node.lineno, getattr(node, "end_lineno", node.lineno))
    except SyntaxError:
        pass
    return symbols


IMMUTABLE_JIT_BASENAMES = {
    "jit_elevation.py",
    ".jit_elevation_lease.json",
    ".devcore_master.key",
}


def _is_immutable_jit_key(key: str, real_path: str = "") -> bool:
    base = os.path.basename(real_path) if real_path else ""
    if base in IMMUTABLE_JIT_BASENAMES:
        return True
    for g in IMMUTABLE_JIT_BASENAMES:
        if key.endswith(f".{g}") or f".{g}::" in key or g in key:
            return True
    return False


def _is_self_protected_key(key: str, real_path: str = "") -> bool:
    if _is_immutable_jit_key(key, real_path):
        return True
    if "raugus_resolver" in key and "plugins" in key:
        return True
    base = os.path.basename(real_path) if real_path else ""
    if base in PROTECTED_GUARD_BASENAMES:
        return True
    for g in PROTECTED_GUARD_BASENAMES:
        if key.endswith(f".{g}") or f".{g}::" in key:
            return True
    return False


def _check_jit_elevation(elevation_token: str = "") -> bool:
    try:
        from security.jit_elevation import verify_jit_elevation
        ver = verify_jit_elevation(candidate_token=elevation_token or None)
        return bool(ver.get("valid") is True)
    except Exception:
        return False


def _is_engine_module_path(real_path: str) -> bool:
    if not real_path:
        return False
    norm = os.path.abspath(real_path).replace("\\", "/")
    return (
        norm.endswith(".py")
        and (
            "/DevCore/core/" in norm
            or "/DevCore/agents/" in norm
            or "/DevCore/security/" in norm
        )
        and "/DevCore/core/patches/" not in norm
        and "/DevCore/core/backups/" not in norm
    )


def _is_writable_via_resolver(
    key: str,
    real_path: str,
    mod_entry: dict,
    sym_entry: dict,
    user_tier: int,
    elevation_token: str = "",
) -> tuple:
    """
    Determines whether `key` is writable via the Raugus Resolver for `user_tier`.
    - Immutable JIT authority files (jit_elevation.py, .devcore_master.key) are never writable by AI.
    - Self-protected guard files are locked by default, but unlocked for 5 minutes when a valid
      Human-in-the-Loop Super Admin JIT Elevation Token/Lease is active.
    - Exam Application blueprints (exam_application.html, exam_builder.html, EXAM_APPLICATION.md) are strictly Read-Only.
    - Live backend engine .py modules are writable by Tier 5 Admins via automatic Hot-Patch Staging, unless the symbol is explicitly locked (`locked: true`).
    - Workspace files follow `permissions.write` in the Raugus Map.
    Returns (allowed: bool, status_code: str, reason: str).
    """
    if _is_immutable_jit_key(key, real_path):
        return (
            False,
            "DENIED_SELF_PROTECTION",
            (
                "[RAUGUS ANTI-SELF-MINTING FIREWALL]\n"
                f"Key '{key}' is an immutable Human-in-the-Loop JIT authority component and cannot be modified by autonomous agents."
            ),
        )

    if _is_self_protected_key(key, real_path):
        if int(user_tier) >= 5 and _check_jit_elevation(elevation_token):
            return True, "ALLOWED_JIT_ELEVATED", ""
        return (
            False,
            "DENIED_SELF_PROTECTION",
            (
                "[RAUGUS SELF-PROTECTION FIREWALL]\n"
                f"Direct modification of key '{key}' is blocked by design.\n\n"
                "WHY THIS WAS BLOCKED (ZERO-TRUST INTEGRITY):\n"
                "The Raugus Resolver is intentionally built to block direct modification of core security "
                "components to prevent unauthorized parameter overrides, circular tampering, and prompt escalation.\n\n"
                "REQUIRED CORRECTION (HUMAN IN THE LOOP):\n"
                "1. Super Admin JIT Elevation (5-Minute Window): Ask the human Super Admin to click '🔓 Elevate JIT (5m)' in the DevCore UI "
                "or run `python3 security/jit_elevation.py --mint` in their terminal to temporarily unlock core security files.\n"
                "2. Pull from Git: Alternatively, core security updates can be committed and pulled via Git.\n"
                "3. Information Protection: Physical host filesystem paths and internal configuration locations are shielded."
            ),
        )

    bname = os.path.basename(real_path or "").lower()
    if bname in ("exam_application.html", "exam_builder.html", "exam_application.md") or ".plugins.exam_application." in key:
        return (
            False,
            "DENIED_READ_ONLY",
            f"Key '{key}' is a Read-Only Exam Application blueprint and cannot be modified.",
        )

    if sym_entry and sym_entry.get("locked") is True:
        return (
            False,
            "DENIED_SYMBOL_LOCKED",
            f"Symbol key '{key}' is explicitly AST-locked in the Raugus Map.",
        )

    if _is_engine_module_path(real_path) and int(user_tier) >= 5:
        return True, "ALLOWED_HOT_PATCH", ""

    mod_perms = mod_entry.get("permissions", {})
    if mod_perms.get("write") is False:
        return (
            False,
            "DENIED_READ_ONLY",
            f"Key '{key}' is marked Read-Only in the Raugus Map.",
        )

    if sym_entry and sym_entry.get("permissions", {}).get("write") is False:
        return (
            False,
            "DENIED_SYMBOL_LOCKED",
            f"Symbol key '{key}' is AST-locked (Read-Only) in the Raugus Map.",
        )

    return True, "ALLOWED_WORKSPACE", ""


def _resolve_module_and_symbol(key: str):
    """
    Splits a VFS key into (module_key, symbol_name_or_None) and looks up the entries
    in RaugusResolver.phonebook.
    """
    resolver = _get_resolver()
    if "::" in key:
        module_key, symbol_name = key.split("::", 1)
    else:
        module_key, symbol_name = key, None

    mod_entry = resolver.phonebook.get(module_key)
    sym_entry = resolver.phonebook.get(key) if symbol_name else None
    return resolver, module_key, symbol_name, mod_entry, sym_entry


@mcp.tool()
def search_keys(query: str, entry_type: str = "all", user_tier: int = 5, limit: int = 30) -> str:
    """
    Search the Raugus Map by keyword across VFS keys (files, directories, and AST symbols).
    Returns ONLY opaque VFS keys, types, required tiers, and permission flags.
    Physical file paths are never revealed.
    """
    resolver = _get_resolver()
    q = (query or "").strip().lower()
    etype = (entry_type or "all").strip().lower()
    max_items = max(1, min(int(limit or 30), 100))

    matches = []
    for alias, data in resolver.phonebook.items():
        req_tier = int(data.get("required_tier", 5))
        if int(user_tier) < req_tier:
            continue

        item_type = data.get("type", "file")
        if etype != "all":
            if etype == "symbol":
                if item_type not in ("symbol", "function", "async_function", "class", "method", "async_method", "variable"):
                    continue
            elif item_type != etype:
                continue

        sym_name = data.get("symbol_name", "")
        if q and q not in alias.lower() and q not in sym_name.lower():
            continue

        real_p = data.get("real_path", "")
        is_sens = bool(data.get("sensitive") is True or resolver.is_sensitive_path(real_p))
        record = {
            "key": alias,
            "type": item_type,
            "required_tier": req_tier,
            "permissions": data.get("permissions", {}),
            "sensitive": is_sens,
        }
        if sym_name:
            record["symbol_name"] = sym_name
        matches.append(record)
        if len(matches) >= max_items:
            break

    return _json_response({
        "status": "GRANTED",
        "query": query,
        "user_tier": int(user_tier),
        "count": len(matches),
        "keys": matches,
    })


@mcp.tool()
def list_module_keys(module_key: str, user_tier: int = 5) -> str:
    """
    Given a module VFS key (e.g. 'devcore.core.routes.system.py'), verifies RBAC rules
    and returns all function, class, variable, and section VFS keys ('<module_key>::<symbol>')
    inside that module without revealing physical file paths.
    """
    resolver, mod_key, _, mod_entry, _ = _resolve_module_and_symbol(module_key)
    if not mod_entry:
        return _json_response({
            "status": "DENIED",
            "key": module_key,
            "reason": f"Key '{module_key}' does not exist in the Raugus Map.",
        })

    req_tier = int(mod_entry.get("required_tier", 5))
    if int(user_tier) < req_tier:
        return _json_response({
            "status": "DENIED",
            "key": mod_key,
            "reason": f"Access Denied: Tier {req_tier} clearance required (caller has Tier {user_tier}).",
        })

    real_path = resolver.get_path(mod_key, int(user_tier))
    if mod_entry.get("sensitive") is True or resolver.is_sensitive_path(real_path):
        return _json_response({
            "status": "DENIED_SENSITIVE_VAULT",
            "key": mod_key,
            "reason": "Key resides inside the Raugus Sensitive Vault. Raw symbol listing is blocked.",
        })

    perms = mod_entry.get("permissions", {})
    if perms.get("read") is False:
        return _json_response({
            "status": "DENIED",
            "key": mod_key,
            "reason": f"Read permission is disabled for key '{mod_key}'.",
        })

    if not real_path or not os.path.isfile(real_path):
        return _json_response({
            "status": "DENIED",
            "key": mod_key,
            "reason": f"Key '{mod_key}' is not a readable module.",
        })

    try:
        with open(real_path, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        return _json_response({"status": "ERROR", "key": mod_key, "reason": str(e)})

    symbol_keys = []
    if real_path.endswith(".py"):
        ast_map = _extract_ast_nodes(source)
        for sym_name, (kind, s_line, e_line) in ast_map.items():
            full_sym_key = f"{mod_key}::{sym_name}"
            mapped_sym = resolver.phonebook.get(full_sym_key, {})
            sym_perms = mapped_sym.get("permissions", perms)
            w_ok, w_mode, _ = _is_writable_via_resolver(full_sym_key, real_path, mod_entry, mapped_sym, int(user_tier))
            symbol_keys.append({
                "key": full_sym_key,
                "symbol_name": sym_name,
                "kind": kind,
                "id": mapped_sym.get("id"),
                "content_hash": mapped_sym.get("content_hash", ""),
                "line_span": max(1, e_line - s_line + 1),
                "permissions": {
                    "read": bool(sym_perms.get("read", True)),
                    "write": w_ok,
                    "delivery_mode": w_mode if w_ok else "READ_ONLY",
                },
            })
    elif real_path.endswith((".md", ".plan")):
        prefix_colon = mod_key + "::"
        for k, sec_data in resolver.phonebook.items():
            if k.startswith(prefix_colon) and sec_data.get("type") == "section":
                sec_name = sec_data.get("symbol_name", k[len(prefix_colon):])
                s_l = int(sec_data.get("start_line", 1))
                e_l = int(sec_data.get("end_line", s_l))
                sec_perms = sec_data.get("permissions", perms)
                w_ok, w_mode, _ = _is_writable_via_resolver(k, real_path, mod_entry, sec_data, int(user_tier))
                symbol_keys.append({
                    "key": k,
                    "symbol_name": sec_name,
                    "kind": "section",
                    "id": sec_data.get("id"),
                    "content_hash": sec_data.get("content_hash", ""),
                    "line_span": max(1, e_l - s_l + 1),
                    "permissions": {
                        "read": bool(sec_perms.get("read", True)),
                        "write": w_ok,
                        "delivery_mode": w_mode if w_ok else "READ_ONLY",
                    },
                })

    m_w_ok, m_w_mode, _ = _is_writable_via_resolver(mod_key, real_path, mod_entry, None, int(user_tier))
    return _json_response({
        "status": "GRANTED",
        "module_key": mod_key,
        "required_tier": req_tier,
        "module_permissions": {
            "read": bool(perms.get("read", True)),
            "write": m_w_ok,
            "delivery_mode": m_w_mode if m_w_ok else "READ_ONLY",
        },
        "symbol_count": len(symbol_keys),
        "symbols": symbol_keys,
    })


@mcp.tool()
def read_by_key(key: str, user_tier: int = 5) -> str:
    """
    Access a file, function, class, variable, or section strictly by its Raugus VFS Key
    (e.g. 'devcore.core.routes.system.py::reload_system' or 'devcore.core.project_manager.py').
    Verifies all Raugus Map rules and returns ONLY the granted code/value result without revealing file paths.
    """
    resolver, mod_key, symbol_name, mod_entry, sym_entry = _resolve_module_and_symbol(key)
    target_entry = sym_entry or mod_entry
    if not target_entry or not mod_entry:
        return _json_response({
            "status": "DENIED",
            "key": key,
            "reason": f"Key '{key}' does not exist in the Raugus Map.",
        })

    req_tier = max(int(mod_entry.get("required_tier", 5)), int(target_entry.get("required_tier", 5)))
    if int(user_tier) < req_tier:
        logging.warning(f"Tier {user_tier} denied read_by_key on Tier {req_tier} key '{key}'")
        return _json_response({
            "status": "DENIED",
            "key": key,
            "reason": f"Access Denied: Tier {req_tier} clearance required (caller has Tier {user_tier}).",
        })

    real_path = resolver.get_path(mod_key, int(user_tier))

    # Sensitive Vault Check: Never return raw source from sensitive keys; return sanitized digest only
    if (
        mod_entry.get("sensitive") is True
        or target_entry.get("sensitive") is True
        or resolver.is_sensitive_path(real_path)
    ):
        try:
            from security.local_brain_broker import generate_digest
            digest = generate_digest(real_path)
            digest.pop("target", None)
        except Exception as e:
            digest = {"status": "BROKER_ERROR", "error": str(e)}
        return _json_response({
            "status": "GRANTED_SANITIZED_DIGEST_ONLY",
            "key": key,
            "sensitive": True,
            "result": digest,
        })

    mod_perms = mod_entry.get("permissions", {})
    sym_perms = target_entry.get("permissions", mod_perms)
    if mod_perms.get("read") is False or sym_perms.get("read") is False:
        return _json_response({
            "status": "DENIED",
            "key": key,
            "reason": f"Read permission is disabled for key '{key}'.",
        })

    if not real_path or not (os.path.isfile(real_path) or os.path.isdir(real_path)):
        return _json_response({
            "status": "DENIED",
            "key": key,
            "reason": f"Key '{key}' does not resolve to a readable asset.",
        })

    w_ok, w_mode, _ = _is_writable_via_resolver(key, real_path, mod_entry, sym_entry, int(user_tier))

    if mod_entry.get("type") == "directory" or os.path.isdir(real_path):
        prefix_dot = mod_key + "."
        prefix_colon = mod_key + "::"
        child_keys = [k for k in resolver.phonebook if k != mod_key and (k.startswith(prefix_dot) or k.startswith(prefix_colon))]
        return _json_response({
            "status": "GRANTED",
            "key": mod_key,
            "type": "directory",
            "child_count": len(child_keys),
            "children": child_keys[:100],
            "permissions": {
                "read": True,
                "write": w_ok,
                "delivery_mode": w_mode if w_ok else "READ_ONLY",
            },
            "result": f"Directory container with {len(child_keys)} registered children.",
        })

    try:
        with open(real_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        full_source = "".join(lines)
    except Exception as e:
        return _json_response({"status": "ERROR", "key": key, "reason": str(e)})

    if symbol_name:
        ast_map = _extract_ast_nodes(full_source) if real_path.endswith(".py") else {}
        if symbol_name in ast_map:
            kind, s_line, e_line = ast_map[symbol_name]
        elif sym_entry and "start_line" in sym_entry and "end_line" in sym_entry:
            kind = sym_entry.get("type", "section" if real_path.endswith((".md", ".plan")) else "symbol")
            s_line = int(sym_entry["start_line"])
            e_line = int(sym_entry["end_line"])
        else:
            return _json_response({
                "status": "DENIED",
                "key": key,
                "reason": f"Symbol or section '{symbol_name}' was not found inside module key '{mod_key}'.",
            })

        snippet = "".join(lines[max(0, s_line - 1): e_line])
        content_hash = sym_entry.get("content_hash") if sym_entry else None
        if not content_hash:
            content_hash = hashlib.sha256(snippet.encode("utf-8")).hexdigest()[:12]

        return _json_response({
            "status": "GRANTED",
            "key": key,
            "module_key": mod_key,
            "symbol_name": symbol_name,
            "kind": kind,
            "id": sym_entry.get("id") if sym_entry else None,
            "content_hash": content_hash,
            "start_line": s_line,
            "end_line": e_line,
            "line_count": max(1, e_line - s_line + 1),
            "permissions": {
                "read": True,
                "write": w_ok,
                "delivery_mode": w_mode if w_ok else "READ_ONLY",
            },
            "result": _scrub_paths(snippet),
        })

    ast_map = _extract_ast_nodes(full_source) if real_path.endswith(".py") else {}
    if ast_map:
        child_keys = [f"{mod_key}::{name}" for name in ast_map.keys()]
    else:
        prefix_colon = mod_key + "::"
        child_keys = [k for k in resolver.phonebook if k.startswith(prefix_colon)]

    file_hash = mod_entry.get("content_hash")
    if not file_hash:
        file_hash = hashlib.sha256(full_source.encode("utf-8")).hexdigest()[:12]

    return _json_response({
        "status": "GRANTED",
        "key": mod_key,
        "type": mod_entry.get("type", "file"),
        "id": mod_entry.get("id"),
        "content_hash": file_hash,
        "line_count": len(lines),
        "symbol_keys": child_keys,
        "permissions": {
            "read": True,
            "write": w_ok,
            "delivery_mode": w_mode if w_ok else "READ_ONLY",
        },
        "result": _scrub_paths(full_source),
    })


@mcp.tool()
def get_block_by_tag(tag_or_id: str, user_tier: int = 5) -> str:
    """
    Resolves an AST symbol or Markdown section block by its persistent invariant UUID ('id')
    or symbol/section tag name (e.g. 'SEC_01_OVERVIEW' or 'reload_system'),
    enforcing RBAC tier clearance without exposing file paths.
    """
    resolver = _get_resolver()
    try:
        entry = resolver.get_block_by_tag(tag_or_id, int(user_tier))
        if not entry:
            return _json_response({
                "status": "NOT_FOUND",
                "tag_or_id": tag_or_id,
                "reason": f"No block found with tag or id '{tag_or_id}'."
            })
        k = entry.get("key", "")
        return read_by_key(k, user_tier=int(user_tier))
    except PermissionError as pe:
        return _json_response({
            "status": "DENIED",
            "tag_or_id": tag_or_id,
            "reason": str(pe)
        })
    except Exception as e:
        return _json_response({
            "status": "ERROR",
            "tag_or_id": tag_or_id,
            "reason": str(e)
        })

@mcp.tool()
def write_by_key(key: str, new_code: str, user_tier: int = 5, elevation_token: str = "") -> str:
    """
    Modify a specific function, class, variable ('module_key::symbol_name'), or module ('module_key')
    strictly via its Raugus VFS Key without exposing physical file paths.
    Enforces RBAC tier, Self-Protection locks, Read-Only blueprints, AST symbol locks, and syntax validation,
    and automatically stages & promotes live engine updates through the Zero-Downtime Hot-Patch sequence.
    When modifying a core security guard file, requires an active 5-minute Human-in-the-Loop Super Admin JIT Elevation Token/Lease.
    """
    resolver, mod_key, symbol_name, mod_entry, sym_entry = _resolve_module_and_symbol(key)
    if not mod_entry:
        return _json_response({
            "status": "DENIED",
            "key": key,
            "reason": f"Module key '{mod_key}' does not exist in the Raugus Map.",
        })

    req_tier = int(mod_entry.get("required_tier", 5))
    if sym_entry:
        req_tier = max(req_tier, int(sym_entry.get("required_tier", req_tier)))

    if int(user_tier) < req_tier:
        logging.warning(f"Tier {user_tier} denied write_by_key on Tier {req_tier} key '{key}'")
        return _json_response({
            "status": "DENIED",
            "key": key,
            "reason": f"Access Denied: Tier {req_tier} clearance required (caller has Tier {user_tier}).",
        })

    real_path = resolver.get_path(mod_key, int(user_tier))

    # 1. Sensitive Vault & OneDrive Lock
    if (
        mod_entry.get("sensitive") is True
        or (sym_entry and sym_entry.get("sensitive") is True)
        or resolver.is_sensitive_path(real_path)
    ):
        return _json_response({
            "status": "DENIED_SENSITIVE_VAULT",
            "key": key,
            "reason": f"Key '{key}' resides inside the Raugus Sensitive Vault and is strictly protected against modification.",
        })

    # 2. Self-Protection, Read-Only Blueprint, and AST Symbol Lock Evaluation
    w_allowed, w_status, w_reason = _is_writable_via_resolver(
        key, real_path, mod_entry, sym_entry, int(user_tier), elevation_token=elevation_token
    )
    if not w_allowed:
        return _json_response({
            "status": w_status,
            "key": key,
            "reason": w_reason,
        })

    if not real_path or not os.path.isfile(real_path):
        return _json_response({
            "status": "DENIED",
            "key": key,
            "reason": f"Key '{mod_key}' does not resolve to an existing file.",
        })

    try:
        from security.mantrap import SemanticMantrap
        with SemanticMantrap.execution_chamber(real_path, "Raugus_MCP_Write"):
            with open(real_path, "r", encoding="utf-8") as f:
                orig_lines = f.readlines()
            orig_source = "".join(orig_lines)
            orig_ast = _extract_ast_nodes(orig_source)

            clean_new = new_code if new_code.endswith("\n") else (new_code + "\n")

            if symbol_name:
                if symbol_name in orig_ast:
                    _, s_line, e_line = orig_ast[symbol_name]
                    full_sym_key = f"{mod_key}::{symbol_name}"
                    if resolver.phonebook.get(full_sym_key, {}).get("locked") is True:
                        return _json_response({
                            "status": "DENIED_SYMBOL_LOCKED",
                            "key": key,
                            "reason": f"Symbol '{symbol_name}' is AST-locked (Read-Only).",
                        })
                    candidate_lines = orig_lines[: s_line - 1] + [clean_new] + orig_lines[e_line:]
                else:
                    sep = ["\n"] if (orig_lines and not orig_lines[-1].endswith("\n")) else ["\n"]
                    candidate_lines = orig_lines + sep + [clean_new]
                candidate_source = "".join(candidate_lines)
            else:
                for s_name, (_, s_l, e_l) in orig_ast.items():
                    s_key = f"{mod_key}::{s_name}"
                    if resolver.phonebook.get(s_key, {}).get("locked") is True:
                        orig_sym_text = "".join(orig_lines[s_l - 1: e_l]).strip()
                        if orig_sym_text not in clean_new:
                            return _json_response({
                                "status": "DENIED_SYMBOL_LOCKED",
                                "key": s_key,
                                "reason": f"Module write rejected: locked symbol '{s_name}' cannot be altered or removed.",
                            })
                candidate_source = clean_new

            # 3. Syntax Validation Gate (ast.parse) for Python modules
            if real_path.endswith(".py"):
                try:
                    ast.parse(candidate_source)
                except SyntaxError as se:
                    return _json_response({
                        "status": "DENIED_SYNTAX_ERROR",
                        "key": key,
                        "reason": f"Syntax validation failed (line {se.lineno}): {se.msg}",
                    })

            # 4. Route through Hot-Patch Staging for Live Backend Engine Modules
            if _is_engine_module_path(real_path):
                basename = os.path.basename(real_path)
                patch_dir = os.path.join(DEVCORE_ROOT, "core", "patches")
                os.makedirs(patch_dir, exist_ok=True)
                staged_path = os.path.join(patch_dir, basename)
                with open(staged_path, "w", encoding="utf-8") as pf:
                    pf.write(candidate_source)

                from core.bootstrap_gateway import run_preflight_checks
                report = run_preflight_checks(base_dir=DEVCORE_ROOT, spawn_agent=False, quiet=True)
                if not report.get("success") or basename not in report.get("promoted_patches", []):
                    return _json_response({
                        "status": "DENIED_HOT_PATCH_FAILED",
                        "key": key,
                        "reason": "Staged update failed hot-patch verification and was rolled back.",
                    })

                try:
                    from core.session_manager import _sync_live_blueprint_routes
                    _sync_live_blueprint_routes()
                except Exception:
                    pass
                delivery_mode = "JIT_HOT_PATCH_PROMOTED" if w_status == "ALLOWED_JIT_ELEVATED" else "HOT_PATCH_PROMOTED"
            else:
                if w_status == "ALLOWED_JIT_ELEVATED":
                    backup_dir = os.path.join(DEVCORE_ROOT, "core", "backups")
                    os.makedirs(backup_dir, exist_ok=True)
                    shutil.copy2(real_path, os.path.join(backup_dir, os.path.basename(real_path)))
                with open(real_path, "w", encoding="utf-8") as wf:
                    wf.write(candidate_source)
                delivery_mode = "JIT_ELEVATED_UPDATED" if w_status == "ALLOWED_JIT_ELEVATED" else "WORKSPACE_UPDATED"

            # Incrementally sync to raugus_map.json on disk
            try:
                from security.raugus_sync import sync_path
                sync_path(real_path)
            except Exception:
                pass

            # Refresh in-memory symbol coordinates for this module
            updated_ast = _extract_ast_nodes(candidate_source)
            mod_perms = mod_entry.get("permissions", {})
            for s_name, (s_kind, s_l, e_l) in updated_ast.items():
                s_key = f"{mod_key}::{s_name}"
                if s_key in resolver.phonebook:
                    resolver.phonebook[s_key]["start_line"] = s_l
                    resolver.phonebook[s_key]["end_line"] = e_l
                    resolver.phonebook[s_key]["type"] = s_kind
                else:
                    resolver.phonebook[s_key] = {
                        "real_path": real_path,
                        "type": s_kind,
                        "symbol_name": s_name,
                        "start_line": s_l,
                        "end_line": e_l,
                        "required_tier": req_tier,
                        "permissions": dict(mod_perms),
                    }

            return _json_response({
                "status": "GRANTED",
                "key": key,
                "module_key": mod_key,
                "delivery_mode": delivery_mode,
                "updated_symbol_keys": [f"{mod_key}::{n}" for n in updated_ast.keys()],
            })
    except Exception as e:
        logging.error(f"write_by_key error on {key}: {traceback.format_exc()}")
        return _json_response({"status": "ERROR", "key": key, "reason": str(e)})


@mcp.tool()
def refresh_key_map(user_tier: int = 5) -> str:
    """
    Re-indexes workspace AST symbol keys and 64-bit hardware inodes in the Raugus Map
    and reloads the in-memory phonebook. Returns only key counts without revealing file paths.
    """
    if int(user_tier) < 5:
        return _json_response({
            "status": "DENIED",
            "reason": "Access Denied: Tier 5 clearance required to refresh the Raugus Map.",
        })
    try:
        import generate_raugusmap
        map_path = os.path.join(DEVCORE_ROOT, "security", "raugus_map.json")
        prev_map = {}
        if os.path.exists(map_path):
            with open(map_path, "r", encoding="utf-8") as pf:
                prev_map = json.load(pf)
        new_map = generate_raugusmap.generate_raugusmap(DEVCORE_ROOT, existing_map=prev_map)
        with open(map_path, "w", encoding="utf-8") as wf:
            json.dump(new_map, wf, indent=4)
        resolver = _get_resolver()
        resolver._load_phonebook()
        total = len(resolver.phonebook)
        counts = {}
        for v in resolver.phonebook.values():
            t = v.get("type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return _json_response({
            "status": "GRANTED",
            "total_keys": total,
            "counts_by_type": counts,
        })
    except Exception as e:
        return _json_response({"status": "ERROR", "reason": str(e)})



@mcp.tool()
def workspace_pipeline(
    action: str = "status",
    commit_msg: str = "",
    no_push: bool = False,
    commit_devcore: bool = False,
    user_tier: int = 5,
) -> str:
    """
    Executes the unified cross-repository workspace pipeline (Central_Docs, e_profile, DevCore)
    in a single tool call to eliminate repetitive commands and conserve tokens.

    Actions:
    - 'status': Consolidated git status across Central_Docs, e_profile, and DevCore.
    - 'audit': Runs documentation quality, category structure, and security audits across repositories.
    - 'commit': Executes full validation, syncs Central_Docs to e_profile, and commits/pushes atomically.
    """
    if int(user_tier) < 3:
        return _json_response({
            "status": "DENIED",
            "reason": "Access Denied: Tier 3 clearance required to invoke the workspace pipeline.",
        })

    pipeline_script = os.path.join(DEVCORE_ROOT, "scripts", "workspace_pipeline.py")
    if not os.path.exists(pipeline_script):
        pipeline_script = "/mnt/c/Users/michael/Documents/Central_Docs/scripts/workspace_pipeline.py"

    cmd = [sys.executable, pipeline_script]
    if action == "status":
        cmd.append("--status")
    elif action == "audit":
        cmd.append("--audit")
    elif action == "commit":
        if not commit_msg:
            return _json_response({
                "status": "ERROR",
                "reason": "Parameter 'commit_msg' is required for action 'commit'.",
            })
        cmd.extend(["--commit", commit_msg])
        if no_push:
            cmd.append("--no-push")
        if commit_devcore:
            cmd.append("--commit-devcore")
    else:
        return _json_response({
            "status": "ERROR",
            "reason": f"Unknown action '{action}'. Supported actions: 'status', 'audit', 'commit'.",
        })

    try:
        import subprocess
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
        )
        scrubbed = _scrub_paths(proc.stdout)
        return _json_response({
            "status": "GRANTED" if proc.returncode == 0 else "FAILED",
            "action": action,
            "exit_code": proc.returncode,
            "output": scrubbed.strip(),
        })
    except subprocess.TimeoutExpired:
        return _json_response({
            "status": "TIMEOUT",
            "action": action,
            "reason": "Pipeline execution timed out after 180 seconds.",
        })
    except Exception as e:
        return _json_response({
            "status": "ERROR",
            "action": action,
            "reason": str(e),
        })


if __name__ == "__main__":
    try:
        mcp.run()
    except Exception as e:
        logging.critical(f"Raugus Resolver MCP Server crashed: {traceback.format_exc()}")
