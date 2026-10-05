import json
with open('/mnt/c/Users/michael/Documents/devcore/sandbox/playlist.json', 'r') as f:
    playlist = json.load(f)

ids = [item['id'] for item in playlist]
playlist_str = ",".join(ids)

markdown = "# Your Active Playlist\n\n"
for i, item in enumerate(playlist):
    markdown += f"{i+1}. **{item['title']}** (`{item['id']}`)\n"

markdown += "\n---\n"
markdown += f'<iframe src="/plugin/media?v={ids[0]}&playlist={playlist_str}" width="100%" height="800px" style="border:none;" allow="autoplay; encrypted-media; fullscreen; picture-in-picture"></iframe>\n'

with open('/home/michael/.gemini/antigravity-cli/brain/7eb981e3-3a00-4f8f-9238-d0902064a212/Current_Playlist.md', 'w') as f:
    f.write(markdown)
