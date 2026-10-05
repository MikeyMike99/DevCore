import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Capture console logs
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        
        print("Navigating to video player...")
        await page.goto("http://127.0.0.1:5000/plugin/media?v=jNQXAC9IVRw&video_temp=1")
        
        # Wait for the YouTube Iframe to be inserted or timeout after 5s
        try:
            await page.wait_for_selector('iframe[src*="youtube.com"]', timeout=5000)
            print("YouTube Iframe successfully injected into the DOM!")
        except Exception as e:
            print("Timeout waiting for YouTube Iframe.")
            
        print("Clicking play button...")
        try:
            await page.click('#btnPlayPause', timeout=2000)
            print("Play button clicked.")
        except Exception as e:
            print("Could not click play button:", e)
            
        await asyncio.sleep(2)
        
        debug_log = await page.evaluate("document.getElementById('debugLog').innerText")
        print("DEBUG DIV CONTENTS:\n", debug_log)
        
        await browser.close()

asyncio.run(run())
