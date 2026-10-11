import os
path = "/mnt/c/Users/michael/Documents/DevCore/sandbox/templates/index.html"
with open(path, "r") as f: c = f.read()

target = """                if (data.action && data.action.tool) {
                    var tName = data.action.tool.toLowerCase();
                    // Audio is handled in action_start to prevent overlapping
                }
                announce(data.action.announcement || 'Action complete');"""

repl = """                if (data.action && data.action.tool) {
                    var tName = data.action.tool.toLowerCase();
                    // Audio is handled in action_start to prevent overlapping
                }
                // Earcon Upgrade: Replaced robotic speech spam with a satisfying auditory pop
                if (typeof playNotificationSound === 'function') {
                    playNotificationSound();
                }"""

if target in c:
    c = c.replace(target, repl)
    with open(path, "w") as f: f.write(c)
    print("Frontend audio patch applied")
else:
    print("Frontend audio target not found")
