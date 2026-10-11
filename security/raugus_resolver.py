import json
import os
import logging

class RaugusResolver:
    def __init__(self, map_file="raugus_map.json", redis_url=None):
        # Resolve path relative to this script to ensure it always finds the map
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.map_file = os.path.join(base_dir, map_file)
        self.phonebook = {}
        
        # [REDIS MIGRATION PLACEHOLDER]
        # Future architecture will shift to Redis to fully decouple the security map
        # from the local Python memory state.
        # self.redis_client = None
        # if redis_url:
        #     import redis
        #     self.redis_client = redis.from_url(redis_url, decode_responses=True)
        #     self._seed_redis_map()
        # else:
        self._load_phonebook()

    def _load_phonebook(self):
        if os.path.exists(self.map_file):
            with open(self.map_file, 'r') as f:
                self.phonebook = json.load(f)
            
            # DYNAMIC PATH CORRECTION FOR COMPILED EXECUTABLES:
            # We recalculate the real_path based on the current executable's root directory,
            # ignoring the hardcoded machine paths from when the map was generated.
            current_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            for alias, data in self.phonebook.items():
                if alias.startswith("devcore."):
                    # We can simply take the alias, remove devcore., and assume all dots EXCEPT the last one are folder separators.
                    # Wait, no. What if a folder has a dot? Better to rely on the fact that generate_raugusmap replaced os.sep with '.'
                    # Actually, we can just replace devcore. with empty, and then replace . with os.sep, but fix the last extension.
                    # Easier: just use the original real_path from the JSON, find "DevCore", and take everything after it!
                    old_path = data.get("real_path", "")
                    if "DevCore" in old_path:
                        # Extract the part after DevCore/
                        parts = old_path.split("DevCore")
                        rel_path = parts[-1].lstrip("\\/")
                        data["real_path"] = os.path.join(current_root, rel_path)
            
            logging.info(f"[RAUGUS] Loaded and dynamically patched {len(self.phonebook)} aliases from {self.map_file}")
        else:
            logging.error(f"[RAUGUS FATAL] Raugus Map not found at {self.map_file}")

    def get_path(self, alias, user_tier):
        """
        Resolves an alias to a physical path, enforcing RBAC Tiers.
        Returns the physical_path if authorized.
        Raises KeyError if alias is invalid (Blocks Path Traversal).
        Raises PermissionError if Tier is too low.
        """
        # [REDIS MIGRATION PLACEHOLDER]
        # if self.redis_client:
        #     entry_str = self.redis_client.hget("raugus:aliases", alias)
        #     if not entry_str:
        #         logging.warning(f"[RAUGUS BLOCKED] Invalid alias requested: {alias}")
        #         raise KeyError(f"Alias '{alias}' does not exist in Redis.")
        #     entry = json.loads(entry_str)
        # else:
        if alias not in self.phonebook:
            logging.warning(f"[RAUGUS BLOCKED] Invalid alias requested: {alias}. Potential traversal attack.")
            raise KeyError(f"Alias '{alias}' does not exist in the Raugus Map.")

        entry = self.phonebook[alias]
        required_tier = entry.get("required_tier", 5)

        if user_tier < required_tier:
            logging.warning(f"[RAUGUS DENIED] Tier {user_tier} attempted to access Tier {required_tier} alias '{alias}'.")
            raise PermissionError(f"Access Denied. Tier {required_tier} clearance required.")

        logging.info(f"[RAUGUS APPROVED] Alias '{alias}' resolved for Tier {user_tier}.")
        real_path = entry.get("real_path")
        if not real_path or not os.path.exists(real_path):
            base_dir = os.path.dirname(os.path.abspath(__file__)) # security folder
            devcore_root = os.path.dirname(base_dir) # DevCore root or bundle root
            if "Documents/DevCore/" in real_path:
                rel = real_path.split("Documents/DevCore/")[-1].replace("/", os.sep)
            elif "/DevCore/" in real_path:
                rel = real_path.split("/DevCore/")[-1].replace("/", os.sep)
            else:
                rel = os.path.basename(real_path)
            candidate = os.path.normpath(os.path.join(devcore_root, rel))
            if os.path.exists(candidate):
                return candidate
            cwd_candidate = os.path.normpath(os.path.join(os.getcwd(), rel))
            if os.path.exists(cwd_candidate):
                return cwd_candidate
        return real_path

    def enforce_path_security(self, path: str, user_tier: int):
        """
        Evaluates a physical path against the Raugus Map.
        Raises PermissionError if the user's tier is too low to access it.
        """
        target_path = os.path.abspath(path)
        
        # [REDIS MIGRATION PLACEHOLDER]
        # if self.redis_client:
        #     # In a Redis architecture, path enforcement will likely involve scanning a specific index
        #     # or resolving the active aliases bound to the workspace tier directly from the KV store.
        #     pass
        
        # Find if this path (or a parent) exists in the map
        highest_tier_required = 1  # Default to Safe Workspace
        
        for alias, data in self.phonebook.items():
            real_path = os.path.abspath(data.get("real_path", ""))
            # Check if target_path is the same or a child of real_path
            # To be safe, we check if target_path starts with real_path
            # e.g. target_path = /core/server.py, real_path = /core
            if target_path == real_path or target_path.startswith(real_path + os.sep):
                req_tier = data.get("required_tier", 1)
                if req_tier > highest_tier_required:
                    highest_tier_required = req_tier
        
        if user_tier < highest_tier_required:
            logging.error(f"[RAUGUS INTRUSION] Tier {user_tier} attempted to access Tier {highest_tier_required} asset: {target_path}")
            raise PermissionError(f"Raugus Semantic Firewall: Access Denied to Tier {highest_tier_required} asset.")
        
        return True



    def enforce_feedback_policy(self, path: str):
        """
        Queries the Raugus map to determine if a file is allowed to request execution feedback.
        Blocks feedback requests on documentation, text files, and markdown.
        """
        if not path:
            return
            
        target_path = os.path.abspath(path)
        
        # Query the map for the physical path
        for alias, data in self.phonebook.items():
            real_path = os.path.abspath(data.get("real_path", ""))
            
            # If the file matches exactly, or is inside a mapped directory
            if target_path == real_path or target_path.startswith(real_path + os.sep):
                # Block if it's in the docs directory, or is a markdown file
                if ".docs." in alias or "devlog" in alias.lower() or alias.endswith(".md") or "textbook" in alias.lower() or "module" in alias.lower():
                    raise PermissionError(f"Raugus Firewall: Alias '{alias}' is classified as documentation. RequestFeedback=True is strictly forbidden.")
        
        # Fallback for dynamic artifacts not yet in the map
        # Allow markdown files as artifacts may require feedback
            
        return True

# Singleton instance for the application to import
resolver = RaugusResolver()
