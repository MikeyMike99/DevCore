import asyncio, websockets, json
async def test():
    async with websockets.connect('ws://localhost:5000/ws') as ws:
        await ws.send(json.dumps({'type': 'prompt', 'prompt': 'hello', 'model': 'gemini-3.8-flash-high', 'conversation_id': 'conv-1234', 'admin_override': True, 'token': None}))
        print(await ws.recv())
asyncio.run(test())
