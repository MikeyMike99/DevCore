import os
script = '''#!/bin/bash
source ~/.bashrc
source ~/alp-env/bin/activate
KEY=
export GEMINI_API_KEY=
python3 server.py
'''
with open('start_server.sh', 'w', encoding='utf-8', newline='\n') as f:
    f.write(script)
