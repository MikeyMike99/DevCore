cmp -s evidence.log "$LAB/seed/auth.log" || { echo "evidence.log is missing or was changed"; exit 1; }
[ "$(tr -d '\r\n ' < evidence.sha256 2>/dev/null)" = "$(sha256sum "$LAB/seed/auth.log" | cut -d' ' -f1)" ] && echo "hash matches" || { echo "evidence.sha256 is missing or wrong"; exit 1; }
