import os

filepath = "/mnt/c/Users/michael/Documents/antigravity_test/DEVLOG.md"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Insert the new chapters right before Chapter 6 (so chronologically after Web Portal/Accessibility)
insertion_point = "## Chapter 6: Amnesia and The Popup Trap"

new_chapters = """## Chapter 6: The Refresh Trap & Asynchronous Resiliency
Even after the web portal was running, the architecture was incredibly fragile. I encountered a massive point of friction: whenever I refreshed the web page, the AI's background task would violently terminate. I was completely blind to what the AI was doing in the background—there was no status indicator—so I would refresh the page to see if it was done, only to accidentally kill the task entirely. 

I laid down a strict requirement: *"can we prevent that from happening again. so that a page refresh does not interrupt the task."*

We had to completely decouple the AI's execution engine from the browser's active session. We built a resilient asynchronous task manager on the backend. Now, the AI runs as an independent, detached worker. The browser can close, the page can reload, and the network can drop, but the agent will continue working on its tasks in the background, waiting for the UI to reconnect.

## Chapter 7: The Battle Against UI Clutter
With the tasks running safely, a new enemy appeared: UI bloat. 

When you navigate the web with a screen reader, information density is everything. The initial web portal was dumping massive amounts of raw server logs, code blocks, and unnecessary metadata directly into the chat interface. I was drowning in noise. *"The responses in the UI is to much it does not tell me what was completed... it should not expose logs and code directly in the UI. I am struggling to find where the message is actually starting because of all the headings."*

There was a fundamental misunderstanding initially that we needed to build custom screen-reader workarounds. I had to push back hard: *"Dude screenreaders are already optimised to interact in the browser effectively the html and tags and what not should just be correctly coded."*

We stripped the UI down to its semantic bones. We removed the chaotic headings. We hid the raw code and execution logs from the user interface, moving them to background files. The chat interface became clean, streamlined, and purely focused on conversation and results, allowing the screen reader to glide through the application natively.

"""

if insertion_point in content:
    content = content.replace(insertion_point, new_chapters + insertion_point)
    # Also bump the numbering of the subsequent chapters
    content = content.replace("## Chapter 6: Amnesia", "## Chapter 8: Amnesia")
    content = content.replace("## Chapter 7: God Mode", "## Chapter 9: God Mode")
    content = content.replace("## Chapter 8: A Clear View", "## Chapter 10: A Clear View")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully added the missing history chapters.")
else:
    print("Could not find insertion point.")
