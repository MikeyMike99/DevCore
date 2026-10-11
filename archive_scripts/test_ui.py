import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        # Capture console logs
        page.on("console", lambda msg: print(f"JS Console [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: print(f"JS Error: {err}"))
        
        print("Navigating to http://127.0.0.1:5000/")
        response = await page.goto("http://127.0.0.1:5000/")
        print(f"Status: {response.status}")
        
        # Wait a bit for JS to execute
        await page.wait_for_timeout(2000)
        
        await browser.close()

asyncio.run(main())
