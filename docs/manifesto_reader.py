import pygame
import sys
import time
import tkinter as tk
from tkinter import simpledialog
from screenreader_speak import screenreader_speak
import textwrap

# --- Configuration ---
FILE_PATH = "DEVELOPERS_MANIFESTO.md"
CHUNK_SIZE = 100  # Load 100 lines at a time to prevent memory/lag issues

def load_chunk(filepath, start_line, chunk_size):
    """Loads a specific chunk of lines from the massive file."""
    lines = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                if i >= start_line and i < start_line + chunk_size:
                    clean_line = line.strip()
                    if clean_line:
                        lines.append((i, clean_line))
                if i >= start_line + chunk_size:
                    break
    except Exception as e:
        return [(0, f"Error loading file: {e}")]
    return lines

def search_file(filepath, query):
    """Searches the entire file for the query and returns the absolute line index."""
    query = query.lower()
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                if query in line.lower():
                    return i, line.strip()
    except Exception as e:
        print(e)
    return -1, None

def estimate_reading_time(text, wpm):
    """Estimates how long a screen reader takes to read a line, tailored to fast screen reader speeds."""
    words = max(1, len(text.split())) # At least 1 word
    
    # Calculate exact seconds based on the current Words Per Minute
    seconds = (words / wpm) * 60.0
    
    # Tiny buffer for punctuation pauses, but no massive arbitrary padding
    return seconds + 0.15

