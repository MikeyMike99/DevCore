import asyncio
from core.routes.auth import get_current_user
from quart import Blueprint, request, jsonify, current_app, Response
import os, json, asyncio

projects_bp = Blueprint('projects_bp', __name__)

@projects_bp.route('/api/projects', methods=['GET'])
async def list_projects():
    projects = current_app.project_mgr.list_projects()
    active = current_app.project_mgr.active_project
    root_name = "Workspaces"
    return jsonify({"projects": projects, "active": active, "root_name": root_name})



@projects_bp.route('/api/projects', methods=['POST'])
async def create_project():
    data = await request.get_json() or {}
    name = data.get('name')
    try:
        current_app.project_mgr.create_project(name)
        return jsonify({"success": True, "project": name})
    except (ValueError, FileExistsError) as e:
        return jsonify({"error": str(e)}), 400



@projects_bp.route('/api/projects/active', methods=['POST'])
async def set_active_project():
    data = await request.get_json() or {}
    name = data.get('name')
    try:
        p = current_app.project_mgr.set_active_project(name)
        return jsonify({"success": True, "active": current_app.project_mgr.active_project, "path": p})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@projects_bp.route('/api/conversations', methods=['GET'])
async def list_conversations():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    limit = request.args.get('limit', default=10, type=int)
    # Threaded to prevent connection blocking
    convos, has_more = await asyncio.to_thread(current_app.session_mgr.list_conversations, current_app.project_mgr.active_project, user, limit)
    return jsonify({"conversations": convos, "has_more": has_more})



@projects_bp.route('/api/conversations/<conv_id>', methods=['GET'])
async def get_conversation(conv_id):
    # Threaded to prevent connection blocking
    items = await asyncio.to_thread(current_app.session_mgr.get_conversation_transcript, conv_id)
    return jsonify({"items": items})



@projects_bp.route('/api/conversations/<conv_id>', methods=['DELETE'])
async def delete_conversation(conv_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        success = await asyncio.to_thread(current_app.session_mgr.delete_session, conv_id, user)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to delete"}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@projects_bp.route('/api/projects/active/conversations', methods=['DELETE'])
async def clear_project_sessions():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    active_proj = current_app.project_mgr.active_project
    if not active_proj:
        return jsonify({"error": "No active project"}), 400

    try:
        # Threaded deletion prevents connection timeouts
        await asyncio.to_thread(current_app.session_mgr.delete_project_sessions, active_proj, user)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


