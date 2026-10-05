import asyncio
import sys
async def main():
    proc = await asyncio.create_subprocess_exec("agy", "--print", "run sleep 10", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    await asyncio.sleep(2)
    proc.send_signal(2) # SIGINT
    out, _ = await proc.communicate()
    print("OUTPUT:", out.decode('utf-8'))
asyncio.run(main())
