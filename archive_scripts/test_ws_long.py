import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://127.0.0.1:5000/ws"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to websocket!")
            
            payload = {
                "type": "prompt",
                "prompt": "Say hello!",
                "model": "gemini-3.8-flash-high",
                "conversation_id": "conv-test",
                "admin_override": False,
                "token": ""
            }
            await websocket.send(json.dumps(payload))
            print("Sent prompt")
            
            # Wait for up to 3 messages
            for i in range(3):
                msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                print(f"Received {i+1}: {msg}")
                if "error" in msg.lower() or '"type": "task_completed"' in msg:
                    break
    except Exception as e:
        print(f"Websocket error: {e}")

asyncio.run(test_ws())
