with open("test_script.js", "r", encoding="utf-8") as f:
    text = f.read()
open_braces = text.count("{")
close_braces = text.count("}")
open_parens = text.count("(")
close_parens = text.count(")")
print(f"Braces: {open_braces} open, {close_braces} close")
print(f"Parens: {open_parens} open, {close_parens} close")
