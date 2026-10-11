import asyncio
import sys

async def main():
    proc = await asyncio.create_subprocess_exec(
        '/home/michael/.local/bin/agy', '--print', 'ping',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    # Read until prompt
    prompt = b''
    while True:
        try:
            char = await asyncio.wait_for(proc.stdout.read(1), timeout=5.0)
            if not char: break
            prompt += char
            if b'paste the authorization code here' in prompt.lower():
                # Read the rest of the line (e.g. ' and press Enter: ')
                rest = await proc.stdout.readline()
                prompt += rest
                break
        except asyncio.TimeoutError:
            break
            
    print('PROMPT:', prompt.decode('utf-8', errors='ignore'))
    
    if b'paste the authorization code here' in prompt.lower():
        print('Sending fake token...')
        proc.stdin.write(b'4/1fake_token_123\n')
        await proc.stdin.drain()
        
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            print('OUTPUT AFTER TOKEN:', out.decode('utf-8', errors='ignore'))
        except asyncio.TimeoutError:
            print('TIMED OUT WAITING FOR CLI TO EXIT')
    else:
        print('No prompt found. Is it authenticated?')

asyncio.run(main())
