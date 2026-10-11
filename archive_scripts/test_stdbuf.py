import subprocess, os
env = os.environ.copy()
proc = subprocess.Popen(['stdbuf', '-oL', '/home/michael/.local/bin/agy', '--print', 'ping'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
print(repr(proc.stdout.readline()))
print(repr(proc.stdout.readline()))
proc.kill()
