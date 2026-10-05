
        // --- INJECTED AGENT LOGGING ---
        function logToAgent(level, msg) {
            try {
                const timestamp = new Date().toISOString();
                const logLine = `[${timestamp}] [${level}] ${msg}`;
                
                // Display locally
                const dbg = document.getElementById('debugLog');
                if (dbg) {
                    dbg.style.display = 'block';
                    dbg.innerHTML += logLine + '<br>';
                }

                // Send to agent backend
                fetch('/api/artifacts/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: 'client_debug.txt',
                        content: logLine + '\n',
                        append: true
                    })
                }).catch(e => {});
            } catch (e) {}
        }

        window.onerror = function(msg, url, lineNo, columnNo, error) {
            logToAgent('ERROR', `${msg} at ${lineNo}:${columnNo}`);
            return false;
        };

        const originalConsoleError = console.error;
        console.error = function(...args) {
            logToAgent('CONSOLE_ERR', args.join(' '));
            originalConsoleError.apply(console, args);
        };
        
        logToAgent('INFO', 'video_application.html loaded. Waiting for YouTube API...');
        // --- END LOGGING ---

        // Data injected by Agent
        const VIDEO_ID = {{ video_id | default("jNQXAC9IVRw") | tojson | safe }};
        
        let player;
        let isPlaying = false;
        let scrubberInterval;

        function onYouTubeIframeAPIReady() {
            logToAgent('INFO', 'onYouTubeIframeAPIReady fired. Initializing player...');
            const autoplay = document.getElementById('chkAutoplay').checked ? 1 : 0;
            
            try {
                player = new YT.Player('ytplayer', {
                height: '100%',
                width: '100%',
                videoId: VIDEO_ID,
                playerVars: {
                    'playsinline': 1,
                    'controls': 1, // Temporarily enable native controls for testing
                    'disablekb': 1, // We handle keyboard
                    'rel': 0,
                    'autoplay': autoplay,
                    'origin': window.location.origin
                },
                events: {
                    'onReady': onPlayerReady,
                    'onStateChange': onPlayerStateChange,
                    'onError': (e) => logToAgent('YT_ERROR', `YouTube Error Code: ${e.data}`)
                }
            });
            } catch (err) {
                logToAgent('FATAL', `Failed to initialize YT.Player: ${err.message}`);
            }
        }

        function formatTime(seconds) {
            if (isNaN(seconds)) return "0:00";
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
            return `${m}:${s.toString().padStart(2, '0')}`;
        }

        function updateScrubber() {
            if (player && player.getCurrentTime) {
                try {
                    const current = player.getCurrentTime();
                    const duration = player.getDuration();
                    const scrubber = document.getElementById('scrubber');
                    const timeDisplay = document.getElementById('timeDisplay');
                    
                    if (duration > 0) {
                        const percent = (current / duration) * 100;
                        scrubber.value = percent;
                        scrubber.setAttribute('aria-valuenow', Math.round(percent));
                        timeDisplay.textContent = `${formatTime(current)} / ${formatTime(duration)}`;
                    }
                } catch(e) {}
            }
        }

        function onPlayerReady(event) {
            logToAgent('INFO', 'onPlayerReady fired! Player is ready.');
            document.getElementById('videoTitle').focus();
            
            const btnPlayPause = document.getElementById('btnPlayPause');
            const btnRewind = document.getElementById('btnRewind');
            const btnForward = document.getElementById('btnForward');
            const btnFullscreen = document.getElementById('btnFullscreen');
            const speedSelect = document.getElementById('speedSelect');
            const scrubber = document.getElementById('scrubber');

            // Play / Pause
            btnPlayPause.addEventListener('click', () => {
                logToAgent('INFO', `btnPlayPause clicked. Current state: isPlaying=${isPlaying}`);
                try {
                    if (isPlaying) {
                        player.pauseVideo();
                        logToAgent('INFO', 'Called pauseVideo()');
                    } else {
                        player.playVideo();
                        logToAgent('INFO', 'Called playVideo()');
                    }
                } catch (err) {
                    logToAgent('ERROR', `Error in play/pause: ${err.message}`);
                }
            });

            // Rewind / Forward
            btnRewind.addEventListener('click', () => {
                player.seekTo(player.getCurrentTime() - 10, true);
                document.getElementById('timeDisplay').textContent = "Rewound 10 seconds";
            });
            btnForward.addEventListener('click', () => {
                player.seekTo(player.getCurrentTime() + 10, true);
                document.getElementById('timeDisplay').textContent = "Skipped 10 seconds";
            });

            // Speed
            speedSelect.addEventListener('change', (e) => {
                player.setPlaybackRate(parseFloat(e.target.value));
            });

            // Scrubber
            scrubber.addEventListener('input', (e) => {
                const duration = player.getDuration();
                const seekTo = (e.target.value / 100) * duration;
                player.seekTo(seekTo, true);
            });

            // Fullscreen
            btnFullscreen.addEventListener('click', () => {
                const iframe = document.querySelector('.video-wrapper iframe');
                if (iframe.requestFullscreen) {
                    iframe.requestFullscreen();
                } else if (iframe.webkitRequestFullscreen) { /* Safari */
                    iframe.webkitRequestFullscreen();
                } else if (iframe.msRequestFullscreen) { /* IE11 */
                    iframe.msRequestFullscreen();
                }
            });

            // Scrubber sync
            scrubberInterval = setInterval(updateScrubber, 1000);
        }

        function onPlayerStateChange(event) {
            logToAgent('INFO', `onPlayerStateChange fired: state=${event.data}`);
            const btnPlayPause = document.getElementById('btnPlayPause');
            if (event.data == YT.PlayerState.PLAYING) {
                isPlaying = true;
                btnPlayPause.textContent = {{ ui.media_player.btn_pause | tojson | safe }};
                btnPlayPause.setAttribute('aria-label', {{ ui.media_player.btn_pause_aria | tojson | safe }});
            } else {
                isPlaying = false;
                btnPlayPause.textContent = {{ ui.media_player.btn_play | tojson | safe }};
                btnPlayPause.setAttribute('aria-label', {{ ui.media_player.btn_play_aria | tojson | safe }});
            }
        }
        
        // Setup Cross-Iframe Alt+N shortcut
        document.addEventListener('keydown', (e) => {
            if (e.altKey && e.key.toLowerCase() === 'n') {
                document.getElementById('videoTitle').focus();
            }
        });
    