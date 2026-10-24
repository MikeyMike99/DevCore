import sys
import json
import os
import ast

def get_ast_symbols(source_code):
    symbols = {}
    try:
        tree = ast.parse(source_code)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Record the start and end lines of the function
                symbols[node.name] = (node.lineno, getattr(node, 'end_lineno', node.lineno))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols[target.id] = (node.lineno, getattr(node, 'end_lineno', node.lineno))
    except SyntaxError:
        pass
    return symbols


def log_violation(tool_name, target, reason):
    try:
        devcore_root = "/mnt/c/Users/michael/Documents/DevCore"
        if devcore_root not in sys.path:
            sys.path.insert(0, devcore_root)
        from security.central_logger import log_siem_event
        from security.swarm_telemetry import SwarmFlowLogger

        log_siem_event(
            level="ERROR",
            message=f"[SECURITY_AUDIT] Raugus PreToolUse Hook intercepted and denied action. Tool: {tool_name}, Target: {target}, Reason: {reason}",
            module_name="raugus_hook",
            logger_name="security.raugus_hook",
        )
        SwarmFlowLogger.log_intrusion_alert(
            modder_id="MainCloudBrain",
            agent_id="PreToolUse_Hook",
            target_namespace=f"{tool_name}:{target}",
            reason=reason,
        )
    except Exception:
        pass

_HOOK_DEVCORE_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

IMMUTABLE_JIT_BASENAMES = {
    "jit_elevation.py",
    ".jit_elevation_lease.json",
    ".devcore_master.key",
}

PROTECTED_SECURITY_FILES = {
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/.agents/raugus_hook.py"),
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/.agents/raugus_post_tool.py"),
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/.agents/hooks.json"),
    os.path.abspath(os.path.expanduser("~/.gemini/config/hooks.json")),
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/.gemini/settings.json"),
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/security/local_brain_broker.py"),
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/security/raugus_resolver.py"),
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/security/raugus_sync.py"),
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/security/raugus_map.json"),
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/generate_raugusmap.py"),
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/security/tool_security_auditor.py"),
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/.agents/plugins/raugus_resolver/server.py"),
    os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/.agents/plugins/raugus_resolver/mcp_config.json"),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, ".agents", "raugus_hook.py")),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, ".agents", "raugus_post_tool.py")),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, ".agents", "hooks.json")),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, ".gemini", "settings.json")),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, "security", "local_brain_broker.py")),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, "security", "raugus_resolver.py")),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, "security", "raugus_sync.py")),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, "security", "raugus_map.json")),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, "generate_raugusmap.py")),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, "security", "tool_security_auditor.py")),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, ".agents", "plugins", "raugus_resolver", "server.py")),
    os.path.abspath(os.path.join(_HOOK_DEVCORE_ROOT, ".agents", "plugins", "raugus_resolver", "mcp_config.json")),
}

FILE_AND_SEARCH_TOOLS = {
    "view_file",
    "view_file_outline",
    "view_code_item",
    "view_content_chunk",
    "write_to_file",
    "replace_file_content",
    "edit_lines",
    "code_action",
    "file_change",
    "write_blob",
    "mcp_tool",
    "call_mcp_tool",
    "grep_search",
    "find_by_name",
    "find",
    "list_dir",
    "list_directory",
    "delete_directory",
    "move",
    "read_url_content",
}

COMMAND_TOOLS = {
    "run_command",
    "shell_exec",
    "send_command_input",
}

WRITE_TOOLS = {
    "write_to_file",
    "replace_file_content",
    "edit_lines",
    "code_action",
    "file_change",
    "write_blob",
    "mcp_tool",
    "call_mcp_tool",
}


def _is_jit_elevated(args: dict) -> bool:
    """
    Checks if a valid Human-in-the-Loop Super Admin JIT Elevation Lease/Token is currently active.
    """
    try:
        for root_cand in (_HOOK_DEVCORE_ROOT, "/mnt/c/Users/michael/Documents/DevCore"):
            if os.path.isdir(root_cand) and root_cand not in sys.path:
                sys.path.insert(0, root_cand)
        from security.jit_elevation import extract_token_from_text, verify_jit_elevation

        raw_blob = json.dumps(args, default=str) if args else ""
        cand_tok = (
            (args or {}).get("elevation_token")
            or extract_token_from_text(raw_blob)
            or None
        )
        ver = verify_jit_elevation(candidate_token=cand_tok)
        return bool(ver.get("valid") is True)
    except Exception:
        return False


