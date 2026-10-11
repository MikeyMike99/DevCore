import os

filepath = "/mnt/c/Users/michael/Documents/antigravity_test/DEVLOG.md"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# I will insert this right after "Chapter 5: The Accessibility War" and before "Chapter 6: The Refresh Trap & Asynchronous Resiliency"
# Wait, chronologically, the dropouts happened in the evening of Sept 17th. 
# The UI clutter and Amnesia happened on the 17th as well.
# I'll insert these as Chapter 8 and 9, and bump the later ones. Let's find a good insertion point.

insertion_point = "## Chapter 8: The Amnesia Crisis"

new_chapters = """## Chapter 8: The Dropout Crisis & Connection Blocking
As the AI started performing heavier tasks—reading the game files, running static analysis, and rewriting code—the web portal began to crack under the load. 

The websocket connection between the browser and the server started violently dropping out. I was getting abruptly disconnected mid-conversation. I checked the logs and realized that whenever the AI executed a massive file write or a heavy system task, it was physically blocking the main server thread, cutting off the networking pipeline. 

My frustration hit a boiling point: *"I still get drop outs... make sure nothing blocks the connection when completing tasks or writing files. It should be non-blocking. Just fix it, drop outs like that is not acceptable."*

We had to fundamentally re-architect how the backend handled execution. We pushed all file I/O and task execution into strictly isolated, asynchronous background workers, ensuring that no matter how hard the AI was thinking or how many files it was modifying, the main websocket heartbeats would never be interrupted again.

## Chapter 9: The Quota Wall & Semantic Sessions
With the server finally stable and the connection solid, a new reality set in: we were moving too much data. Because the AI was reading the entire project context to understand the game state, we were burning through API limits at a terrifying rate. 

*"Dude, stop hitting my quota,"* I told the AI. But when it suggested I manually manage the files to save tokens, I refused: *"I am not doing it manually, that is why you are there."*

This forced us to overhaul how we managed chat history. The UI was currently cluttered with raw, ugly UUIDs for session names (like `Session a14-xyz...`), which made it impossible to know which chat contained what context. 

I demanded an upgrade: *"Add readable tags for the sessions in the interface and add a way for me to clear all conversations and sessions related to a project."* We implemented an auto-naming system that dynamically reads the content of the first interaction and semantically names the session in the sidebar. 

But I am a Cyber Security student; I don't just delete data. I instituted a strict data-retention policy: *"When deleting sessions, the conversations should be logged and protected under admin access only before clearing it from the history."* Now, when a user clicks 'Clear All' in the UI to save their quota, the system silently archives the conversation into an encrypted, admin-only vault before wiping it from the active memory.

"""

if insertion_point in content:
    content = content.replace(insertion_point, new_chapters + insertion_point)
    # Renumber subsequent chapters
    content = content.replace("## Chapter 8: The Amnesia", "## Chapter 10: The Amnesia")
    content = content.replace("## Chapter 9: The War on Native Popups", "## Chapter 11: The War on Native Popups")
    content = content.replace("## Chapter 10: God Mode", "## Chapter 12: God Mode")
    content = content.replace("## Chapter 11: A Clear View", "## Chapter 13: A Clear View")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully added the Dropout Crisis and Quota Wall chapters.")
else:
    print("Could not find insertion point. The old text may have been altered.")
