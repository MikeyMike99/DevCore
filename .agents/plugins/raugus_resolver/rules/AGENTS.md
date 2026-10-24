# Raugus VFS Key Resolver Protocol (MCP Tooling)

You have access to the **Raugus Resolver (`raugus-resolver`)** MCP Server, which enforces the **Opaque Key-Only Virtual File System (VFS) Protocol**.

**CRITICAL DIRECTIVE:**
1. **Zero Physical File Paths:** The Raugus Resolver never exposes physical filesystem paths (`real_path`). All access to files, functions, classes, and variables through the Resolver is performed strictly via **Raugus VFS Keys** (e.g., `devcore.core.routes.system.py` or `devcore.core.routes.system.py::reload_system`).
2. **Rule Verification Before Grant:** When you pass a key to the Resolver, it looks up the key in the Raugus Map, verifies RBAC tier clearance, file/symbol read-write locks, Sensitive Vault boundaries, and AST syntax rules, and returns **only the granted result**.

### Available MCP Tools (`raugus-resolver`):
1. **`search_keys(query, entry_type="all", user_tier=5, limit=30)`**:
   - Discover VFS keys (`devcore.*` and `devcore.*::symbol`) and their RBAC permissions by keyword without exposing file paths.
2. **`list_module_keys(module_key, user_tier=5)`**:
   - List all function, class, and variable keys (`<module_key>::<symbol_name>`) inside a module key along with their line spans and read/write permissions.
3. **`read_by_key(key, user_tier=5)`**:
   - Retrieve the exact source code or value of a function, class, variable (`module_key::symbol_name`), or module (`module_key`) purely by key after all Raugus rules are verified.
4. **`write_by_key(key, new_code, user_tier=5)`**:
   - Update a specific function, class, variable (`module_key::symbol_name`), or module (`module_key`) by key. Automatically validates AST syntax, enforces function-level write locks, and routes live backend engine updates through the Zero-Downtime Hot-Patch staging sequence without exposing physical paths.
5. **`refresh_key_map(user_tier=5)`**:
   - Re-index workspace AST keys and hardware inodes in the Raugus Map after structural updates.
6. **`workspace_pipeline(action="status", commit_msg="", no_push=False, commit_devcore=False, user_tier=5)`**:
   - Executes the unified cross-repository workspace pipeline (`Central_Docs`, `e_profile`, `DevCore`, `Audio_pllayback_suite`) in a single tool call. Eliminates token bloat from repetitive status checks, manual quality/structure/security audits, and fragmented multi-repo commits.
7. **`get_block_by_tag(tag_or_id, user_tier=5)`**:
   - Retrieve an immutable AST or documentation block directly by its tag identifier or content hash without loading surrounding code.

---

## 3. Operational Triage & Recovery Protocol (Infinite Loop Prevention)

### The Anti-Loop Axiom: NEVER Attempt Alternative File Tools After a Denial
> **CRITICAL ARCHITECTURAL DIRECTIVE:**
> If an operation is denied by the Raugus PreToolUse hook or the Resolver MCP Broker, the restriction is **semantic and architectural**, NOT a tooling syntax limitation.
> - **STRICTLY FORBIDDEN**: Switching between `write_to_file`, `replace_file_content`, `edit_lines`, `run_command` (`sed`, `cat`, `python << 'EOF'`), or `git` (`apply`, `checkout`, `restore`) after a denial.
> - Attempting tool-hopping causes an immediate infinite retry loop, generates SIEM intrusion alerts, and will be intercepted at every step.
> - When denied: Read the denial reason, match it to the table below, and execute **ONLY** the prescribed recovery action.

### The 6 Denial Categories & Prescribed Agent Action

