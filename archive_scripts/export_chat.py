import urllib.request
import json
import sys

def export(conv_id):
    try:
        req = urllib.request.Request(f'http://127.0.0.1:5000/api/conversations/{conv_id}')
        response = urllib.request.urlopen(req)
        data = json.loads(response.read())
        items = data.get('items', [])
        
        filename = f'chat_export_{conv_id}.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            for item in items:
                step_type = item.get('step_type')
                if step_type == 'user_input':
                    f.write(f"\n[{item.get('created_at', '')}] User: {item.get('text', '')}\n")
                elif step_type == 'agent_response':
                    f.write(f"\n[{item.get('created_at', '')}] Agent: {item.get('text', '')}\n")
                elif step_type == 'tool':
                    tool_name = item.get('tool_name', '')
                    params = item.get('tool_info', {}).get('parameters', {})
                    f.write(f"\n[{item.get('created_at', '')}] [Tool Execution]: {tool_name}\n")
                    f.write(f"Parameters: {json.dumps(params, indent=2)}\n")
                    if 'result' in item:
                        f.write(f"Result: {item.get('result', {}).get('output', '')[:500]}...\n")
        print(f"Exported to {filename}")
    except Exception as e:
        print(f"Failed to export: {e}")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        export(sys.argv[1])
    else:
        print("Usage: python export_chat.py <conversation_id>")
