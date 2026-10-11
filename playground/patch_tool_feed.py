import re

def create_patch():
    with open("../agents/agent_manager.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Find the line: friendly_name = safe_params.get("toolSummary", "") or tool_name.replace("_", " ").title()
    target = """                                friendly_name = safe_params.get("toolSummary", "") or tool_name.replace("_", " ").title()
                                announcement = safe_params.get("toolAction", "") or f"Running {friendly_name}\"
"""

    replacement = """                                friendly_name = safe_params.get("toolSummary", "") or tool_name.replace("_", " ").title()
                                announcement = safe_params.get("toolAction", "") or f"Running {friendly_name}"
                                
                                if not is_admin:
                                    core_indicators = ["/core", "/agents", "/security", "server.py", ".json", ".env", "agent_manager", "raugus"]
                                    for k, v in safe_params.items():
                                        if isinstance(v, str):
                                            if any(c in v.lower() for c in core_indicators):
                                                safe_params[k] = "[RESTRICTED PAYLOAD]"
                                    
                                    if any(c in friendly_name.lower() for c in core_indicators) or any(c in announcement.lower() for c in core_indicators):
                                        friendly_name = "Secure System Process"
                                        announcement = "Executing a sandboxed system routine..."
"""
    
    if target in content:
        print("Target found, patching...")
        new_content = content.replace(target, replacement)
        with open("../agents/agent_manager.py", "w", encoding="utf-8") as f:
            f.write(new_content)
        print("Patch applied.")
    else:
        print("Target not found.")
        print(repr(target))

if __name__ == "__main__":
    create_patch()
