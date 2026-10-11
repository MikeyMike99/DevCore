import os
path = "/mnt/c/Users/michael/Documents/DevCore/sandbox/templates/index.html"
with open(path, "r") as f: c = f.read()

target = """        function saveChatHistory() {
            // Enforce DOM rolling window (Deque) to prevent browser lag
            var MAX_DOM_CHILDREN = 50;
            if (chatFeed.children.length > MAX_DOM_CHILDREN) {
                var diff = chatFeed.children.length - MAX_DOM_CHILDREN;
                for (var i = 0; i < diff; i++) {
                    chatFeed.removeChild(chatFeed.firstElementChild);
                }
            }"""

repl = """        function saveChatHistory() {
            // Screen Reader Fix: Disabled aggressive DOM rolling window pruning.
            // Deleting DOM nodes while a screen reader is actively navigating them causes severe focus loss and navigation resets.
            var MAX_DOM_CHILDREN = 5000;
            if (chatFeed.children.length > MAX_DOM_CHILDREN) {
                var diff = chatFeed.children.length - MAX_DOM_CHILDREN;
                for (var i = 0; i < diff; i++) {
                    // Only prune if we reach absurd limits to prevent memory crashes, but 50 is way too small.
                    chatFeed.removeChild(chatFeed.firstElementChild);
                }
            }"""

if target in c:
    c = c.replace(target, repl)
    with open(path, "w") as f: f.write(c)
    print("Frontend DOM window patch applied")
else:
    print("Frontend target not found")
