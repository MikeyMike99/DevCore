#!/usr/bin/env python3
"""
Sync Docs to E-Profile
======================
Automated synchronization, DLP path sanitization, link normalization,
and catalog generator bridge between DevCore and the public e_profile portfolio.
"""

import os
import re
import json
import shutil
from pathlib import Path

DEVCORE_ROOT = Path("/mnt/c/Users/michael/Documents/DevCore")
EPROFILE_ROOT = Path("/mnt/c/Users/michael/Documents/e_profile")

DOCS_SRC = DEVCORE_ROOT / "docs"
DOCS_DEST = EPROFILE_ROOT / "content" / "docs"

COLLECTIONS = {
    "devlog": DOCS_SRC / "devlog",
    "textbook": DOCS_SRC / "Siraugga_Textbook",
    "manual": DOCS_SRC / "Siraugga_Master_Manual",
    "manifesto": DOCS_SRC / "The_Manifesto",
    "story": DOCS_SRC / "DEVLOG.md",
    "guides": [
        DOCS_SRC / "USER_MANUAL.md",
        DOCS_SRC / "SECURITY.md",
        DOCS_SRC / "HOT_PATCH_ARCHITECTURE.md",
        DOCS_SRC / "RAUGUS_RESOLVER_MCP_ARCHITECTURE.md"
    ]
}

def sanitize_content(raw_text: str, category: str) -> str:
    """
    Sanitizes local workstation paths, normalizes markdown links for web viewing,
    and strips sensitive development credentials.
    """
    text = raw_text
    
    # 1. Scrub Windows/WSL local paths to web relative links
    text = re.sub(r'file:///mnt/c/Users/michael/Documents/DevCore/docs/devlog/[^/]+/([a-zA-Z0-9_]+)\.md', r'/docs/devlog/\1', text)
    text = re.sub(r'file:///mnt/c/Users/michael/Documents/DevCore/docs/Siraugga_Textbook/([a-zA-Z0-9_]+)\.md', r'/docs/textbook/\1', text)
    text = re.sub(r'file:///mnt/c/Users/michael/Documents/DevCore/docs/Siraugga_Master_Manual/([a-zA-Z0-9_]+)\.md', r'/docs/manual/\1', text)
    text = re.sub(r'file:///mnt/c/Users/michael/Documents/DevCore/docs/The_Manifesto/([a-zA-Z0-9_]+)\.md', r'/docs/manifesto/\1', text)
    text = re.sub(r'file:///mnt/c/Users/michael/Documents/DevCore/docs/DEVLOG\.md', r'/docs/story/DEVLOG', text)
    text = re.sub(r'file:///mnt/c/Users/michael/Documents/DevCore/docs/([a-zA-Z0-9_]+)\.md', r'/docs/guides/\1', text)
    
    # Generic local path scrubbing
    text = re.sub(r'file:///mnt/c/Users/michael/Documents/DevCore/([a-zA-Z0-9_./-]+)', r'/\1', text)
    text = re.sub(r'file:///home/michael/\.gemini/antigravity-cli/brain/[a-zA-Z0-9_-]+/[a-zA-Z0-9_./-]+', r'[SANITY_REDACTED_BRAIN_SESSION]', text)
    text = re.sub(r'/mnt/c/Users/michael/Documents/DevCore/', r'/', text)
    text = re.sub(r'/home/michael/\.gemini/antigravity-cli/brain/', r'[LOCAL_BRAIN_VAULT]/', text)
    
    # 2. Normalize relative markdown links between devlog pillars
    # e.g., (./01_PROBLEMS_ENCOUNTERED/01_43_TOKEN_BURST_PREMATURE_ROLLOVER_AND_MIDTASK_RESET_TRAPS.md)
    def normalize_link(match):
        target = match.group(1)
        if target.endswith('.md'):
            basename = os.path.basename(target)[:-3]
            if "01_" in target:
                return f'(/docs/devlog/{basename})'
            elif "02_" in target:
                return f'(/docs/devlog/{basename})'
            elif "03_" in target:
                return f'(/docs/devlog/{basename})'
            elif "04_" in target:
                return f'(/docs/devlog/{basename})'
            elif "05_" in target:
                return f'(/docs/devlog/{basename})'
            elif "Chapter_" in target or "Module_" in target or "Checkpoint_" in target:
                return f'(/docs/textbook/{basename})'
            return f'(/docs/{category}/{basename})'
        return match.group(0)

    text = re.sub(r'\(\./([^)]+\.md)\)', normalize_link, text)
    text = re.sub(r'\(\.\./([^)]+\.md)\)', normalize_link, text)
    
    return text

def extract_metadata(file_path: Path, relative_slug: str, category: str) -> dict:
    """Extracts title, summary, and word count from a markdown document."""
    title = relative_slug.replace('_', ' ')
    summary = "Siraugga Framework architecture documentation."
    word_count = 0
    
    try:
        content = file_path.read_text(encoding='utf-8', errors='replace')
        words = content.split()
        word_count = len(words)
        
        # Extract title from first # header
        for line in content.splitlines():
            line_s = line.strip()
            if line_s.startswith('# '):
                title = line_s[2:].strip()
                break
                
        # Extract summary from first meaningful paragraph
        in_code = False
        for line in content.splitlines():
            line_s = line.strip()
            if line_s.startswith('```'):
                in_code = not in_code
                continue
            if in_code or not line_s or line_s.startswith('#') or line_s.startswith('>') or line_s.startswith('|'):
                continue
            if len(line_s) > 30:
                summary = line_s[:220].strip()
                if len(line_s) > 220:
                    summary += "..."
                break
    except Exception:
        pass
        
    return {
        "slug": relative_slug,
        "category": category,
        "title": title,
        "summary": summary,
        "word_count": word_count,
        "rel_path": str(file_path.relative_to(DOCS_DEST)).replace('\\', '/')
    }

