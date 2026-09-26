import json
import os
import logging

class RaugusResolver:
    def __init__(self, map_file="raugus_map.json"):
        # Resolve path relative to this script to ensure it always finds the map
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.map_file = os.path.join(base_dir, map_file)
        self.phonebook = {}
        self._load_phonebook()

    def _load_phonebook(self):
        if os.path.exists(self.map_file):
            with open(self.map_file, 'r') as f:
                self.phonebook = json.load(f)
            logging.info(f"[RAUGUS] Loaded {len(self.phonebook)} aliases from {self.map_file}")
        else:
            logging.error(f"[RAUGUS FATAL] Raugus Map not found at {self.map_file}")

    def get_path(self, alias, user_tier):
        """
        Resolves an alias to a physical path, enforcing RBAC Tiers.
        Returns the physical_path if authorized.
        Raises KeyError if alias is invalid (Blocks Path Traversal).
        Raises PermissionError if Tier is too low.
        """
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

# Singleton instance for the application to import
resolver = RaugusResolver()
