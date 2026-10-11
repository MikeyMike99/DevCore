import esprima
with open('script_1.js', 'r', encoding='utf-8') as f:
    js = f.read()
js = js.replace('<script>', '')
try:
    esprima.parseScript(js)
    print("JS parsed successfully. No syntax errors!")
except Exception as e:
    print(f"JS syntax error: {e}")
