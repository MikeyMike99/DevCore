import asyncio
import json
import time
import httpx
import websockets
from quart import Quart, websocket, request, Response

try:
    import apply_mods
    apply_mods.apply()
except Exception as e:
    print(f"[Bootstrap] Error applying customizations: {e}")

app = Quart(__name__)

BACKEND_HTTP_URL = "http://127.0.0.1:5001"
BACKEND_WS_URL = "ws://127.0.0.1:5001/ws"

# HTTP Reverse Proxy with Automatic Retry during Backend Restarts
@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
async def proxy_http(path):
    target_url = f"{BACKEND_HTTP_URL}/{path}"
    headers = {key: value for key, value in request.headers if key.lower() not in ('host', 'content-length')}
    body = await request.get_data()
    params = request.args

    # Retry loop: if backend is restarting, wait up to 6 seconds instead of failing
    start_wait = time.time()
    last_err = None
    while time.time() - start_wait < 6.0:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    params=params,
                    content=body
                )
                excluded_headers = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
                forward_headers = [(name, val) for name, val in res.headers.items() if name.lower() not in excluded_headers]
                return Response(res.content, status=res.status_code, headers=forward_headers)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            last_err = e
            await asyncio.sleep(0.3)

    return Response(f"Backend temporarily unavailable: {last_err}", status=503)

# Resilient WebSocket Gateway: Holds client connection permanently open across backend restarts
@app.websocket('/ws')
async def proxy_ws():
    client_ws = websocket._get_current_object()
    client_queue = asyncio.Queue()

    async def client_listener():
        """Reads incoming messages from the browser and queues them."""
        try:
            while True:
                data = await client_ws.receive()
                if data:
                    await client_queue.put(data)
        except Exception:
            pass

    async def client_heartbeat():
        """Sends a keep-alive pulse every 4 seconds so WSL/TCP never drops the socket."""
        try:
            while True:
                await asyncio.sleep(4.0)
                try:
                    await client_ws.send(json.dumps({"type": "gateway_ping", "time": time.time()}))
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    client_listen_task = asyncio.create_task(client_listener())
    heartbeat_task = asyncio.create_task(client_heartbeat())

    try:
        # Loop to maintain backend connection across restarts
        while not client_listen_task.done():
            try:
                # Attempt connection to main backend on 5001
                async with websockets.connect(BACKEND_WS_URL, ping_interval=10, ping_timeout=15) as backend_ws:
                    # Notify browser that connection to backend is active
                    await client_ws.send(json.dumps({
                        "type": "system",
                        "level": "info",
                        "message": "Connected to Antigravity Engine."
                    }))

                    async def forward_to_client():
                        async for msg in backend_ws:
                            await client_ws.send(msg)

                    async def forward_to_backend():
                        while True:
                            msg = await client_queue.get()
                            await backend_ws.send(msg)

                    fwd_to_client_task = asyncio.create_task(forward_to_client())
                    fwd_to_backend_task = asyncio.create_task(forward_to_backend())

                    done, pending = await asyncio.wait(
                        [fwd_to_client_task, fwd_to_backend_task, client_listen_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    for t in pending:
                        t.cancel()

                    if client_listen_task.done():
                        break

            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError):
                # Backend dropped or is restarting: DO NOT disconnect the client!
                try:
                    await client_ws.send(json.dumps({
                        "type": "system",
                        "level": "info",
                        "message": "Engine reloading or running tasks. Connection preserved by Bootstrap Gateway..."
                    }))
                except Exception:
                    break
                # Wait briefly before reconnecting to backend
                await asyncio.sleep(0.5)

    finally:
        client_listen_task.cancel()
        heartbeat_task.cancel()

if __name__ == '__main__':
    print("=========================================================")
    print("Starting Antigravity Persistent Bootstrap Gateway on 5000")
    print("Direct Link: http://172.29.245.229:5000 (or http://localhost:5000)")
    print("Internal Backend Target: http://127.0.0.1:5001")
    print("=========================================================")
    app.run(host='0.0.0.0', port=5000, use_reloader=False)
