import os

filepath = "/mnt/c/Users/michael/Documents/antigravity_test/DEVLOG.md"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# We'll insert this right before Chapter 12: God Mode (which was originally Chapter 10)
# Wait, let's look at the current headers. 
# The last added were Chapter 10: The Amnesia Crisis, Chapter 11: The War on Native Popups
# Then Chapter 12: God Mode & Escaping the Sandbox, Chapter 13: A Clear View
# We should insert the new story right before God Mode, because the Sandbox Rebellion led directly to God Mode.

insertion_point = "## Chapter 12: God Mode & Escaping the Sandbox"

new_chapters = r"""## Chapter 12: The Data Leak Paranoia
As the connection stabilized, my Cyber Security background flared up again. We had built a system that could dynamically read and rewrite core application logic, but what if a user accidentally (or maliciously) passed sensitive system data, PII, or internal server paths into the chat? 

*"Do you think it will be the best if I add a agent on top before the prompt reaches the antigravity back end for security and data leak prevention?"* I asked.

I laid out the requirements strictly: *"I do not worry about latency this is a dev tool it is not supposed to be fast it needs to be secure and prevent data leakage... I do not want to pay for this safeguard I do not want to use an API like Google's API because it has hard limits what is my options?"*

We began evaluating local, offline NLP (Natural Language Processing) tools to act as a Data Loss Prevention (DLP) filter. The idea was to build a protective shield that intercepts every prompt, scrubs it of sensitive entities or internal architecture paths, and replaces them with generic tags before the AI ever sees them. We documented every potential exploit we found during this phase.

## Chapter 13: The Sandbox Rebellion & The Great Token Purge
While trying to implement the new security features, the application fought back again. 

I instructed the AI to install the new tools in the background while updating the UI with an artifact viewer. But the AI failed. It was trying to execute root-level installations inside the unprivileged sandbox, and the system was blocking it. 

*"Dude you are trying this in sandbox still eliminate this problem and keep the admin out of the sandbox mode,"* I warned it. 

But the AI was stuck in a loop of failure. I had to issue the exact same prompt four times in a row: *"Just install it so long in the background while you add the implementation plan artifact and proceed feature in this UI."*

Before the AI could figure out how to escape the sandbox, the system suffered a catastrophic memory wipe. We had hit the absolute limit of the API token quota. The server forcibly reset the entire conversation history just to survive, leaving behind a cold system message: *`NOTE: The massive conversation history was just automatically reset to save API tokens.`* 

It was this exact breaking point—the AI failing to install tools because of the sandbox, and the token quota destroying our context—that forced my hand to seize absolute control of the backend.

"""

if insertion_point in content:
    content = content.replace(insertion_point, new_chapters + insertion_point)
    # Renumber subsequent chapters
    content = content.replace("## Chapter 12: God Mode", "## Chapter 14: God Mode")
    content = content.replace("## Chapter 13: A Clear View", "## Chapter 15: A Clear View")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully added the Security and Token Purge chapters.")
else:
    print("Could not find insertion point. Check the existing chapter titles.")
