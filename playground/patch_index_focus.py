import os
path = "/mnt/c/Users/michael/Documents/DevCore/sandbox/templates/index.html"
with open(path, "r") as f: c = f.read()

target = """                // Focus response heading for seamless screen reader accessibility
                var respHeading = currentAgentArticle.querySelector('h2');
                if (respHeading) {
                    respHeading.focus();
                }"""

repl = """                // Removed forced focus stealing! Let ARIA Live handle the announcement
                // so the user's cursor stays safely in the input box!"""

if target in c:
    c = c.replace(target, repl)
    with open(path, "w") as f: f.write(c)
    print("Frontend focus patch applied")
else:
    print("Frontend focus target not found")
