import os
import glob
from cryptography.fernet import Fernet

# Use the same AES key as our binary stamper
STAMP_KEY = b'A4l7KaUtSVz1kvIS0SPXP2olNkyY6XVLNOhrEtTvkrc='

def get_cipher():
    return Fernet(STAMP_KEY)

def get_brain_dir():
    # Resolves to ~/.gemini/antigravity-cli/brain
    home = os.path.expanduser("~")
    return os.path.join(home, ".gemini", "antigravity-cli", "brain")

def lock_brain():
    """Encrypts all transcript files in the brain for Cold Storage."""
    brain_dir = get_brain_dir()
    if not os.path.exists(brain_dir):
        return

    cipher = get_cipher()
    # Find all transcript files
    search_pattern = os.path.join(brain_dir, "**", "transcript*.jsonl")
    for file_path in glob.glob(search_pattern, recursive=True):
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # Don't double encrypt
            if data.startswith(b'gAAAAA'): 
                continue
                
            encrypted = cipher.encrypt(data)
            with open(file_path, 'wb') as f:
                f.write(encrypted)
            print(f"[Cold Storage] Locked: {file_path}")
        except Exception as e:
            print(f"[Cold Storage Error] Failed to lock {file_path}: {e}")

def unlock_brain():
    """Decrypts all transcript files in the brain for Active Use."""
    brain_dir = get_brain_dir()
    if not os.path.exists(brain_dir):
        return

    cipher = get_cipher()
    search_pattern = os.path.join(brain_dir, "**", "transcript*.jsonl")
    for file_path in glob.glob(search_pattern, recursive=True):
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # Only decrypt if it is encrypted (Fernet tokens start with gAAAAA)
            if data.startswith(b'gAAAAA'):
                decrypted = cipher.decrypt(data)
                with open(file_path, 'wb') as f:
                    f.write(decrypted)
                print(f"[Cold Storage] Unlocked: {file_path}")
        except Exception as e:
            print(f"[Cold Storage Error] Failed to unlock {file_path}: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "lock":
        lock_brain()
    else:
        unlock_brain()
