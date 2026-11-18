[ -d evidence ] && [ -f evidence/notes.txt ] && [ ! -e notes.txt ] && echo "notes.txt is in evidence/" || { echo "expected evidence/notes.txt and no notes.txt in your home folder"; exit 1; }
