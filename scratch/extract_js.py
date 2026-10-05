import re

with open('/mnt/c/Users/michael/Documents/devcore/sandbox/templates/video_application.html', 'r') as f:
    content = f.read()

scripts = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)
for i, s in enumerate(scripts):
    with open(f'/mnt/c/Users/michael/Documents/devcore/scratch/script_{i}.js', 'w') as out:
        out.write(s)