def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Manifesto Screen Reader Interface")
    font = pygame.font.Font(None, 32)
    clock = pygame.time.Clock()

    tk_root = tk.Tk()
    tk_root.withdraw()

    current_chunk_start = 0
    lines = load_chunk(FILE_PATH, current_chunk_start, CHUNK_SIZE)
    current_index = 0
    
    auto_read = False
    next_read_time = 0
    
    # Default to a much faster reading speed typical for screen reader users
    current_wpm = 350 

    screenreader_speak("Reader loaded. Press Left or Right arrow to adjust Auto-Read speed.")

    running = True
    while running:
        current_time = time.time()
        
        # Handle Auto-Read
        if auto_read and current_time >= next_read_time:
            current_index += 1
            if current_index >= len(lines):
                current_chunk_start += CHUNK_SIZE
                lines = load_chunk(FILE_PATH, current_chunk_start, CHUNK_SIZE)
                current_index = 0
                if not lines:
                    screenreader_speak("End of document reached.", interrupt=True)
                    auto_read = False
                    continue
            
            line_num, text = lines[current_index]
            screenreader_speak(text, interrupt=False)
            next_read_time = current_time + estimate_reading_time(text, current_wpm)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                
            elif event.type == pygame.KEYDOWN:
                keys = pygame.key.get_pressed()
                caps_held = keys[pygame.K_CAPSLOCK]
                rshift_held = keys[pygame.K_RSHIFT]
                lctrl_held = keys[pygame.K_LCTRL]
                rctrl_held = keys[pygame.K_RCTRL]
                ctrl_held = lctrl_held or rctrl_held
                
                # STOP Auto-read on any key press (except the activation modifiers)
                if event.key not in [pygame.K_DOWN, pygame.K_CAPSLOCK, pygame.K_RSHIFT, pygame.K_LCTRL, pygame.K_RCTRL, pygame.K_RIGHT, pygame.K_LEFT]:
                    if auto_read:
                        auto_read = False
                        screenreader_speak("Stopped.", interrupt=True)
                
                # DYNAMIC SPEED ADJUSTMENT
                if event.key == pygame.K_RIGHT:
                    current_wpm += 50
                    screenreader_speak(f"Speed up, {current_wpm} words per minute", interrupt=True)
                    if auto_read:
                        # Recalculate remaining time for current line
                        line_num, text = lines[current_index]
                        next_read_time = time.time() + estimate_reading_time(text, current_wpm)
                        
                elif event.key == pygame.K_LEFT:
                    current_wpm = max(100, current_wpm - 50)
                    screenreader_speak(f"Speed down, {current_wpm} words per minute", interrupt=True)
                    if auto_read:
                        # Recalculate remaining time for current line
                        line_num, text = lines[current_index]
                        next_read_time = time.time() + estimate_reading_time(text, current_wpm)
                
                # CTRL + F (Search)
                elif event.key == pygame.K_f and ctrl_held:
                    auto_read = False
                    screenreader_speak("Search mode.", interrupt=True)
                    query = simpledialog.askstring("Search", "Enter text to search for:", parent=tk_root)
                    
                    if query:
                        found_index, found_text = search_file(FILE_PATH, query)
                        if found_index != -1:
                            current_chunk_start = (found_index // CHUNK_SIZE) * CHUNK_SIZE
                            lines = load_chunk(FILE_PATH, current_chunk_start, CHUNK_SIZE)
                            for i, (line_num, text) in enumerate(lines):
                                if line_num == found_index:
                                    current_index = i
                                    break
                            screenreader_speak(f"Found. {found_text}", interrupt=True)
                        else:
                            screenreader_speak(f"Not found: {query}", interrupt=True)
                    else:
                        screenreader_speak("Cancelled.", interrupt=True)
                        
                # DOWN ARROW
                elif event.key == pygame.K_DOWN:
                    if caps_held or rshift_held:
                        auto_read = True
                        if lines:
                            line_num, text = lines[current_index]
                            screenreader_speak(f"Auto read: {text}", interrupt=True)
                            next_read_time = time.time() + estimate_reading_time(text, current_wpm)
                    else:
                        auto_read = False
                        current_index += 1
                        if current_index >= len(lines):
                            current_chunk_start += CHUNK_SIZE
                            lines = load_chunk(FILE_PATH, current_chunk_start, CHUNK_SIZE)
                            current_index = 0
                        
                        if lines:
                            line_num, text = lines[current_index]
                            screenreader_speak(text, interrupt=True)
                            
                # UP ARROW
                elif event.key == pygame.K_UP:
                    auto_read = False
                    current_index -= 1
                    if current_index < 0:
                        if current_chunk_start > 0:
                            current_chunk_start = max(0, current_chunk_start - CHUNK_SIZE)
                            lines = load_chunk(FILE_PATH, current_chunk_start, CHUNK_SIZE)
                            current_index = len(lines) - 1
                        else:
                            current_index = 0
                            screenreader_speak("Top.")
                    
                    if lines:
                        line_num, text = lines[current_index]
                        screenreader_speak(text, interrupt=True)
                        
                elif event.key == pygame.K_SPACE or event.key == pygame.K_ESCAPE:
                    auto_read = False
                    screenreader_speak("Stopped.", interrupt=True)
                
                elif event.key == pygame.K_c:
                    if lines:
                        line_num, text = lines[current_index]
                        screenreader_speak(text, interrupt=True)

        screen.fill((30, 30, 30))
        title_surf = font.render("Manifesto Reader Tool", True, (200, 200, 200))
        screen.blit(title_surf, (20, 20))
        
        controls = [
            "Controls:",
            "- DOWN/UP: Next/Prev Line",
            "- RIGHT/LEFT: Adjust Auto-Read Speed",
            "- CTRL + F: Search and Jump",
            "- SPACE: Stop Auto-Read",
            "- R-SHIFT + DOWN: Auto-Read"
        ]
        
        for i, ctrl in enumerate(controls):
            ctrl_surf = font.render(ctrl, True, (150, 150, 150))
            screen.blit(ctrl_surf, (20, 60 + (i*30)))
            
        if lines:
            line_num, text = lines[current_index]
            wrapped_text = textwrap.wrap(f"Line {line_num}: {text}", width=60)
            for i, line in enumerate(wrapped_text):
                text_surf = font.render(line, True, (255, 255, 100))
                screen.blit(text_surf, (20, 300 + (i*30)))
                
        status = "STATUS: AUTO-READING" if auto_read else "STATUS: MANUAL"
        status_color = (100, 255, 100) if auto_read else (200, 200, 200)
        status_surf = font.render(status, True, status_color)
        screen.blit(status_surf, (20, 500))
        
        speed_surf = font.render(f"WPM: {current_wpm}", True, (150, 150, 255))
        screen.blit(speed_surf, (600, 500))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
