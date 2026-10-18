[//]: # (DOC_ID: SIRA-DEV-CINEMATIC_TTS_NARR | VERSION: v1.2 | SCOPE: DEV)

# Architectural Blueprint: Cinematic TTS & In-Game Narrator

[//]: # (SECTION_ID: SIRA-DEV-CINEMATIC_TTS_NARR-SEC-1)
## 1. The Vision
[//]: # (SECTION_ID: SIRA-DOC-CINEMATIC_TTS_-SEC-1)
To transcend the standard chat interface and build an immersive, highly accessible auditory experience. By integrating a Cinematic TTS engine (e.g., ElevenLabs) via the **API Proxy Doctrine**, we will accomplish two major objectives:
1. **The Voice of Siraugga:** Give the autonomous agent a distinct, imposing, and cinematic persona.
2. **The In-Game Narrator:** Provide an API hook so the game engine can trigger the TTS plugin to narrate quests, ops briefings, and environmental lore, entirely bypassing the need for generic, monotonous OS-level screen readers (like NVDA or VoiceOver) during gameplay.

[//]: # (SECTION_ID: SIRA-DEV-CINEMATIC_TTS_NARR-SEC-2)
## 2. The Security Model (Zero-Trust)
[//]: # (SECTION_ID: SIRA-DOC-CINEMATIC_TTS_-SEC-2)
The core agent logic (`App Router Module`, `Task Orchestrator Module`) **must never** directly connect to the internet or external TTS APIs.
- The TTS engine will be built as an isolated **Peripheral Plugin** (`/plugin/tts`).
- The core agent simply outputs standard Markdown text.
- The Proxy Plugin intercepts that text, makes the outbound request to ElevenLabs, downloads the audio byte stream, and serves it to the frontend.
- If the API key is revoked or the cloud is compromised, the core agent's cognition is completely unaffected. It gracefully degrades back to text-only mode.

---

[//]: # (SECTION_ID: SIRA-DEV-CINEMATIC_TTS_NARR-SEC-3)
## 3. Step-by-Step Implementation Plan
[//]: # (SECTION_ID: SIRA-DEV-CINEMATIC_TTS_NARR-SEC-1)

### Phase 1: Infrastructure & Configuration
[//]: # (SECTION_ID: SIRA-DOC-CINEMATIC_TTS_-SEC-1)
- [ ] **Config Slot:** Add an `elevenlabs_api_key` and `voice_id` slot to `ui_config.json`.
- [ ] **Raugus Map Update:** Register a new abstract route for the TTS plugin in `security/raugus_map.json` (e.g., `devcore.plugins.Core Component`).
- [ ] **The Proxy Endpoint:** Create the backend route `@app.route('/api/plugin/tts')`. This endpoint will accept a JSON payload `{"text": "Hello"}` and return binary audio data (`audio/mpeg`).

[//]: # (SECTION_ID: SIRA-DEV-CINEMATIC_TTS_NARR-SEC-2)
### Phase 2: Frontend Chat Integration
[//]: # (SECTION_ID: SIRA-DOC-CINEMATIC_TTS_-SEC-2)
- [ ] **UI Toggle:** Inject a "Voice Mode" toggle button into `index.html` (accessible via keyboard).
- [ ] **Stream Interception:** Modify the WebSocket message handler (`socket.onmessage`). When Voice Mode is active, buffer incoming text chunks until a complete sentence is formed (using regex for punctuation like `.`, `!`, `?`).
- [ ] **The Audio Queue:** Send the buffered sentence to the `/api/plugin/tts` endpoint. Push the returned audio blob into a JavaScript playback queue so that sentences play seamlessly one after the other.

[//]: # (SECTION_ID: SIRA-DEV-CINEMATIC_TTS_NARR-SEC-3)
### Phase 3: The Game Engine Narrator Hook
[//]: # (SECTION_ID: SIRA-DOC-CINEMATIC_TTS_-SEC-3)
- [ ] **The In-Game Endpoint:** Expose a secure, local-only REST API endpoint specifically for the game client (e.g., `/api/game/narrate`).
- [ ] **Payload Structure:** Allow the game engine to send payloads like `{"quest_id": "OP_WINTER", "text": "Infiltrate the compound.", "priority": "high"}`.
- [ ] **Audio Handoff:** The backend passes the request through the TTS proxy and streams the cinematic audio directly back to the game engine's audio mixer.

[//]: # (SECTION_ID: SIRA-DEV-CINEMATIC_TTS_NARR-SEC-4)
## 4. Hardware/Network Considerations
[//]: # (SECTION_ID: SIRA-DOC-CINEMATIC_TTS_-SEC-4)
- **Latency:** Because cloud TTS introduces a ~500ms delay, the frontend audio queue is critical. We must start generating audio for sentence 2 while sentence 1 is still playing.
- **Caching:** Implement a local audio cache (`/sandbox/cache/tts_audio/`) for static game lore. If the narrator reads a quest briefing once, save the audio hash. The next time a player triggers that quest, serve the local MP3 instead of making a costly API call.