def sync():
    """Main synchronization pipeline."""
    print("=" * 60)
    print("   SIRAUGGA FRAMEWORK DOCS SYNC -> E-PROFILE")
    print("=" * 60)
    
    if not EPROFILE_ROOT.exists():
        print(f"[ERROR] E-Profile directory not found: {EPROFILE_ROOT}")
        return False
        
    DOCS_DEST.mkdir(parents=True, exist_ok=True)
    
    catalog = []
    synced_count = 0

    # 1. Sync Devlog Pillars
    print("[*] Synchronizing 5-Pillar Devlog Suite...")
    dest_devlog = DOCS_DEST / "devlog"
    dest_devlog.mkdir(parents=True, exist_ok=True)
    
    devlog_src = COLLECTIONS["devlog"]
    if devlog_src.exists():
        for root, _, files in os.walk(devlog_src):
            for fn in files:
                if fn.endswith('.md'):
                    src_f = Path(root) / fn
                    slug = fn[:-3]
                    content = src_f.read_text(encoding='utf-8', errors='replace')
                    sanitized = sanitize_content(content, "devlog")
                    
                    dest_f = dest_devlog / fn
                    dest_f.write_text(sanitized, encoding='utf-8')
                    synced_count += 1
                    
                    meta = extract_metadata(dest_f, slug, "devlog")
                    catalog.append(meta)

    # 2. Sync Textbook
    print("[*] Synchronizing Zero-Trust Cybersecurity Textbook...")
    dest_tb = DOCS_DEST / "textbook"
    dest_tb.mkdir(parents=True, exist_ok=True)
    
    tb_src = COLLECTIONS["textbook"]
    if tb_src.exists():
        for fn in os.listdir(tb_src):
            if fn.endswith('.md'):
                src_f = tb_src / fn
                slug = fn[:-3]
                content = src_f.read_text(encoding='utf-8', errors='replace')
                sanitized = sanitize_content(content, "textbook")
                
                dest_f = dest_tb / fn
                dest_f.write_text(sanitized, encoding='utf-8')
                synced_count += 1
                
                meta = extract_metadata(dest_f, slug, "textbook")
                catalog.append(meta)

    # 3. Sync Master Manual
    print("[*] Synchronizing Siraugga Master Manual...")
    dest_mm = DOCS_DEST / "manual"
    dest_mm.mkdir(parents=True, exist_ok=True)
    
    mm_src = COLLECTIONS["manual"]
    if mm_src.exists():
        for fn in os.listdir(mm_src):
            if fn.endswith('.md'):
                src_f = mm_src / fn
                slug = fn[:-3]
                content = src_f.read_text(encoding='utf-8', errors='replace')
                sanitized = sanitize_content(content, "manual")
                
                dest_f = dest_mm / fn
                dest_f.write_text(sanitized, encoding='utf-8')
                synced_count += 1
                
                meta = extract_metadata(dest_f, slug, "manual")
                catalog.append(meta)

    # 4. Sync Manifesto
    print("[*] Synchronizing The Manifesto...")
    dest_man = DOCS_DEST / "manifesto"
    dest_man.mkdir(parents=True, exist_ok=True)
    
    man_src = COLLECTIONS["manifesto"]
    if man_src.exists():
        for fn in os.listdir(man_src):
            if fn.endswith('.md'):
                src_f = man_src / fn
                slug = fn[:-3]
                content = src_f.read_text(encoding='utf-8', errors='replace')
                sanitized = sanitize_content(content, "manifesto")
                
                dest_f = dest_man / fn
                dest_f.write_text(sanitized, encoding='utf-8')
                synced_count += 1
                
                meta = extract_metadata(dest_f, slug, "manifesto")
                catalog.append(meta)

    # 5. Sync Development Story (DEVLOG.md)
    print("[*] Synchronizing Development Story (DEVLOG.md)...")
    dest_story = DOCS_DEST / "story"
    dest_story.mkdir(parents=True, exist_ok=True)
    
    story_src = COLLECTIONS["story"]
    if story_src.exists():
        content = story_src.read_text(encoding='utf-8', errors='replace')
        sanitized = sanitize_content(content, "story")
        
        dest_f = dest_story / "DEVLOG.md"
        dest_f.write_text(sanitized, encoding='utf-8')
        synced_count += 1
        
        meta = extract_metadata(dest_f, "DEVLOG", "story")
        meta["title"] = "The Antigravity Dev Portal: A Development Story (73 Chapters)"
        catalog.append(meta)

    # 6. Sync General Architecture Guides
    print("[*] Synchronizing General Architecture Guides...")
    dest_guides = DOCS_DEST / "guides"
    dest_guides.mkdir(parents=True, exist_ok=True)
    
    for g_src in COLLECTIONS["guides"]:
        if g_src.exists():
            fn = g_src.name
            slug = fn[:-3]
            content = g_src.read_text(encoding='utf-8', errors='replace')
            sanitized = sanitize_content(content, "guides")
            
            dest_f = dest_guides / fn
            dest_f.write_text(sanitized, encoding='utf-8')
            synced_count += 1
            
            meta = extract_metadata(dest_f, slug, "guides")
            catalog.append(meta)

    # 7. Write docs_catalog.json
    catalog_path = DOCS_DEST / "docs_catalog.json"
    catalog.sort(key=lambda x: (x["category"], x["slug"]))
    with open(catalog_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2)
        
    print(f"[+] Successfully synced and sanitized {synced_count} documents.")
    print(f"[+] Master catalog generated at: {catalog_path}")
    print("=" * 60)
    return True

if __name__ == '__main__':
    sync()
