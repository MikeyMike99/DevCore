[ "$(tr -d '\r\n ' < count.txt 2>/dev/null)" = "5" ] && echo "correct" || { echo "count.txt is missing or the number is wrong"; exit 1; }
