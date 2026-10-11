import zipfile
import os

source_dir = r'C:\Users\michael\Documents\e_profile'
output_zip = r'C:\Users\michael\Documents\e_profile\e_profile_slim_deploy.zip'

print("Creating slim deployment zip...")

with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(source_dir):
        # EXCLUDE MASSIVE DIRECTORIES
        dirs[:] = [d for d in dirs if d not in ['.git', 'venv', '__pycache__', '.pytest_cache', '.vscode', 'node_modules']]
        
        for file in files:
            file_path = os.path.join(root, file)
            
            # Skip the zip itself
            if file_path == output_zip:
                continue
                
            arcname = os.path.relpath(file_path, source_dir)
            zipf.write(file_path, arcname)

print(f"Successfully created: {output_zip}")
print(f"Size: {os.path.getsize(output_zip) / (1024*1024):.2f} MB")
