[ "$(tr -d '\r\n ' < secret.txt 2>/dev/null)" = "siraugga" ] && echo "secret decoded" || { echo "secret.txt is missing or not the decoded secret"; exit 1; }
