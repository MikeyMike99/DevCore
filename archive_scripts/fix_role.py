import re

html_path = 'templates/index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_js = """        try {
            var storedUser = localStorage.getItem('agy_user_data');
            if (storedUser && storedUser !== "undefined") {
                currentUser = JSON.parse(storedUser) || currentUser;
            }
        } catch (e) {}"""

new_js = """        try {
            var storedUser = localStorage.getItem('agy_user_data');
            if (storedUser && storedUser !== "undefined") {
                currentUser = JSON.parse(storedUser) || currentUser;
                
                // Force sync frontend role for upgraded admin account
                if (currentUser.username === 'admin' && currentUser.role === 'admin') {
                    currentUser.role = 'super_admin';
                    localStorage.setItem('agy_user_data', JSON.stringify(currentUser));
                }
            }
        } catch (e) {}"""

if old_js in content:
    content = content.replace(old_js, new_js)

old_ui_js = """                if (currentUser.role === 'admin') {
                    roleBadge.className = "px-1.5 py-0.5 rounded text-[10px] font-bold bg-teal-900 text-teal-300";
                } else if (currentUser.role === 'gamedev') {"""

new_ui_js = """                if (currentUser.role === 'admin' || currentUser.role === 'super_admin') {
                    roleBadge.className = "px-1.5 py-0.5 rounded text-[10px] font-bold bg-teal-900 text-teal-300";
                } else if (currentUser.role === 'gamedev') {"""

if old_ui_js in content:
    content = content.replace(old_ui_js, new_ui_js)

# Also fix the hardcoded span
old_html = '<span id="user-role-badge" class="px-1.5 py-0.5 rounded text-xs font-bold bg-teal-900 text-teal-300 w-fit">ADMIN</span>'
new_html = '<span id="user-role-badge" class="px-1.5 py-0.5 rounded text-xs font-bold bg-teal-900 text-teal-300 w-fit">SUPER_ADMIN</span>'
content = content.replace(old_html, new_html)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Role display fixed.")
