---
name: devcore-media-player
description: >-
  Use this skill to spawn the DevCore Accessible Video Player, manage playlists, and resume playback. Use when the user asks to watch a video, view a playlist, or resume playing their last video.
---

# DevCore Accessible Video Player Skill

This skill explains how to correctly interface with the Zero-Trust DevCore Media Player (`video_application.html`).

## 1. Spawning the Player
To render the video player to the user, you must output a raw HTML iframe directly in your chat response.
**IMPORTANT:** The iframe must include `allow="autoplay"` to delegate user gestures, and the URL must point to `/plugin/media`.

```html
<iframe src="/plugin/media?v=[VIDEO_ID]" width="100%" height="800px" style="border:none;" allow="autoplay; encrypted-media; fullscreen; picture-in-picture"></iframe>
```

## 2. Resuming Playback
The frontend automatically syncs its playback state to `sandbox/static/playback_state.json` every 5 seconds.
If the user asks to "resume" or "continue watching":
1. Read `/mnt/c/Users/michael/Documents/devcore/sandbox/static/playback_state.json`.
2. Extract the `video_id` and the `timestamp` (in seconds).
3. Inject the timestamp into the iframe URL using the `start=` parameter:
```html
<iframe src="/plugin/media?v=[VIDEO_ID]&start=[TIMESTAMP]" width="100%" height="800px" style="border:none;" allow="autoplay; encrypted-media; fullscreen; picture-in-picture"></iframe>
```

## 3. Managing the Playlist
The active playlist is stored at `/mnt/c/Users/michael/Documents/devcore/sandbox/static/playlist.json` as an array of JSON objects (e.g. `[{"id": "...", "title": "..."}]`).
The frontend natively reads this JSON file to render an accessible playlist UI below the video description.

When the user asks to:
- **Add a video**: Use Python or bash to append a JSON object (`{"id": "...", "title": "..."}`) to `playlist.json`.
- **Remove a video**: Use Python or bash to splice the item out of `playlist.json`.
- **View the playlist**: You can either read `playlist.json` and summarize it in chat, or simply spawn the iframe player (which will natively render the playlist UI on its own).

## 4. YouTube Music Restrictions
Be aware that YouTube restricts official music videos (like VEVO tracks) from being played in customized embedded players. 
If the user asks to add a music video to the playlist:
1. **Warn the user** using plain, non-technical language (e.g., "YouTube usually blocks official music videos from playing directly in our custom player"). Do NOT use technical jargon like "DRM", "Error 150", or "Syndication Restrictions".
2. Do not attempt to bypass this via automation (like trying to magically close cross-origin tabs). 
3. Reassure them that the media player handles this gracefully: if a video is blocked, a "Watch on YouTube" button will safely appear so they can open it in a new tab without breaking their experience.
