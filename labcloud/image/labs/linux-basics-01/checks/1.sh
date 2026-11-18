[ "$(tr -d '\r\n ' < hello.txt 2>/dev/null)" = "hello" ] && echo "hello.txt looks right" || { echo "hello.txt is missing or does not contain 'hello'"; exit 1; }
