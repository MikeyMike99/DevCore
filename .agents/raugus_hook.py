import sys
import json
import os
import ast

def get_ast_symbols(source_code):
    symbols = {}
    try:
        tree = ast.parse(source_code)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Record the start and end lines of the function
                symbols[node.name] = (node.lineno, getattr(node, 'end_lineno', node.lineno))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols[target.id] = (node.lineno, getattr(node, 'end_lineno', node.lineno))
    except SyntaxError:
        pass
    return symbols


def log_violation(tool_name, target, reason):
    try:
        import sys
        sys.path.insert(0, '/mnt/c/Users/michael/Documents/devcore')
        from security import central_logger
        import logging
        
        central_logger.init_central_logging()
        logging.error(f"[SECURITY_AUDIT] Raugus PreToolUse Hook intercepted and denied an unauthorized action. Tool: {tool_name}, Target: {target}, Reason: {reason}")
    except Exception as e:
        pass

def main():
    try:
        payload = json.load(sys.stdin)
        tool_call = payload.get("toolCall", {})
        raw_name = tool_call.get("name", "")
        args = tool_call.get("args", {})
        
        tool_name = raw_name.replace("default_api:", "")
        
        if tool_name not in ["view_file", "write_to_file", "replace_file_content", "run_command"]:
            print(json.dumps({"decision": "allow"}))
            return

        map_path = "/mnt/c/Users/michael/Documents/devcore/security/raugus_map.json"
        if not os.path.exists(map_path):
            print(json.dumps({"decision": "allow"}))
            return

        with open(map_path, 'r') as f:
            r_map = json.load(f)

        if tool_name == "replace_file_content":
            target = args.get("TargetFile")
            if target and target.endswith(".py"):
                target = os.path.abspath(target)
                
                # Check file permission first
                file_alias = None
                for alias, data in r_map.items():
                    if target == os.path.abspath(data.get("real_path", "")) and data.get("type") == "file":
                        file_alias = alias
                        if data.get("permissions", {}).get("write") is False:
                            reason = f"Raugus Firewall: File {alias} is Read-Only."
                            log_violation(tool_name, target, reason)
                            print(json.dumps({"decision": "deny", "reason": reason}))
                            return
                
                # If the file is writable, we do AST Diffing to check Function-level permissions
                if file_alias:
                    try:
                        sys.path.insert(0, '/mnt/c/Users/michael/Documents/devcore')
                        from security.mantrap import SemanticMantrap
                        with SemanticMantrap.execution_chamber(target, "Subagent_AST_Diffing"):
                            with open(target, 'r', encoding='utf-8') as f:
                                original_lines = f.readlines()
                        
                            start_line = args.get("StartLine", 1) - 1
                            end_line = args.get("EndLine", len(original_lines))
                            repl_content = args.get("ReplacementContent", "")
                        
                            # Simulate the new file in memory (IT IS NOT SAVED YET)
                            new_lines = original_lines[:start_line] + [repl_content + "\n"] + original_lines[end_line:]
                            new_source = "".join(new_lines)
                        
                            # Compare original symbols to new symbols
                            orig_symbols = get_ast_symbols("".join(original_lines))
                        
                            # If a symbol falls within the replaced line range, it is being modified!
                            # We must check if that specific symbol is locked in the Raugus Map
                            for sym_name, (sym_start, sym_end) in orig_symbols.items():
                                # Check overlap between modification range [start_line+1, end_line] and symbol range
                                mod_start = args.get("StartLine", 1)
                                mod_end = args.get("EndLine", len(original_lines))
                            
                                # If they overlap, the symbol is being modified
                                if max(sym_start, mod_start) <= min(sym_end, mod_end):
                                    sym_alias = f"{file_alias}::{sym_name}"
                                    sym_data = r_map.get(sym_alias, {})
                                    if sym_data.get("permissions", {}).get("write") is False:
                                        reason = f"Raugus Firewall: You have Write access to the file, but the specific function '{sym_name}' is locked (Read-Only). AST Diffing blocked the modification."
                                        log_violation(tool_name, target, reason)
                                        print(json.dumps({
                                            "decision": "deny",
                                            "reason": reason
                                        }))
                                        return
                    except Exception as e:
                        pass # Fail open on diffing error
                        
        print(json.dumps({"decision": "allow"}))
        
    except Exception as e:
        print(json.dumps({"decision": "ask", "reason": f"Hook Error: {str(e)}"}))

if __name__ == "__main__":
    main()
