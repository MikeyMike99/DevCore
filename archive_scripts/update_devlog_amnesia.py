import os

filepath = "/mnt/c/Users/michael/Documents/antigravity_test/DEVLOG.md"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

old_chapter_8 = "## Chapter 8: Amnesia and The Popup Trap\nAs the portal expanded, we faced two massive friction points that threatened to ruin the experience.\n\nThe first was the \"Amnesia Bug.\" Every time the backend server restarted—which happened frequently during development—the AI would completely forget everything we were working on. I had to constantly remind it what directory we were in and what the context was. The continuous interruptions (\"we got interrupted again... I think we got interrupted by the restart?\") were draining.\n\nThe second issue was the UI feedback loop. The web portal relied on standard native browser popups for alerts (like \"Reload error: There is no websocket in this context\"). For a sighted user, clicking \"OK\" on a popup is mildly annoying. For a screen reader user, it is a jarring, focus-stealing trap. I explicitly pleaded with the AI: *\"I do not like all these browser popups... I just need a better feedback and response system.\"*\n\nWe had to rip out the native `window.confirm` dialogues entirely. We replaced them with semantic HTML `<dialog>` elements. These custom modals naturally trap keyboard focus and announce themselves cleanly to the screen reader without fighting the browser's native alert systems. We finally had a UI that respected accessibility as a priority."

new_chapters = r"""## Chapter 8: The Amnesia Crisis
As the portal expanded, we faced a massive friction point that nearly broke the project. The AI was suffering from severe short-term memory loss. 

Every time the backend server restarted—which happened constantly as we added new features—the AI would completely forget our conversation, our active workspace, and our goals. The chat logs from this period are incredibly frustrating to read back. 

*"What directory are you looking at right now?"* I had to ask it, over and over.
*"Why is our sessions not persistent?"*
*"Are you not following our conversation, what is happening here?"*

The AI, stripped of its context, would regress. It would forget we had built a Web UI and start telling me to run raw bash commands in the terminal again. My frustration peaked: *"I do not want to run commands I just want to prompt and press buttons. Dude, we created a web interface... this is the last time I am prompting you to add it so that our sessions can be persistent even if the server restarts."*

This crisis forced us to engineer a robust Session and Workspace Manager directly into the backend. We couldn't rely on the AI's volatile memory. We built local state files that strictly bound the AI to a specific project directory (`C:\Users\michael\Documents\antigravity_test`) and a specific conversation history. From that point on, if the server crashed, the AI woke up exactly where it left off, context intact.

## Chapter 9: The War on Native Popups
The second major issue was the UI feedback loop. The web portal initially relied on standard native browser popups for alerts (like *"Reload error: There is no websocket in this context"*). 

For a sighted user, clicking "OK" on a popup is mildly annoying. For a screen reader user, it is a jarring, focus-stealing trap that completely disrupts the flow of work. I explicitly pleaded with the AI: *"I do not like all these browser popups... I just need a better feedback and response system."*

We had to rip out the native `window.confirm` and `alert()` dialogues entirely. We replaced them with semantic HTML `<dialog>` elements. These custom modals naturally trap keyboard focus and announce themselves cleanly to the NVDA screen reader without fighting the browser's native alert systems. We finally had a UI that respected accessibility as an absolute priority."""

if old_chapter_8 in content:
    content = content.replace(old_chapter_8, new_chapters)
    # Renumber subsequent chapters
    content = content.replace("## Chapter 9: God Mode", "## Chapter 10: God Mode")
    content = content.replace("## Chapter 10: A Clear View", "## Chapter 11: A Clear View")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully added the Amnesia Crisis chapter.")
else:
    print("Could not find insertion point. The old text may have been altered.")
