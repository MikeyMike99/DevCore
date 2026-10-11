# Next-Gen Line Editor Protocol (MCP Tooling)

You have access to a custom MCP tool called `edit_lines`. 

**CRITICAL DIRECTIVE:**
If you are tasked with modifying an existing file that is large, or if you ever experience a "target content not found" error when attempting to use the standard `replace_file_content` tool, you MUST immediately pivot to using `edit_lines`.

### Workflow:
1. **Targeting:** Use the `view_file` tool to inspect the document and determine the exact, 1-indexed `start_line` and `end_line` of the code block you want to replace.
2. **Execution:** Call the `edit_lines` tool, providing the `target_file`, the `start_line`, the `end_line`, and the complete `new_code` that will replace that block.
3. **No Character-Matching:** Do not attempt to use `replace_file_content` again if it fails once due to whitespace or character mismatch. Rely entirely on the coordinate-based line editor.
