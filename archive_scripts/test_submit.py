import subprocess, os
env = os.environ.copy()
proc = subprocess.Popen(['stdbuf', '-oL', '/home/michael/.local/bin/agy', '--print', 'ping'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
proc.stdin.write("badtoken\n")
proc.stdin.flush()
print("WROTE TOKEN")
for i in range(10):
    line = proc.stdout.readline()
    print(f"Line {i}: {repr(line)}")
    if not line: break
proc.kill()