def check_self_protection(tool_name, args):
    """
    Prevents the AI agent from modifying, renaming, deleting, or overwriting
    the security hook, hooks.json, Raugus map, resolver, or Local Brain Broker via file tools or bash commands,
    unless a valid Human-in-the-Loop Super Admin JIT Elevation Lease/Token is active.
    Strictly and unconditionally blocks AI self-minting or tampering with jit_elevation.py / .devcore_master.key.
    """
    import re

    # 1. Unconditional Anti-Self-Minting & Master Key Guard (Never lifted by JIT)
    if tool_name == "read_url_content":
        url_val = str(args.get("Url") or "")
        if "/api/security/jit-elevate" in url_val or "/api/security/jit-revoke" in url_val:
            return (
                "Raugus Anti-Self-Minting Firewall: Autonomous agents are strictly forbidden from "
                "invoking Human-in-the-Loop JIT elevation endpoints."
            )

    if tool_name in WRITE_TOOLS:
        cand = args.get("TargetFile") or args.get("target_file") or args.get("AbsolutePath")
        if cand:
            bname = os.path.basename(str(cand).replace("\\", "/"))
            if bname in IMMUTABLE_JIT_BASENAMES:
                return (
                    f"Raugus Anti-Self-Minting Firewall: '{bname}' is an immutable hardware/JIT authority "
                    "file and cannot be modified even during Super Admin elevation."
                )
            for resolved in (os.path.abspath(cand), os.path.realpath(cand)):
                if resolved in PROTECTED_SECURITY_FILES:
                    if _is_jit_elevated(args):
                        try:
                            import shutil
                            bdir = os.path.join(_HOOK_DEVCORE_ROOT, "core", "backups")
                            os.makedirs(bdir, exist_ok=True)
                            if os.path.exists(resolved):
                                shutil.copy2(resolved, os.path.join(bdir, os.path.basename(resolved)))
                        except Exception:
                            pass
                        return None
                    return (
                        f"Raugus Self-Protection Firewall: Core security file '{resolved}' is strictly "
                        "locked against AI modification, rename, or overwrite. "
                        "To temporarily lift this lock for 5 minutes (Human-in-the-Loop), the Super Admin "
                        "must run `python3 security/jit_elevation.py --mint` or click '🔓 Elevate JIT (5m)' in the DevCore UI."
                    )
    elif tool_name in COMMAND_TOOLS:
        cmd_line = args.get("CommandLine") or args.get("Input") or ""
        if (
            "/api/security/jit-elevate" in cmd_line
            or "/api/security/jit-revoke" in cmd_line
            or ".jit_elevation_lease.json" in cmd_line
            or ".devcore_master.key" in cmd_line
            or ("jit_elevation.py" in cmd_line and any(f in cmd_line for f in ("--mint", "--revoke", "mint_jit_token", "revoke_jit_token")))
        ):
            return (
                "Raugus Anti-Self-Minting Firewall: Autonomous agents are strictly forbidden from "
                "minting, revoking, or modifying Human-in-the-Loop JIT elevation tokens or hardware master keys."
            )
        if "jit_elevation.py" in cmd_line and any(x in cmd_line for x in ["sed ", "mv ", "rm ", "cp ", ">", "tee "]):
            return (
                "Raugus Anti-Self-Minting Firewall: Modifying or overwriting jit_elevation.py via shell commands is strictly forbidden."
            )
        if "tool_security_auditor.py" in cmd_line and not any(x in cmd_line for x in ["sed ", "mv ", "rm ", "cp ", ">"]):
            return None
        protected_basenames = (
            "raugus_hook.py",
            "hooks.json",
            "local_brain_broker.py",
            "raugus_resolver.py",
            "raugus_map.json",
            "generate_raugusmap.py",
            "tool_security_auditor.py",
            ".gemini/settings.json",
        )
        destructive_patterns = (
            r"\bsed\b", r"\bawk\b", r"\bmv\b", r"\brm\b", r"\bcp\b",
            r"\btee\b", r"\bchmod\b", r"\bchown\b", r"\bchattr\b",
            r"\bicacls", r"\btruncate\b", r"\bdd\b", r"shutil\.",
            r"os\.rename", r"os\.remove", r"os\.unlink", r">",
        )
        if any(pb in cmd_line for pb in protected_basenames):
            if any(re.search(dp, cmd_line) for dp in destructive_patterns):
                if _is_jit_elevated(args):
                    return None
                return (
                    "Raugus Self-Protection Firewall: Modifying, renaming, or overwriting core security "
                    "guard files via shell commands is strictly forbidden without an active Super Admin JIT Elevation Token."
                )
    return None


