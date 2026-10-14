import os
import json
import uuid
import ast

def parse_ast_for_file(filepath):
    # Returns a list of top-level function and variable names
    symbols = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols.append(target.id)
    except Exception as e:
        pass # Ignore syntax errors or unparseable files
    return symbols

def generate_raugusmap(root_dir, existing_map=None):
    raugus_map = {}
    existing_map = existing_map or {}
    
    ignore_dirs = {'.git', '__pycache__', 'venv', 'node_modules', '.venv', 'scratch', '.pytest_cache'}
    ignore_files = {'.DS_Store', 'raugus_map.json'}

    def _get_inode(p):
        try:
            return int(os.stat(p).st_ino)
        except Exception:
            return 0

    # Explicitly register sensitive vault directories (even when empty)
    exam_content_dir = os.path.join(root_dir, "plugins", "exam_application", "content")
    exam_content_alias = "devcore.plugins.exam_application.content"
    raugus_map[exam_content_alias] = {
        "type": "directory",
        "real_path": exam_content_dir,
        "inode": _get_inode(exam_content_dir),
        "required_tier": 3,
        "sensitive": True,
        "permissions": {"read": False, "write": False, "execute": False, "local_broker": True},
        "id": existing_map.get(exam_content_alias, {}).get("id", str(uuid.uuid4()))
    }

    # Automatically discover and register all OneDrive sync roots (regardless of folder name)
    try:
        import re
        import sys
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)
        from security.raugus_resolver import discover_onedrive_roots
        for od_root in discover_onedrive_roots():
            slug = re.sub(r"[^a-z0-9]+", "_", os.path.basename(od_root).lower()).strip("_") or "root"
            od_alias = f"external.onedrive.{slug}"
            raugus_map[od_alias] = {
                "type": "directory",
                "real_path": od_root,
                "inode": _get_inode(od_root),
                "required_tier": 3,
                "sensitive": True,
                "permissions": {"read": False, "write": False, "execute": False, "local_broker": True},
                "id": existing_map.get(od_alias, {}).get("id", str(uuid.uuid4()))
            }
    except Exception:
        pass
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        
        for filename in filenames:
            if filename in ignore_files:
                continue
                
            real_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(real_path, root_dir)
            norm_rel = rel_path.replace("\\", "/")
            alias = "devcore." + rel_path.replace(os.sep, '.')
            
            required_tier = 5
            if rel_path.startswith("static") or rel_path.startswith("templates"):
                required_tier = 2
            elif rel_path.startswith("docs") or rel_path.startswith("sandbox"):
                required_tier = 3
                
            perms = {"read": True, "write": True, "execute": True}
            if required_tier >= 5:
                perms = {"read": True, "write": False, "execute": False}
            elif required_tier == 3:
                perms = {"read": True, "write": True, "execute": False}
            elif required_tier == 2:
                perms = {"read": True, "write": True, "execute": False}

            is_sensitive = (
                norm_rel.startswith("plugins/exam_application/content/")
                or bool(existing_map.get(alias, {}).get("sensitive", False))
            )
            if is_sensitive:
                required_tier = 3
                perms = {"read": False, "write": False, "execute": False, "local_broker": True}
            elif alias in existing_map and "permissions" in existing_map[alias]:
                perms = dict(existing_map[alias]["permissions"])
                
            # 1. Map the File
            raugus_map[alias] = {
                "type": "file",
                "real_path": real_path,
                "required_tier": required_tier,
                "sensitive": is_sensitive,
                "permissions": perms,
                "id": existing_map.get(alias, {}).get("id", str(uuid.uuid4()))
            }
            
            # 2. Map one deeper: Functions and Variables (if Python file)
            if filename.endswith(".py"):
                symbols = parse_ast_for_file(real_path)
                for sym in symbols:
                    sym_alias = f"{alias}::{sym}"
                    sym_perms = dict(existing_map[sym_alias]["permissions"]) if (not is_sensitive and sym_alias in existing_map and "permissions" in existing_map[sym_alias]) else dict(perms)
                    # Symbols inherit file permissions by default, but can be locked down later
                    raugus_map[sym_alias] = {
                        "type": "symbol",
                        "real_path": real_path,
                        "symbol_name": sym,
                        "required_tier": required_tier,
                        "sensitive": is_sensitive,
                        "permissions": sym_perms, # Copy of file perms
                        "id": existing_map.get(sym_alias, {}).get("id", str(uuid.uuid4()))
                    }
                    
    return raugus_map

if __name__ == "__main__":
    root_directory = "/mnt/c/Users/michael/Documents/DevCore"
    # Write directly to the active security directory
    output_file = "/mnt/c/Users/michael/Documents/DevCore/security/raugus_map.json"
    if not os.path.exists(os.path.dirname(output_file)):
        output_file = "/mnt/c/Users/michael/Documents/devcore/security/raugus_map.json"
    
    prev_map = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r') as pf:
                prev_map = json.load(pf)
        except Exception:
            prev_map = {}

    s_map = generate_raugusmap(root_directory, existing_map=prev_map)
    
    with open(output_file, 'w') as f:
        json.dump(s_map, f, indent=4)
        
    print(f"Raugus Map successfully generated at {output_file} with {len(s_map)} aliases (Files + Deep Symbols).")
