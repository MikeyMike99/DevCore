import os
import sys
import zipfile
import io
import json
from cryptography.fernet import Fernet
from .stamper import STAMP_KEY

class EncryptedVFS:
    def __init__(self, vfs_file="assets.bin"):
        self.vfs_file = vfs_file
        self.cipher = Fernet(STAMP_KEY)
        self.files = {}
        self.loaded = False
        
    def load(self):
        if self.loaded: return
        
        # Check if we are running in Nuitka (sys._MEIPASS is used by PyInstaller, Nuitka uses sys.argv[0] directory)
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.argv[0])))
        vfs_path = os.path.join(base_dir, self.vfs_file)
        
        # If not found next to exe, check in CWD (for Dev mode)
        if not os.path.exists(vfs_path):
            vfs_path = os.path.join(os.getcwd(), self.vfs_file)
            
        if not os.path.exists(vfs_path):
            print(f"[VFS] No encrypted payload found at {vfs_path}. Running in plaintext dev mode.")
            return

        with open(vfs_path, 'rb') as f:
            encrypted_data = f.read()
            
        try:
            zip_bytes = self.cipher.decrypt(encrypted_data)
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                for file_info in z.infolist():
                    if not file_info.is_dir():
                        self.files[file_info.filename.replace('\\', '/')] = z.read(file_info.filename)
            self.loaded = True
            print("[VFS] Encrypted Asset Payload Loaded into RAM successfully.")
        except Exception as e:
            print(f"[VFS] Failed to decrypt payload: {e}")

    def read(self, filepath):
        """Returns the bytes of the file, checking live overrides first, then RAM VFS."""
        # 1. Live Override (unencrypted file on disk takes priority for OTA updates)
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                return f.read()
                
        # 2. RAM VFS
        normalized_path = filepath.replace('\\', '/')
        if self.loaded and normalized_path in self.files:
            return self.files[normalized_path]
            
        return None

vfs = EncryptedVFS()
vfs.load()