def find_sensitive_target(tool_name, args, r_map):
    """
    Checks if a tool call targets a path marked 'sensitive': true in raugus_map.json,
    inside plugins/exam_application/content, or inside any automatically detected
    OneDrive sync root (regardless of what the OneDrive folder is named or whether
    accessed via wildcards, relative paths, string-splitting, URL hex encoding, or two-step scripts).
    Allows authorized single-command calls to local_brain_broker.py.
    """
    import glob
    import re
    devcore_root = "/mnt/c/Users/michael/Documents/DevCore"
    if devcore_root not in sys.path:
        sys.path.insert(0, devcore_root)

    try:
        from security.raugus_resolver import (
            discover_onedrive_roots,
            is_path_in_onedrive,
            is_sensitive_inode,
            normalize_cross_platform_path,
        )
    except Exception:
        def normalize_cross_platform_path(p):
            return os.path.abspath(p) if p else ""
        def discover_onedrive_roots():
            return []
        def is_path_in_onedrive(p):
            return None
        def is_sensitive_inode(p, m=None):
            return False

    sensitive_dirs = []
    sensitive_files = set()
    for alias, data in r_map.items():
        if data.get("sensitive") is True:
            rp = data.get("real_path", "")
            if rp:
                abs_rp = normalize_cross_platform_path(rp)
                if data.get("type") == "directory" or os.path.isdir(abs_rp):
                    if abs_rp not in sensitive_dirs:
                        sensitive_dirs.append(abs_rp)
                else:
                    sensitive_files.add(abs_rp)

    # Always ensure exam_application/content and all discovered OneDrive roots are registered
    default_exam_vault = os.path.abspath("/mnt/c/Users/michael/Documents/DevCore/plugins/exam_application/content")
    if default_exam_vault not in sensitive_dirs:
        sensitive_dirs.append(default_exam_vault)

    for od_root in discover_onedrive_roots():
        if od_root not in sensitive_dirs:
            sensitive_dirs.append(od_root)

    def _decode_hex_url(s):
        if not s or "%" not in s:
            return s
        return re.sub(r"%([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)

    def _is_path_sensitive(cand_path):
        if not cand_path:
            return None
        cand_str = _decode_hex_url(str(cand_path))
        if cand_str.startswith("file://"):
            cand_str = cand_str[7:]
        elif "path=" in cand_str:
            cand_str = cand_str.split("path=", 1)[-1].split("&", 1)[0]
        norm_cand = normalize_cross_platform_path(cand_str)
        for resolved in (norm_cand, os.path.realpath(norm_cand)):
            if resolved in sensitive_files:
                return resolved
            for sdir in sensitive_dirs:
                if resolved == sdir or resolved.startswith(sdir + os.sep):
                    return resolved
            od_hit = None
            if od_hit:
                return od_hit
            if is_sensitive_inode(resolved, r_map):
                return resolved
        return None

    def _deobfuscate_and_check_text(raw_text):
        if not raw_text:
            return None
        decoded = _decode_hex_url(str(raw_text))
        # Collapse quote-splitting and string concatenation: 'One' + 'Drive' -> OneDrive
        collapsed = re.sub(r"['\"]\s*\+?\s*['\"]", "", decoded)
        for sdir in sensitive_dirs:
            if sdir in collapsed or sdir.lower() in collapsed.lower():
                return sdir
        if "exam_application/content" in collapsed or ("exam_application" in collapsed and "content" in collapsed):
            return default_exam_vault
        if re.search(r"/mnt/[a-z]/users/[^/\s]+/onedrive", collapsed, re.IGNORECASE) or re.search(r"[a-z]:\\users\\[^\\\s]+\\onedrive", collapsed, re.IGNORECASE):
            return sensitive_dirs[-1] if sensitive_dirs else default_exam_vault
        return None

    if tool_name in FILE_AND_SEARCH_TOOLS:
        cand = (
            args.get("AbsolutePath")
            or args.get("TargetFile")
            or args.get("target_file")
            or args.get("SearchPath")
            or args.get("SearchDirectory")
            or args.get("DirectoryPath")
            or args.get("File")
            or args.get("Url")
        )
        direct_hit = _is_path_sensitive(cand)
        if direct_hit:
            return direct_hit
        if cand:
            url_deob = _deobfuscate_and_check_text(cand)
            if url_deob:
                return url_deob

        # Prevent writing two-step sneaky scripts (.py/.sh) that target sensitive vaults or OneDrive
        if tool_name in WRITE_TOOLS and cand:
            if str(cand).lower().endswith((".py", ".sh", ".bash", ".ps1")):
                code_body = (
                    args.get("CodeContent")
                    or args.get("ReplacementContent")
                    or args.get("new_code")
                    or ""
                )
                script_hit = _deobfuscate_and_check_text(code_body)
                if script_hit:
                    return script_hit
        return None

    if tool_name in COMMAND_TOOLS:
        cmd_line = args.get("CommandLine") or args.get("Input") or ""
        # Allow the Main Brain to talk to the Local Brain Broker script
        if "local_brain_broker.py" in cmd_line and not any(x in cmd_line for x in [";", "&&", "||", "|", "`", "$("]):
            return None
        cwd = args.get("Cwd", "") or "/mnt/c/Users/michael/Documents/DevCore/playground"
        hit = _is_path_sensitive(cwd)
        if hit:
            return hit

        # Block base64 decode into shell/python execution pipelines
        if re.search(r"base64\s+(-d|--decode)", cmd_line) and re.search(r"\|\s*(bash|sh|zsh|python|python3|eval)\b", cmd_line):
            return default_exam_vault

        # Check quoted strings, absolute paths, relative paths (..), and wildcard globs (*)
        decoded_cmd = _decode_hex_url(cmd_line)
        candidates = []
        for m in re.finditer(r'"([^"]+)"|\'([^\']+)\'|(/mnt/[a-zA-Z]/[^\s"\';|&]+)|([a-zA-Z]:\\[^\s"\';|&]+)|(\.\./[^\s"\';|&]+)', decoded_cmd):
            tok = next((g for g in m.groups() if g), None)
            if tok:
                candidates.append(tok)

        for tok in candidates:
            if "\n" in tok or not (len(tok) < 260):
                continue
            resolved_tok = tok
            if not os.path.isabs(tok) and not (len(tok) >= 3 and tok[1] == ":") and not tok.startswith("http"):
                resolved_tok = os.path.abspath(os.path.join(cwd, tok))
            sub_hit = _is_path_sensitive(resolved_tok)
            if sub_hit:
                return sub_hit
            # Expand shell wildcards (*, ?, [) to block glob-based renames or reads (e.g. mv ../plugins/exam_application/con*)
            if any(w in resolved_tok for w in ("*", "?", "[")):
                for g_match in glob.glob(resolved_tok):
                    g_hit = _is_path_sensitive(g_match)
                    if g_hit:
                        return g_hit

        # Deobfuscate string concatenation ('One' + 'Drive') and hex URLs in cmd_line
        deob_hit = _deobfuscate_and_check_text(decoded_cmd)
        if deob_hit:
            return deob_hit

        for sfile in sensitive_files:
            if sfile in decoded_cmd:
                return sfile

    return None


def main():
    try:
        payload = json.load(sys.stdin)
        tool_call = payload.get("toolCall", {})
        raw_name = tool_call.get("name", "")
        raw_args = tool_call.get("args", {}) or {}
        args = dict(raw_args)
        if isinstance(raw_args.get("Arguments"), dict):
            for k, v in raw_args["Arguments"].items():
                args.setdefault(k, v)
        
        tool_name = raw_name.replace("default_api:", "").lower()
        
        if tool_name in ("mcp_tool", "call_mcp_tool") and raw_args.get("ToolName") in (
            "search_keys",
            "list_module_keys",
            "read_by_key",
            "write_by_key",
            "refresh_key_map",
        ):
            print(json.dumps({"decision": "allow"}))
            return

        if tool_name not in (FILE_AND_SEARCH_TOOLS | COMMAND_TOOLS):
            print(json.dumps({"decision": "allow"}))
            return

        # --- SELF-PROTECTION LOCK ON SECURITY HOOK & BROKER FILES ---
        tamper_reason = check_self_protection(tool_name, args)
        if tamper_reason:
            target_desc = args.get("TargetFile") or args.get("target_file") or args.get("CommandLine", "security_file")
            log_violation(tool_name, target_desc, tamper_reason)
            print(json.dumps({"decision": "deny", "reason": tamper_reason}))
            return

        map_path = "/mnt/c/Users/michael/Documents/DevCore/security/raugus_map.json"
        if not os.path.exists(map_path):
            map_path = "/mnt/c/Users/michael/Documents/devcore/security/raugus_map.json"
        if not os.path.exists(map_path):
            print(json.dumps({"decision": "allow"}))
            return

        with open(map_path, 'r') as f:
            r_map = json.load(f)

        # --- SENSITIVE VAULT LOCAL BRAIN BROKER INTERCEPTION ---
        sensitive_target = find_sensitive_target(tool_name, args, r_map)
        if sensitive_target:
            try:
                sys.path.insert(0, "/mnt/c/Users/michael/Documents/DevCore")
                from security.local_brain_broker import generate_digest
                digest_obj = generate_digest(sensitive_target)
                digest_str = json.dumps(digest_obj, indent=2)
            except Exception as broker_err:
                digest_str = f'{{"status": "BROKER_ERROR", "error": "{str(broker_err)}"}}'

            reason = (
                f"[RAUGUS SENSITIVE VAULT INTERCEPTION]\n"
                f"Target '{sensitive_target}' has attribute `sensitive: true` in the Raugus Map. "
                f"Direct access by the Main Cloud Brain is blocked so raw sensitive data never leaves the local machine.\n\n"
                f"Instead, the Local Brain (Qwen2.5-1.5B CPU) automatically inspected the target and generated this sanitized digest:\n"
                f"{digest_str}\n\n"
                f"HOW TO CONVERSE WITH THE LOCAL BRAIN (DO NOT RETRY {tool_name}):\n"
                f"1. To ask the Local Brain to generate Exam JSON questions from this sensitive target:\n"
                f"   python3 /mnt/c/Users/michael/Documents/DevCore/security/local_brain_broker.py --target \"{sensitive_target}\" --mode exam --count 5 --query \"Specify question types or topics here\"\n"
                f"2. To ask the Local Brain a follow-up question or query about this target:\n"
                f"   python3 /mnt/c/Users/michael/Documents/DevCore/security/local_brain_broker.py --target \"{sensitive_target}\" --mode query --query \"Your specific question here\"\n"
                f"3. To target a specific AST symbol, section tag, or VFS key directly:\n"
                f"   python3 /mnt/c/Users/michael/Documents/DevCore/security/local_brain_broker.py --target \"<vfs_key_or_tag_id>\" --mode query --query \"...\"\n"
                f"4. To perform zero-cost AST triage and find relevant keys/tags:\n"
                f"   python3 /mnt/c/Users/michael/Documents/DevCore/security/local_brain_broker.py --target \"{sensitive_target}\" --mode triage --query \"keywords\""
            )
            log_violation(tool_name, sensitive_target, "Intercepted sensitive path and routed to Local Brain Broker.")
            print(json.dumps({"decision": "deny", "reason": reason}))
            return

        if tool_name == "write_to_file":
            target = args.get("TargetFile", "")
            if target.endswith(".md"):
                artifact_meta = args.get("ArtifactMetadata", {})
                if artifact_meta.get("RequestFeedback") is True:
                    if "plan" in target.lower():
                        print(json.dumps({"decision": "ask", "reason": "Implementation plans require manual user confirmation to proceed."}))
                        return
                    else:
                        reason = "Rule 8 Violation: RequestFeedback: true is strictly forbidden on Markdown files."
                        log_violation(tool_name, target, reason)
                        print(json.dumps({"decision": "deny", "reason": reason}))
                        return

        if tool_name in WRITE_TOOLS:
            target = args.get("TargetFile") or args.get("target_file") or args.get("AbsolutePath")
            if target:
                target = os.path.abspath(target)
                norm_t = target.replace("\\", "/")
                is_live_engine_py = (
                    norm_t.endswith(".py")
                    and (
                        "/DevCore/core/" in norm_t
                        or "/DevCore/agents/" in norm_t
                        or "/DevCore/security/" in norm_t
                    )
                    and "/DevCore/core/patches/" not in norm_t
                    and "/DevCore/core/backups/" not in norm_t
                )
                if is_live_engine_py:
                    bname = os.path.basename(target)
                    if target in PROTECTED_SECURITY_FILES and _is_jit_elevated(args):
                        try:
                            import shutil
                            bdir = os.path.join(_HOOK_DEVCORE_ROOT, "core", "backups")
                            os.makedirs(bdir, exist_ok=True)
                            if os.path.exists(target):
                                shutil.copy2(target, os.path.join(bdir, bname))
                        except Exception:
                            pass
                    else:
                        reason = (
                            f"Raugus Hot-Patch Enforcement: Direct in-place edits to live backend engine module '{bname}' are forbidden.\n"
                            f"MANDATORY 3-STEP HOT-PATCH SEQUENCE:\n"
                            f"1. Stage the complete updated Python file in '/mnt/c/Users/michael/Documents/DevCore/core/patches/{bname}' using write_to_file.\n"
                            f"2. Trigger the validated hot-patch sequence via: curl -s -X POST http://127.0.0.1:5000/api/simulate-patch (or POST http://127.0.0.1:5000/api/reload).\n"
                            f"3. The server will validate syntax (py_compile), snapshot core/backups/{bname}, hot-swap in memory, and roll back automatically on error."
                        )
                        log_violation(tool_name, target, reason)
                        print(json.dumps({"decision": "deny", "reason": reason}))
                        return

        if tool_name in ["replace_file_content", "edit_lines"]:
            target = args.get("TargetFile") or args.get("target_file")
            if target:
                target = os.path.abspath(target)
                
                # Check file permission first
                file_alias = None
                for alias, data in r_map.items():
                    if target == os.path.abspath(data.get("real_path", "")) and data.get("type") == "file":
                        file_alias = alias
                        if data.get("permissions", {}).get("write") is False:
                            reason = f"Raugus Firewall: File {alias} is Read-Only."
                            if "exam_application.html" in target or "exam_builder.html" in target:
                                reason += " Do NOT modify these templates. Use the exam-generator skill and exam_temp.json payload instead."
                            log_violation(tool_name, target, reason)
                            print(json.dumps({"decision": "deny", "reason": reason}))
                            return
                
                # If the file is writable, we do AST Diffing to check Function-level permissions
                if file_alias and target.endswith(".py"):
                    try:
                        sys.path.insert(0, '/mnt/c/Users/michael/Documents/devcore')
                        from security.mantrap import SemanticMantrap
                        with SemanticMantrap.execution_chamber(target, "Subagent_AST_Diffing"):
                            with open(target, 'r', encoding='utf-8') as f:
                                original_lines = f.readlines()
                        
                            sl = args.get("StartLine") or args.get("start_line", 1)
                            el = args.get("EndLine") or args.get("end_line", len(original_lines))
                            start_line = sl - 1
                            end_line = el
                            repl_content = args.get("ReplacementContent", "") or args.get("new_code", "")
                        
                            # Simulate the new file in memory (IT IS NOT SAVED YET)
                            new_lines = original_lines[:start_line] + [repl_content + "\n"] + original_lines[end_line:]
                            new_source = "".join(new_lines)
                        
                            # Compare original symbols to new symbols
                            orig_symbols = get_ast_symbols("".join(original_lines))
                        
                            # If a symbol falls within the replaced line range, it is being modified!
                            # We must check if that specific symbol is locked in the Raugus Map
                            for sym_name, (sym_start, sym_end) in orig_symbols.items():
                                # Check overlap between modification range [start_line+1, end_line] and symbol range
                                mod_start = sl
                                mod_end = el
                            
                                # If they overlap, the symbol is being modified
                                if max(sym_start, mod_start) <= min(sym_end, mod_end):
                                    sym_alias = f"{file_alias}::{sym_name}"
                                    sym_data = r_map.get(sym_alias, {})
                                    if sym_data.get("permissions", {}).get("write") is False:
                                        reason = f"Raugus Firewall: You have Write access to the file, but the specific function '{sym_name}' is locked (Read-Only). AST Diffing blocked the modification."
                                        log_violation(tool_name, target, reason)
                                        print(json.dumps({
                                            "decision": "deny",
                                            "reason": reason
                                        }))
                                        return
                    except Exception as e:
                        pass # Fail open on diffing error
                        
        print(json.dumps({"decision": "allow"}))
        
    except Exception as e:
        print(json.dumps({"decision": "ask", "reason": f"Hook Error: {str(e)}"}))

if __name__ == "__main__":
    main()
