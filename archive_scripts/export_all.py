import json
import re

def export_transcript(path, output, title):
    with open(path, 'r', encoding='utf-8') as f:
        msgs = [json.loads(line) for line in f]

    with open(output, 'w', encoding='utf-8') as out:
        out.write(f"# {title}\n\n")
        for m in msgs:
            if m.get("type") == "USER_INPUT":
                out.write("### USER\n")
                content = m.get("content", "").replace("<USER_REQUEST>", "").replace("</USER_REQUEST>", "").strip()
                out.write(content + "\n\n")
            elif m.get("type") == "PLANNER_RESPONSE":
                out.write("### AI\n")
                content = m.get("content", "").strip()
                content = re.sub(r'\[ARTIFACT: .*?\]\nPath: .*?\nLast Edited: .*?\n', '', content)
                if content:
                    out.write(content + "\n\n")
                
                tool_calls = m.get("tool_calls", [])
                for tc in tool_calls:
                    fn_name = tc.get("function", {}).get("name", "")
                    args = tc.get("function", {}).get("arguments", {})
                    try:
                        if isinstance(args, str):
                            args = json.loads(args)
                    except:
                        pass
                    
                    if fn_name == "default_api:run_command":
                        cmd = args.get("CommandLine", "")
                        out.write("**[Action: Ran Command]**\n`ash\n" + cmd + "\n`\n\n")
                    elif fn_name == "default_api:write_to_file":
                        fpath = args.get("TargetFile", "")
                        out.write(f"**[Action: Wrote File]** {fpath}\n\n")
                    elif fn_name == "default_api:replace_file_content":
                        fpath = args.get("TargetFile", "")
                        out.write(f"**[Action: Edited File]** {fpath}\n\n")
                    elif fn_name == "default_api:view_file":
                        fpath = args.get("AbsolutePath", "")
                        out.write(f"**[Action: Read File]** {fpath}\n\n")
                    else:
                        out.write(f"**[Action: {fn_name}]**\n\n")
                out.write("\n")

export_transcript(
    '/mnt/c/Users/michael/.gemini/antigravity/brain/f5e3c6ba-71ee-403b-8619-b0e1792b8d20/.system_generated/logs/transcript_full.jsonl',
    '/mnt/c/Users/michael/Documents/antigravity_test/chat_export.md',
    'Web Application Debugging Chat Export'
)
export_transcript(
    '/home/michael/.gemini/antigravity-cli/brain/2292e072-e533-4e9a-8f00-722ba6d8acc7/.system_generated/logs/transcript_full.jsonl',
    '/mnt/c/Users/michael/Documents/antigravity_test/previous_chat_export.md',
    'Web Application Debugging (Previous Session Export)'
)
print("Export complete with commands!")
