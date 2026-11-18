[ "$(tr -d '\r\n ' < attacker.txt 2>/dev/null)" = "203.0.113.9" ] && echo "correct" || { echo "attacker.txt is missing or not the right IP"; exit 1; }
