from mcp.server.mcpserver import MCPServer
import os
import sys
import logging
import traceback

# 1. Setup Isolated Logging
LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs", "plugin_line_editor.log"))
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] MCP_LINE_EDITOR: %(message)s'
)
logging.info("Next-Gen Line Editor MCP Server Booting (v1.2 - Backup Removed for Zero-Trust)...")

mcp = MCPServer("Line Editor")

@mcp.tool()
def edit_lines(target_file: str, start_line: int, end_line: int, new_code: str) -> str:
    """
    Replace a specific block of lines in a target file with new code.
    This eliminates the exact-match exactness trap by relying entirely on line numbers.
    Lines are 1-indexed. start_line and end_line are inclusive.
    Can also be used to append to the end of a file by specifying a start_line > current line count.
    """
    logging.info(f"Received request to edit {target_file} from line {start_line} to {end_line}")
    
    # If file doesn't exist, treat it as an empty file creation
    lines = []
    if os.path.exists(target_file):
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            err = f"Error reading file '{target_file}': {str(e)}"
            logging.error(err)
            return err
    else:
        logging.info(f"Target file {target_file} does not exist. It will be created.")
        
    try:
        # Validate indices
        if start_line < 1:
            err = "Error: start_line must be >= 1"
            logging.error(err)
            return err
        if start_line > end_line:
            err = "Error: start_line cannot be greater than end_line"
            logging.error(err)
            return err
            
        # Ensure new_code ends with newline
        if new_code and not new_code.endswith('\n'):
            new_code += '\n'
            
        if start_line > len(lines):
            # Appending logic with padding if there's a gap
            padding = ['\n'] * (start_line - len(lines) - 1)
            lines.extend(padding)
            lines.append(new_code)
            final_content = lines
            action_desc = f"Appended code starting at line {start_line}"
        else:
            # Splicing logic
            idx_start = start_line - 1
            idx_end = end_line
            before = lines[:idx_start]
            after = lines[idx_end:]
            final_content = before + [new_code] + after
            action_desc = f"Replaced lines {start_line} through {end_line}"
            
        with open(target_file, "w", encoding="utf-8") as f:
            f.writelines(final_content)
            
        msg = f"Success! {action_desc} in {os.path.basename(target_file)}."
        logging.info(msg)
        return msg
    except Exception as e:
        err_trace = traceback.format_exc()
        logging.critical(f"FATAL ERROR during file operation on {target_file}:\n{err_trace}")
        return f"Error modifying file: {str(e)}"

if __name__ == "__main__":
    try:
        mcp.run()
    except Exception as e:
        logging.critical(f"MCP Server crashed: {traceback.format_exc()}")
