import os
path = "/mnt/c/Users/michael/Documents/DevCore/sandbox/templates/index.html"
with open(path, "r") as f: c = f.read()

target = """                    rawEditor.value = 'Decrypting and loading artifact...';
                    article.classList.add('is-flipped');
                    var flipBack = article.querySelector('.flip-back');
                    if (flipBack) flipBack.removeAttribute('aria-hidden');
                
                try {
                    var res = await fetch('/api/artifacts?path=' + encodeURIComponent(url), { headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('agy_auth_token') || '') } });
                    var data = await res.json();
                    if (data.content) {
                        rawEditor.value = data.content;
                        article.dataset.artifactUrl = url;
                        // Force screen reader focus into the edit box so they instantly know it flipped!
                        rawEditor.focus();
                    } else {"""

repl = """                    rawEditor.value = 'Decrypting and loading artifact...';
                    article.classList.add('is-flipped');
                    var flipBack = article.querySelector('.flip-back');
                    if (flipBack) flipBack.removeAttribute('aria-hidden');
                    // Force screen reader focus into the edit box IMMEDIATELY so they instantly know it flipped!
                    rawEditor.focus();
                
                try {
                    var res = await fetch('/api/artifacts?path=' + encodeURIComponent(url), { headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('agy_auth_token') || '') } });
                    var data = await res.json();
                    if (data.content) {
                        rawEditor.value = data.content;
                        article.dataset.artifactUrl = url;
                    } else {"""

if target in c:
    c = c.replace(target, repl)
    with open(path, "w") as f: f.write(c)
    print("Frontend patch applied")
else:
    print("Frontend target not found")
