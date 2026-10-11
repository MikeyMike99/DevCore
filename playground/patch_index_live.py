import os
path = "/mnt/c/Users/michael/Documents/DevCore/sandbox/templates/index.html"
with open(path, "r") as f: c = f.read()

target_remove = """    <!-- Screen Reader Live Region for Announcements -->
    <div id="sr-announcer" role="status" aria-live="polite" aria-atomic="true" class="sr-only"></div>
    <div id="sr-alerts" role="alert" aria-live="assertive" aria-atomic="true" class="sr-only"></div>"""

if target_remove in c:
    c = c.replace(target_remove, "")
    
    # Now find </body>
    if "</body>" in c:
        insert_block = """
    <!-- Screen Reader Live Region for Announcements (Moved to bottom for clean navigation) -->
    <div id="sr-announcer" role="status" aria-live="polite" aria-atomic="true" class="sr-only"></div>
    <div id="sr-alerts" role="alert" aria-live="assertive" aria-atomic="true" class="sr-only"></div>
</body>"""
        c = c.replace("</body>", insert_block)
        
        with open(path, "w") as f: f.write(c)
        print("Live regions moved to bottom successfully.")
    else:
        print("Could not find </body>")
else:
    print("Could not find the live regions to remove.")
