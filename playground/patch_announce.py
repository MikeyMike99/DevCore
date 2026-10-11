import os
path = "/mnt/c/Users/michael/Documents/DevCore/sandbox/templates/index.html"
with open(path, "r") as f: c = f.read()

target = """        function announce(text, isAlert) {
            var target = isAlert ? srAlerts : srAnnouncer;
            if (!target) return;
            target.textContent = '';
            setTimeout(function() {
                target.textContent = text;
            }, 50);
        }"""

repl = """        function announce(text, isAlert) {
            var target = isAlert ? srAlerts : srAnnouncer;
            if (!target) return;
            target.textContent = '';
            
            // Clear any previous cleanup timeout to prevent race conditions
            if (target.cleanupTimeout) clearTimeout(target.cleanupTimeout);
            
            setTimeout(function() {
                target.textContent = text;
                
                // Clear the text after 5 seconds!
                // This ensures the screen reader announces it instantly, but prevents the text 
                // from permanently lingering in the DOM and cluttering navigation at the top of the page.
                target.cleanupTimeout = setTimeout(function() {
                    target.textContent = '';
                }, 5000);
            }, 50);
        }"""

if target in c:
    c = c.replace(target, repl)
    with open(path, "w") as f: f.write(c)
    print("Announce patch applied")
else:
    print("Announce target not found")
