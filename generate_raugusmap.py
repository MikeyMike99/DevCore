import os
import json
import uuid

def generate_raugusmap(root_dir):
    raugus_map = {}
    
    # Base configuration
    ignore_dirs = {'.git', '__pycache__', 'venv', 'node_modules', '.venv', 'scratch', '.pytest_cache'}
    ignore_files = {'.DS_Store'}
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Modify dirnames in-place to skip ignored directories
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        
        for filename in filenames:
            if filename in ignore_files:
                continue
                
            real_path = os.path.join(dirpath, filename)
            
            # Create a dot-notation alias relative to the root
            rel_path = os.path.relpath(real_path, root_dir)
            # e.g., 'docs/DEVLOG.md' -> 'devcore.docs.DEVLOG.md'
            alias = "devcore." + rel_path.replace(os.sep, '.')
            
            # Assign base Tiers (Can be manually tuned later by Admin)
            # Default to Tier 5 for Python files/system files, Tier 2 for static/UI
            required_tier = 5
            if rel_path.startswith("static") or rel_path.startswith("templates"):
                required_tier = 2
            elif rel_path.startswith("docs"):
                required_tier = 3
                
            raugus_map[alias] = {
                "real_path": real_path,
                "required_tier": required_tier,
                "id": str(uuid.uuid4())
            }
            
    return raugus_map

if __name__ == "__main__":
    root_directory = "/mnt/c/Users/michael/Documents/DevCore"
    output_file = os.path.join(root_directory, "raugus_map.json")
    
    s_map = generate_raugusmap(root_directory)
    
    with open(output_file, 'w') as f:
        json.dump(s_map, f, indent=4)
        
    print(f"Raugus Map successfully generated at {output_file} with {len(s_map)} aliases.")
