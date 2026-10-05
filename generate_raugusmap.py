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

def generate_raugusmap(root_dir):
    raugus_map = {}
    
    ignore_dirs = {'.git', '__pycache__', 'venv', 'node_modules', '.venv', 'scratch', '.pytest_cache'}
    ignore_files = {'.DS_Store', 'raugus_map.json'}
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        
        for filename in filenames:
            if filename in ignore_files:
                continue
                
            real_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(real_path, root_dir)
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
                
            # 1. Map the File
            raugus_map[alias] = {
                "type": "file",
                "real_path": real_path,
                "required_tier": required_tier,
                "permissions": perms,
                "id": str(uuid.uuid4())
            }
            
            # 2. Map one deeper: Functions and Variables (if Python file)
            if filename.endswith(".py"):
                symbols = parse_ast_for_file(real_path)
                for sym in symbols:
                    sym_alias = f"{alias}::{sym}"
                    # Symbols inherit file permissions by default, but can be locked down later
                    raugus_map[sym_alias] = {
                        "type": "symbol",
                        "real_path": real_path,
                        "symbol_name": sym,
                        "required_tier": required_tier,
                        "permissions": dict(perms), # Copy of file perms
                        "id": str(uuid.uuid4())
                    }
                    
    return raugus_map

if __name__ == "__main__":
    root_directory = "/mnt/c/Users/michael/Documents/DevCore"
    # Write directly to the active security directory
    output_file = "/mnt/c/Users/michael/Documents/devcore/security/raugus_map.json"
    
    s_map = generate_raugusmap(root_directory)
    
    with open(output_file, 'w') as f:
        json.dump(s_map, f, indent=4)
        
    print(f"Raugus Map successfully generated at {output_file} with {len(s_map)} aliases (Files + Deep Symbols).")
