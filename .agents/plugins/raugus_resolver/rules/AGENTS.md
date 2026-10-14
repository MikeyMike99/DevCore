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
