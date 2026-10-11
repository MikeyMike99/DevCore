import subprocess, os, time, re
env = os.environ.copy()
cmd = ['script', '-q', '-c', '/home/michael/.local/bin/agy --print ping', '/dev/null']
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
url = None
for _ in range(5):
    line = proc.stdout.readline()
    print("READING:", repr(line))
    if "https://accounts.google.com" in line:
        match = re.search(r'(https://accounts\.google\.com/[^\s]+)', line)
        if match:
            url = match.group(1)
            print("FOUND URL:", url)
            break
proc.stdin.write("badtoken\n")
proc.stdin.flush()
for _ in range(15):
    line = proc.stdout.readline()
    print("READING2:", repr(line))
    if "Error:" in line or "error:" in line or "pong" in line.lower():
        break
proc.kill()
