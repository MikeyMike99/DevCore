import asyncio
import aiohttp

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:5000/api/sound/incoming") as resp:
            print("Status:", resp.status)
            print("Headers:", resp.headers)
            content = await resp.read()
            print("Size:", len(content))

asyncio.run(main())