| Status Code / Denial Message | Architectural Cause | What You MUST NOT Do | Prescribed Recovery Action |
| :--- | :--- | :--- | :--- |
| **`DENIED_SELF_PROTECTION`** | Target is a core security file (`raugus_hook.py`, `hooks.json`, `server.py`, `raugus_map.json`, etc.). | **DO NOT** attempt bash redirection, heredocs, python scripts, git commands, or self-minting JIT tokens. | **STOP IMMEDIATELY**. Ask the human Super Admin to unlock core security files for 5 minutes via **🔓 Elevate JIT (5m)** in the DevCore UI or `python3 security/jit_elevation.py --mint` in their terminal, then pass `elevation_token` to `write_by_key`. |
| **`DENIED_SENSITIVE_VAULT`** | Target resides inside a Sensitive Study Vault or cloud-synced directory (`sensitive: true`). | **DO NOT** attempt raw text reads, hex encoding, wildcard globbing, or two-step helper scripts. | **ROUTE TO LOCAL BRAIN BROKER**. For practice questions: `python3 security/local_brain_broker.py --target "<key>" --mode exam`. For queries: `python3 security/local_brain_broker.py --target "<key>" --mode query`. |
| **`DENIED_READ_ONLY` (Blueprints)** | Target is an immutable UI blueprint (`exam_application.html`, `exam_builder.html`, `EXAM_APPLICATION.md`). | **DO NOT** attempt to hack template JS/CSS to add dynamic features. | **USE PAYLOAD INJECTION**. Fulfill all behavioral changes strictly via the JSON schema (`exam-generator` skill + `exam_temp.json` payload). |
| **`DENIED_SYMBOL_LOCKED`** | Function or symbol is AST-locked (`permissions.write == false` or `locked == true`). | **DO NOT** attempt whole-module overwrites or editing lines around the function. | **PRESERVE THE LOCKED SYMBOL**. Confine edits strictly to unlocked symbols. If the locked symbol must change, request explicit user clearance. |
| **`DENIED_SYNTAX_ERROR` / `DENIED_HOT_PATCH_FAILED`** | Candidate code failed Python AST compilation (`ast.parse`) or preflight bytecode validation. | **DO NOT** attempt force-writing to disk bypassing hot-patch staging. | **FIX INDENTATION / SYNTAX IN-MEMORY**. Re-parse candidate code for missing colons, indentation errors, or unclosed quotes, then retry `write_by_key`. |
| **`[RAUGUS WORKSPACE PIPELINE GUIDANCE]`** | Attempted fragmented operations (`git status` on sub-repos, manual `audit_docs.py`, separate commits). | **DO NOT** run individual git commands across multiple repositories. | **USE THE UNIFIED PIPELINE**. Execute `python3 scripts/workspace_pipeline.py --status`, `--audit`, or `--commit "<msg>"`, or invoke MCP tool `workspace_pipeline`. |

---

## 4. How the Raugus Architecture Works (Agent Quick Reference)
1. **Opaque Virtual File System (VFS)**: Real paths (`/mnt/c/...`) are invisible and rejected. Discover modules and functions using `search_keys(query="...")`.
2. **AST Symbol Extraction**: Read or update functions directly via `<module_key>::<symbol_name>`. The resolver isolates only the target function in memory, preserving neighboring code.
3. **Zero-Downtime Hot-Patching**: For live engine modules, `write_by_key` automatically stages code in `core/patches/`, compiles it, snapshots backups, and reloads memory without dropping active WebSocket connections.

---

## 5. Token Minimization & Block-Level AST Workflows
To prevent token inflation and preserve AI context windows:
1. **Surgical Reads**: Prioritize `read_by_key('<module>::<symbol>')` or `get_block_by_tag('<tag>')` rather than loading multi-hundred-line modules. AST slices average 15–30 lines, reducing token overhead by over 90%.
2. **Surgical Writes**: Update target functions directly via `write_by_key('<module>::<symbol>', new_code)`. The resolver recompiles and hot-patches solely the modified symbol.
3. **Local Triage**: Use `python3 security/local_brain_broker.py --target "<target>" --mode triage --query "<query>"` to locate symbol keys and tags on local CPU before invoking cloud reasoning.

