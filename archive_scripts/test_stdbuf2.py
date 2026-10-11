import subprocess, os, re
env = os.environ.copy()
proc = subprocess.Popen(['stdbuf', '-oL', '/home/michael/.local/bin/agy', '--print', 'ping'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
for i in range(5):
    line = proc.stdout.readline()
    print(f"Line {i}: {repr(line)}")
    if "https://accounts.google.com" in line:
        match = re.search(r'(https://accounts\.google\.com/[^\s]+)', line)
        print(f"Match: {match.group(1) if match else 'None'}")
        proc.kill()
        break
