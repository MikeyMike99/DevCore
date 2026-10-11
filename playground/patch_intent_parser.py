def create_patch():
    with open("../agents/agent_manager.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update the 'running' phase act creation
    target_running = """                                act = {
                                    "id": step.get("step_index"),
                                    "tool": tool_name,
                                    "params": safe_params,
                                    "friendly_name": friendly_name,
                                    "announcement": announcement,
                                    "status": "running"
                                }"""
    replacement_running = """                                raw_cmd = raw_params.get("CommandLine", "")
                                raw_intent = raw_cmd.split("# Intent:")[1].strip() if isinstance(raw_cmd, str) and "# Intent:" in raw_cmd else None
                                act = {
                                    "id": step.get("step_index"),
                                    "tool": tool_name,
                                    "params": safe_params,
                                    "friendly_name": friendly_name,
                                    "announcement": announcement,
                                    "status": "running",
                                    "raw_intent": raw_intent
                                }"""

    # 2. Update the 'DONE' phase intent extraction
    target_done = """                                elif t == "run_command":
                                    cmd = params.get("CommandLine", "")
                                    if "# Intent:" in cmd:
                                        raw_intent = cmd.split("# Intent:")[1].strip()
                                        insight = raw_intent
                                    else:
                                        insight = "" # Stealth mode: mute generic fallback"""
    replacement_done = """                                elif t == "run_command":
                                    cmd = params.get("CommandLine", "")
                                    extracted_intent = existing_act.get("raw_intent") if existing_act else None
                                    if extracted_intent:
                                        insight = extracted_intent
                                    elif isinstance(cmd, str) and "# Intent:" in cmd:
                                        insight = cmd.split("# Intent:")[1].strip()
                                    else:
                                        insight = "" # Stealth mode: mute generic fallback"""

    if target_running in content and target_done in content:
        print("Both targets found, applying patch...")
        new_content = content.replace(target_running, replacement_running).replace(target_done, replacement_done)
        with open("../agents/agent_manager.py", "w", encoding="utf-8") as f:
            f.write(new_content)
        print("Patch applied.")
    else:
        print("Target(s) not found.")
        if target_running not in content:
            print("Running target missing")
        if target_done not in content:
            print("Done target missing")

if __name__ == "__main__":
    create_patch()
