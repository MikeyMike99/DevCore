import os
import zipfile
import io
from cryptography.fernet import Fernet
from security.stamper import STAMP_KEY

def pack_directories(dirs_and_files, output_file="assets.bin"):
    print("[VFS Pack] Compressing frontend assets...")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        for item in dirs_and_files:
            if os.path.isdir(item):
                for root, _, files in os.walk(item):
                    for file in files:
                        filepath = os.path.join(root, file)
                        z.write(filepath, filepath)
            elif os.path.isfile(item):
                z.write(item, item)
    
    zip_bytes = buffer.getvalue()
    print(f"[VFS Pack] Compressed size: {len(zip_bytes)} bytes.")
    
    cipher = Fernet(STAMP_KEY)
    encrypted_bytes = cipher.encrypt(zip_bytes)
    
    with open(output_file, 'wb') as f:
        f.write(encrypted_bytes)
    print(f"[VFS Pack] Encrypted payload written to {output_file} ({len(encrypted_bytes)} bytes).")

if __name__ == "__main__":
    pack_directories(["sandbox/templates", "sandbox/static", "core/ui_config.json"])
