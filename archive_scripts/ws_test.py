import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://127.0.0.1:5000/ws"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to websocket!")
            # Wait for any initial message
            msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            print(f"Received: {msg}")
    except Exception as e:
        print(f"Websocket error: {e}")

asyncio.run(test_ws())
