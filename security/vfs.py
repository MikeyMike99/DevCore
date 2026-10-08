import os
import sys
import zipfile
import io
import json
import logging
from cryptography.fernet import Fernet
from .stamper import STAMP_KEY

class EncryptedVFS:
    def __init__(self, vfs_file="assets.bin"):
        self.vfs_file = vfs_file
        self.cipher = Fernet(STAMP_KEY)
        self.files = {}
        self.loaded = False
        self.is_frozen = getattr(sys, 'frozen', False)
        
    def load(self):
        if self.loaded: return
        
        # Check if we are running in Nuitka
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.argv[0])))
        vfs_path = os.path.join(base_dir, self.vfs_file)
        
        # If not found next to exe, check in CWD
        if not os.path.exists(vfs_path):
            vfs_path = os.path.join(os.getcwd(), self.vfs_file)
            
        if not os.path.exists(vfs_path):
            msg = f"[VFS] CRITICAL: No encrypted payload found at {vfs_path}."
            if self.is_frozen:
                logging.critical(msg + " Halting execution to prevent unencrypted fallback.")
                sys.exit(1)
            else:
                logging.warning(msg + " Running in plaintext dev mode.")
            return

        try:
            with open(vfs_path, 'rb') as f:
                encrypted_data = f.read()
                
            zip_bytes = self.cipher.decrypt(encrypted_data)
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                for file_info in z.infolist():
                    if not file_info.is_dir():
                        self.files[file_info.filename.replace('\\', '/')] = z.read(file_info.filename)
            self.loaded = True
            logging.info("[VFS] Encrypted Asset Payload Loaded into RAM successfully.")
        except Exception as e:
            msg = f"[VFS] CRITICAL: Failed to decrypt payload or payload corrupted: {e}"
            logging.critical(msg)
            if self.is_frozen:
                sys.exit(1)

    def read(self, filepath):
        """Returns the bytes of the file, checking live overrides first, then RAM VFS."""
        if os.path.exists(filepath):
            return open(filepath, 'rb').read()
                
        normalized_path = filepath.replace('\\', '/')
        if self.loaded and normalized_path in self.files:
            return self.files[normalized_path]
            
        logging.warning(f"[VFS] File not found in VFS or Disk: {filepath}")
        return None

vfs = EncryptedVFS()
