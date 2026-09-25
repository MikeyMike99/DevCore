import os
import sys
import json

MAGIC_START = b"\n---AGY_STAMP_START---\n"
MAGIC_END = b"\n---AGY_STAMP_END---\n"

def stamp_exe(source_exe: str, dest_exe: str, payload: dict):
    """
    Copies the source .exe and safely appends a JSON payload to the bottom of the binary file.
    This creates a uniquely stamped executable without recompiling.
    """
    import shutil
    
    if not os.path.exists(source_exe):
        raise FileNotFoundError(f"Source executable {source_exe} not found.")
        
    # 1. Copy the clean master .exe
    shutil.copy2(source_exe, dest_exe)
    
    # 2. Prepare the payload
    payload_bytes = json.dumps(payload).encode('utf-8')
    stamp_data = MAGIC_START + payload_bytes + MAGIC_END
    
    # 3. Inject it at the end of the binary
    with open(dest_exe, "ab") as f:
        f.write(stamp_data)
        
    print(f"Successfully stamped {dest_exe} with payload: {payload}")

def read_stamp() -> dict:
    """
    Reads the currently executing binary (sys.executable) to see if it was stamped
    with a JSON payload. Returns the dictionary if found, else None.
    """
    if not getattr(sys, 'frozen', False):
        # We are running natively in Python (not an .exe)
        return None
        
    exe_path = sys.executable
    if not os.path.exists(exe_path):
        return None
        
    try:
        # Read the last 4096 bytes of the binary (where our stamp would be)
        with open(exe_path, "rb") as f:
            f.seek(0, 2) # End of file
            file_size = f.tell()
            read_size = min(4096, file_size)
            f.seek(file_size - read_size)
            tail_data = f.read()
            
        start_idx = tail_data.rfind(MAGIC_START)
        end_idx = tail_data.rfind(MAGIC_END)
        
        if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
            # We found a valid stamp!
            json_bytes = tail_data[start_idx + len(MAGIC_START) : end_idx]
            return json.loads(json_bytes.decode('utf-8'))
            
    except Exception as e:
        print(f"[Stamper] Failed to read executable stamp: {e}")
        
    return None

if __name__ == "__main__":
    # Simple CLI for the developer to stamp an exe quickly
    import argparse
    parser = argparse.ArgumentParser(description="Stamp a DevCore Executable with a Client ID")
    parser.add_argument("--source", default="Siraugga.exe", help="The master .exe file")
    parser.add_argument("--dest", required=True, help="The output stamped .exe file")
    parser.add_argument("--id", required=True, help="The unique EXE ID / Deployment Token")
    parser.add_argument("--days", type=int, default=7, help="Days until this exe expires")
    
    args = parser.parse_args()
    
    import datetime
    expire_date = (datetime.datetime.now() + datetime.timedelta(days=args.days)).isoformat()
    
    payload = {
        "exe_id": args.id,
        "expires": expire_date
    }
    
    stamp_exe(args.source, args.dest, payload)
