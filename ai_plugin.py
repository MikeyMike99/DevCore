from flask import Blueprint, jsonify, request, render_template, session
import sys
import os
import time
import threading
import asyncio

ai_path = os.path.dirname(os.path.abspath(__file__))
if ai_path not in sys.path:
    sys.path.append(ai_path)

from agent_manager import AgentTaskManager
from project_manager import ProjectManager
from session_manager import SessionManager
from security_manager import SecurityManager

ai_bp = Blueprint('ai', __name__, template_folder='templates', static_folder='static')

project_mgr = ProjectManager()
session_mgr = SessionManager()
agent_mgr = AgentTaskManager(project_manager=project_mgr)
security_mgr = SecurityManager()

# Background event loop for AI orchestration
ai_loop = asyncio.new_event_loop()
def run_ai_loop():
    asyncio.set_event_loop(ai_loop)
    ai_loop.run_forever()

threading.Thread(target=run_ai_loop, daemon=True).start()

@ai_bp.route('/')
def ai_home():
    return render_template('ai_index.html')

@ai_bp.route('/api/chat', methods=['POST'])
def start_chat():
    data = request.json
    prompt = data.get('prompt')
    
    # Authenticate via e_profile master session
    is_admin = session.get('is_admin', False)
    user = {"role": "admin" if is_admin else "modder", "username": session.get('username', 'guest')}
    
    if agent_mgr.is_running():
        # Instead of rejecting, send it as stdin input to the running agent setup
        asyncio.run_coroutine_threadsafe(
            agent_mgr.send_input(prompt), 
            ai_loop
        )
        return jsonify({"success": True, "message": "Input sent to agent"})

    # Dispatch to the background asyncio loop
    asyncio.run_coroutine_threadsafe(
        agent_mgr.start_task(prompt, user=user), 
        ai_loop
    )
    return jsonify({"success": True, "message": "Task started"})

@ai_bp.route('/api/stream', methods=['GET'])
def get_stream():
    # Fetch everything in the queue
    messages = []
    while agent_mgr.message_queue:
        messages.append(agent_mgr.message_queue.pop(0)["msg"])
    return jsonify({"messages": messages})

@ai_bp.route('/api/kill', methods=['POST'])
def kill_chat():
    asyncio.run_coroutine_threadsafe(agent_mgr.cancel_task(), ai_loop)
    return jsonify({"success": True})
