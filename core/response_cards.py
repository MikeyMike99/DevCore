"""Server-side response card builder for help menus, guides, usage overviews, and featured cards."""
import html
import json
import os
import re
import time
from urllib.parse import quote


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def normalize_prompt(text: str) -> str:
    cleaned = re.sub(r"[\s.!?,;:]+$", "", str(text or "").strip().lower())
    return re.sub(r"\s+", " ", cleaned)


CARD_TRIGGERS = {
    "help": "menu",
    "/help": "menu",
    "help exam": "exam",
    "/help exam": "exam",
    "help quiz": "exam",
    "/help quiz": "exam",
    "help test": "exam",
    "exam help": "exam",
    "quiz help": "exam",
    "exam guide": "exam",
    "quiz guide": "exam",
    "help media": "media",
    "/help media": "media",
    "media help": "media",
    "media guide": "media",
    "help course": "course",
    "/help course": "course",
    "course help": "course",
    "course guide": "course",
    "/course": "course",
    "help privacy": "privacy",
    "/help privacy": "privacy",
    "help terms": "privacy",
    "/help terms": "privacy",
    "privacy": "privacy",
    "terms": "privacy",
    "/privacy": "privacy",
    "/terms": "privacy",
    "terms and privacy": "privacy",
    "privacy policy": "privacy",
    "help tickets": "tickets",
    "/help tickets": "tickets",
    "help ticket": "tickets",
    "/help ticket": "tickets",
    "ticket": "tickets",
    "tickets": "tickets",
    "/ticket": "tickets",
    "/tickets": "tickets",
    "report a problem": "tickets",
    "report a bug": "tickets",
    "help tiers": "tiers",
    "/help tiers": "tiers",
    "tiers": "tiers",
    "/tiers": "tiers",
    "tier": "tiers",
    "help tier": "tiers",
    "/help tier": "tiers",
    "usage": "usage",
    "/usage": "usage",
    "help usage": "usage",
    "/help usage": "usage",
    "limits": "usage",
    "/limits": "usage",
}


def get_triggers() -> dict:
    return {"ok": True, "triggers": dict(CARD_TRIGGERS)}


def _card_btn(label: str, topic: str, variant: str = "indigo") -> dict:
    return {"label": label, "action": "card", "topic": topic, "variant": variant}


def _link_btn(label: str, href: str, variant: str = "teal") -> dict:
    return {"label": label, "action": "link", "href": href, "target": "_blank", "variant": variant}


def _panel_btn(label: str, target: str, variant: str = "emerald") -> dict:
    return {"label": label, "action": "panel", "target": target, "variant": variant}


def _modal_btn(label: str, target: str, variant: str = "teal") -> dict:
    return {"label": label, "action": "modal", "target": target, "variant": variant}


def _usage_bar(pct: float) -> str:
    n = max(0, min(100, round(pct)))
    color = "#f43f5e" if n >= 90 else ("#f59e0b" if n >= 70 else "#14b8a6")
    return (
        f'<span role="progressbar" aria-valuenow="{n}" aria-valuemin="0" aria-valuemax="100" '
        f'aria-label="{n} percent used" '
        f'style="display:inline-block;width:110px;height:9px;background:#1e293b;border:1px solid #334155;'
        f'border-radius:999px;vertical-align:middle;overflow:hidden;margin:0 6px">'
        f'<span style="display:block;height:100%;width:{n}%;background:{color}"></span></span> '
        f'<strong>{n}%</strong>'
    )


def _resolve_viewer(security_mgr, headers, remote_addr: str, client_id: str) -> tuple:
    token = (headers.get("Authorization") or "").replace("Bearer ", "").strip()
    user = None
    if security_mgr is not None:
        try:
            user = security_mgr.get_user_from_token(token or None, remote_addr=remote_addr, headers=headers)
        except Exception:
            user = None
    is_admin = bool(user and security_mgr is not None and security_mgr.is_admin_user(user))
    if not user:
        from security import guest_session
        user = {
            "username": guest_session.guest_username(headers),
            "name": "Guest",
            "role": "guest",
            "token_scope": "user",
        }
    u = dict(user)
    from agents import unlock_links
    cid = (client_id or "").strip()[:80]
    u.update(
        _client_id=cid,
        _device_id=cid,
        _slot_key=f"{u.get('username')}::{cid}" if cid else u.get("username"),
        _unlimited=unlock_links.is_unlimited(headers),
    )
    return u, is_admin


def _collect_usage_snapshot(security_mgr, headers, remote_addr: str, client_id: str) -> dict:
    from agents import model_router, tier_limits
    snap = model_router.usage_snapshot(wait=True)
    c = snap.get("claude") or {}
    claude = dict(c, available=bool(c))
    google = [
        {
            "group": g["group"],
            "period": g["period"],
            "remaining_pct": g["remaining_pct"],
            "resets": time.strftime("%a %d %b, %H:%M", time.localtime(g["reset_ts"])),
        }
        for g in snap.get("google", [])
    ]
    out_now = model_router.status()
    models = []
    for name in model_router.configured_models():
        fam = model_router.family(name)
        entry = out_now.get(fam)
        back_at = (time.time() + entry["available_in_s"]) if entry else None
        models.append({
            "name": name,
            "status": "out" if entry else "available",
            "back_at": time.strftime("%a %d %b, %H:%M", time.localtime(back_at)) if back_at else None,
        })
    viewer, is_admin = _resolve_viewer(security_mgr, headers, remote_addr, client_id)
    _ok, used, limit, tier = tier_limits.check_prompt(viewer)
    you = {
        "tier": tier,
        "tier_name": "Super Admin" if tier >= 5 else tier_limits.TIER_NAMES.get(tier, f"Tier {tier}"),
        "used": used,
        "limit": limit,
        "unlimited": tier >= 5 or limit is None,
        "unlocked_by_link": bool(viewer.get("_unlimited")),
    }
    limits = tier_limits.load_limits()
    tiers = [{"tier": t, "name": tier_limits.TIER_NAMES[t], "limit": limits.get(t)} for t in sorted(tier_limits.TIER_NAMES)]
    return {
        "claude": claude,
        "google": google,
        "models": models,
        "you": you,
        "tiers": tiers,
        "exams_unlimited": True,
        "is_admin": is_admin,
    }


def _help_open_tip() -> str:
    return (
        "## Opening Help\n"
        "- Type **help** or **/help** in the chat box at any time and press **Execute** (or **Enter** on a keyboard).\n"
        "- For one guide, add its name: **help exam**, **help media**, **help course**, **help tickets**, **help usage**, **help privacy**.\n\n"
    )


def _shortcuts_block(touch: bool, lines: list) -> str:
    if touch:
        return ""
    return "## Keyboard shortcuts\n" + "\n".join(lines) + "\n\n"


def _build_usage_card(usage_data: dict) -> dict:
    lines = ["# Usage", "", "## Claude subscription"]
    c = usage_data.get("claude") or {}
    if c.get("available"):
        if c.get("session_pct") is not None:
            lines.append(
                f"- **Current session:** {_usage_bar(c['session_pct'])} used · resets {html.escape(str(c.get('session_resets') or ''))}"
            )
        if c.get("week_pct") is not None:
            lines.append(
                f"- **This week:** {_usage_bar(c['week_pct'])} used · resets {html.escape(str(c.get('week_resets') or ''))}"
            )
    else:
        lines.append("- Usage figures are not available right now.")

    lines.extend(["", "## Google subscription (Antigravity)"])
    google = usage_data.get("google") or []
    if google:
        for g in google:
            used_pct = 100 - g["remaining_pct"]
            lines.append(
                f"- **{html.escape(g['group'])} · {html.escape(g['period'])}:** {_usage_bar(used_pct)} "
                f"used ({g['remaining_pct']}% left) · resets {html.escape(g['resets'])}"
            )
    else:
        lines.append("- Usage figures are not available right now.")

    lines.extend(["", "## Models"])
    for m in usage_data.get("models") or []:
        st = (
            f"⛔ out of quota · back {html.escape(m.get('back_at') or 'later')}"
            if m.get("status") == "out"
            else "✅ available"
        )
        lines.append(f"- **{html.escape(m['name'])}:** {st}")

    lines.extend([
        "",
        "Smart mode skips models that are out and uses the next best one automatically.",
        "",
        "## Your prompts today",
    ])
    you = usage_data.get("you") or {}
    if you.get("unlimited"):
        lines.append(f"- **{html.escape(str(you.get('tier_name') or 'User'))}:** unlimited")
    else:
        lim = you.get("limit") or 0
        used = you.get("used") or 0
        pct = (used / lim) * 100 if lim else 0
        lines.append(
            f"- **{html.escape(str(you.get('tier_name') or 'User'))}:** {used} of {lim} used {_usage_bar(pct)} · resets at midnight"
        )
    if usage_data.get("exams_unlimited"):
        lines.append("- Exams and quizzes don't count toward your limit.")

    return {
        "topic": "usage",
        "sender_label": "Siraugga Usage",
        "model_badge": "Built-in",
        "status_label": "Ready",
        "title": "Usage",
        "announce": "Usage",
        "replace_existing": True,
        "markdown": "\n".join(lines),
        "button_groups": [
            {
                "title": "Actions",
                "buttons": [
                    _card_btn("🔄 Refresh usage", "usage"),
                    _card_btn("⬅️ Back to Help Menu", "menu"),
                ],
            }
        ],
        "iframes": [],
    }


def _build_tiers_card(usage_data: dict) -> dict:
    lim = {t["tier"]: t["limit"] for t in (usage_data.get("tiers") or [])}

    def per_day(tier_num: int, fallback: str) -> str:
        if tier_num not in lim:
            return fallback
        val = lim[tier_num]
        return "no daily limit" if val is None else f"{val} a day"

    you = usage_data.get("you") or {}
    if you:
        tail = (
            ", with no daily limit."
            if you.get("unlimited")
            else f", with {you.get('used', 0)} of {you.get('limit', 0)} prompts used today."
        )
        extra = ' A "no limit" link is active in this browser.' if you.get("unlocked_by_link") else ""
        you_line = f"You are **{html.escape(str(you.get('tier_name') or ''))}** (Tier {you.get('tier', 1)}){tail}{extra}"
    else:
        you_line = "Could not check your tier right now."

    md = (
        "# Tiers: What You Can Do\n\n"
        + you_line
        + "\n\nEvery account has a tier. Each tier keeps everything from the tiers below it, and Siraugga checks your tier on the server for every request, so these rules can't be skipped from the browser.\n\n"
        "## Tier 1 · Guest (everyone starts here)\n"
        "**Where you work:** the public part of Siraugga (the sandbox): the chat, the exam tools, the media player and other public tools.\n\n"
        "**You can:**\n"
        f"- **Chat with Siraugga:** {per_day(1, 'a small number of prompts each day')} on Siraugga's shared subscription. They reset at midnight.\n"
        "- **Make and take exams and quizzes as often as you like.** They don't count toward your daily prompts.\n"
        "- **Use your own study material:** upload files to **📁 My Exam Content** in Settings & Sessions (only you can see them; deleted after 30 days), or attach a file to a message.\n"
        "- **Bring your own key** (🔑 in the top bar) to chat without using your daily prompts.\n"
        "- **Send tickets** to report problems or ask for changes. Guests answer a few quick questions first, then an AI check decides whether the ticket goes to the admin team.\n"
        "- **Ask about how something was built.** You get a plain-language summary written for your tier.\n\n"
        "**You can't:** see or change any source code, project files, plans, settings or logs. The AI works for you inside a locked sandbox.\n\n"
        "## Tier 2 · Modder\n"
        "**Where you work:** the same public sandbox as Guests, plus the safe game and project content you are given access to.\n\n"
        "**You can:**\n"
        f"- **Daily prompts:** {per_day(2, 'more than Tier 1')}.\n"
        "- **Read** safe content such as game scripts, settings files, data, dialogue and documentation.\n"
        "- **Send tickets straight to review**, without the extra questions.\n\n"
        "**You can't:** save changes to files (Modder access is read-only), or see the engine code, logs or admin settings.\n\n"
        "## Tier 3 · Developer\n"
        "**Where you work:** your own assigned project workspace, where applications, games and plugins are built.\n\n"
        "**You can:**\n"
        f"- **Daily prompts:** {per_day(3, 'more than Tier 2')}.\n"
        "- **Read and edit** the files in your assigned projects: game scripts, settings files, data, dialogue and documentation.\n"
        "- **Have the AI read** the docs, sandbox and playground areas when it helps you.\n"
        "- **Ask for technical summaries** of implementation plans. The AI removes any passwords or secrets before showing them.\n\n"
        "**You can't:** leave your project workspace, see the core engine, the security system or the logs, or open plans and system files directly.\n\n"
        "## Tier 4 · Plugin Master\n"
        "**Where you work:** the project workspaces, like Developers.\n\n"
        f"- **Daily prompts:** {per_day(4, 'more than Tier 3')}.\n"
        "- Builds and maintains larger projects and plugins. Like Developers, Plugin Masters can't reach the core engine or security system.\n\n"
        "## Tier 5 · Super Admin (Siraugga admin team)\n"
        "- **No daily limit**, and full access to the whole system: the core engine, the AI agents, the security system and the logs.\n"
        "- Admin tools: telemetry, audits, the ticket queue (approving or declining tickets) and setting the daily limits on this page.\n\n"
        "## Blocked for Tiers 1 to 4\n"
        "- Secret settings, passwords and keys, version-control internals and hidden system folders are blocked, and so are the AI agents working for you.\n"
        "- Tricks to reach files outside your area (such as shortcuts or \"../\" paths) are detected and refused.\n\n"
        "## Getting a higher tier\n"
        "- Tiers are given by the Siraugga admin team. Send a ticket (choose **Other**) saying what you need, or email **devcore.fammaly@gmail.com**."
    )
    return {
        "topic": "tiers",
        "sender_label": "Siraugga Help",
        "model_badge": "Built-in",
        "status_label": "Ready",
        "title": "Tiers: what you can do",
        "announce": "Tiers: what you can do",
        "replace_existing": True,
        "markdown": md,
        "button_groups": [
            {
                "title": "Actions",
                "buttons": [
                    _panel_btn("🎫 Send a ticket", "ticket"),
                    _card_btn("📊 My usage today", "usage"),
                    _modal_btn("🔑 Bring your own key", "byos"),
                    _card_btn("🔒 Terms & Privacy", "privacy"),
                    _card_btn("⬅️ Back to Help Menu", "menu"),
                ],
            }
        ],
        "iframes": [],
    }


def _build_course_card() -> dict:
    guide_path = os.path.join(_repo_root(), "sandbox", "static", "help", "course_guide.md")
    md = ""
    if os.path.isfile(guide_path):
        try:
            with open(guide_path, "r", encoding="utf-8") as f:
                md = f.read().strip()
        except Exception:
            md = ""
    if not md:
        md = "# Practical Course Guide\n\nOpen the interactive practical course to follow the step-by-step WSL lab."
    return {
        "topic": "course",
        "sender_label": "Siraugga Help",
        "model_badge": "Built-in",
        "status_label": "Ready",
        "title": "Practical Course Guide",
        "announce": "Practical Course Guide",
        "replace_existing": True,
        "markdown": md,
        "button_groups": [
            {
                "title": "Navigate",
                "buttons": [
                    _link_btn("🎓 Open the course (new tab)", "/course"),
                    _card_btn("⬅️ Back to Help Menu", "menu"),
                ],
            }
        ],
        "iframes": [],
    }


def build_card(topic: str, security_mgr=None, headers=None, remote_addr: str = "", client_id: str = "", touch: bool = False) -> dict:
    headers = headers or {}
    t = (topic or "menu").strip().lower()
    if t in ("usage", "tiers"):
        usage_data = _collect_usage_snapshot(security_mgr, headers, remote_addr, client_id)
        return _build_usage_card(usage_data) if t == "usage" else _build_tiers_card(usage_data)

    if t == "course":
        return _build_course_card()

    viewer, is_admin = _resolve_viewer(security_mgr, headers, remote_addr, client_id)

    if t == "exam":
        content_how = (
            "Put source files (notes, PDFs, docs) into the `plugins/exam_application/content/` folder and ask for an exam from them. They are read through the local privacy broker."
            if is_admin
            else 'Upload study material to your own folder: open **Settings & Sessions**, then **📁 My Exam Content** (PDF, Word, text, Markdown or CSV, up to 5 MB). Or attach one file to a message with the **📎 Attach** button. Then ask, for example: "Make a 5-question exam from my content folder." Only you can see your folder.'
        )
        shortcuts = _shortcuts_block(
            touch,
            [
                "- **Alt+N**: submit answer / next question",
                "- **Alt+T**: announce time remaining",
                "- **Alt+H**: open this Help menu",
                "- **H**: jump between headings (exam title, question, answer options)",
            ],
        )
        md = (
            "# Siraugga Exam Generator Guide\n\n"
            "## How to provide content\n"
            "- **Ask for a topic.** For example: \"Make me a 5-question quiz on the water cycle.\"\n"
            f"- **Use your own material.** {content_how}\n\n"
            "## Supported question types\n"
            "- **Multiple choice** (true/false is multiple choice with two options)\n"
            "- **Select all that apply**\n"
            "- **Fill in the blank**\n"
            "- **Dropdown**\n"
            "- **Matching**\n"
            "- **Terminal command**\n\n"
            "## Features\n"
            "- **Timers** for the whole exam\n"
            "- **Anti-cheat mode** (flags leaving the exam tab)\n"
            "- **Weighted scoring** and **partial credit**\n"
            "- **Answer explanations**\n"
            "- **Embedded media** (image, audio or video, with alt text)\n\n"
            "## Not available\n"
            "- Retake or resume a past exam (ask for a new one instead)\n"
            "- Changing colours or text size during a test\n\n"
            + _help_open_tip()
            + shortcuts
            + "## Example prompts\n"
            "- \"Generate a quick 3-question multiple-choice quiz on JavaScript arrays.\"\n"
            "- \"Make a 5-question exam from my content folder using dropdowns and fill-in-the-blanks.\"\n"
            "- \"Create a 10-minute weighted exam on Linux commands with 2 terminal-command questions and 2 matching questions.\"\n\n"
            "## Build one now"
        )
        return {
            "topic": "exam",
            "sender_label": "Siraugga Help",
            "model_badge": "Built-in",
            "status_label": "Ready",
            "title": "Siraugga Exam Generator Guide",
            "announce": "Siraugga Exam Generator Guide",
            "replace_existing": True,
            "markdown": md,
            "button_groups": [
                {
                    "title": "Navigate",
                    "buttons": [_card_btn("⬅️ Back to Help Menu", "menu")],
                }
            ],
            "iframes": [
                {
                    "heading": "",
                    "src": "/plugin/exam_builder",
                    "title": "Exam Generator Builder",
                    "class_name": "w-full min-h-[600px] border-0 rounded-lg shadow-xl",
                }
            ],
        }

    if t == "privacy":
        md = (
            "# Terms & Privacy\n\n"
            "You accepted these when you first opened Siraugga. In short:\n\n"
            "## Cookies\n"
            "- We only use cookies the site needs to work and stay secure: your guest session, your acceptance of these terms, ticket questions, and \"no limit\" links if you used one.\n"
            "- No advertising or tracking cookies. You can delete them any time in your browser settings.\n\n"
            "## Your IP address\n"
            "- Siraugga does **not** use your IP address to identify you and does **not** store it.\n"
            "- To stop abuse of the free limit, guest prompts are also counted per network, using a scrambled code that changes every day and is kept in memory only.\n"
            "- Our hosting and security provider, Cloudflare, sees IP addresses when you connect.\n\n"
            "## What you send us\n"
            "- **Chat messages and files** go to AI providers (such as Claude and Gemini) or our own model to answer you. AI answers can be wrong.\n"
            "- **Tickets** (with your email address) are checked by an AI, sent to the admin team and, if approved, may be made live by an AI agent. Your email is only used for updates about your ticket.\n\n"
            "## Bring your own key (BYOS)\n"
            "- If you add your own Google AI key, **you are responsible for its usage and charges**. Use a separate key with a spending cap.\n"
            "- **In My Browser Only** (recommended) keeps the key on this device. **7-Day Vault** stores it encrypted on our server for up to 7 days. **Ephemeral RAM Only** keeps it in server memory for this session.\n"
            "- The agent runs on our server, so the operator can see your prompts and the agent's work. Remove your key any time with **Revoke & Scrub**.\n"
            "- You accept the full Bring Your Own Key terms in the key window before your key is used.\n\n"
            "## Fair use\n"
            "- Please don't try to break into, overload or misuse the site, or hide instructions for Siraugga's AI agents. Tickets that could put the site or others at risk are refused.\n\n"
            "## Your rights\n"
            "- To see, correct or delete your information, email **devcore.fammaly@gmail.com**."
        )
        return {
            "topic": "privacy",
            "sender_label": "Siraugga Help",
            "model_badge": "Built-in",
            "status_label": "Ready",
            "title": "Terms and Privacy",
            "announce": "Terms and Privacy",
            "replace_existing": True,
            "markdown": md,
            "button_groups": [
                {
                    "title": "Read more",
                    "buttons": [
                        _link_btn("📄 Full Terms & Privacy (new tab)", "/terms"),
                        _link_btn("🔑 Bring Your Own Key terms (new tab)", "/terms#byos"),
                        _modal_btn("🛡️ Open the key window", "byos"),
                        _card_btn("⬅️ Back to Help Menu", "menu"),
                    ],
                }
            ],
            "iframes": [],
        }

    if t == "tickets":
        md = (
            "# Tickets: Report a Problem or Request a Change\n\n"
            "## How it works\n"
            "- **Send a ticket** describing the problem or the change you want.\n"
            "- Our **review agent** checks it first, then the **Siraugga admin team** approves or declines it.\n"
            "- You can follow every step under **Settings & Sessions → 🎫 My Tickets**, and by email.\n\n"
            "## Tips for a good ticket\n"
            "- Use a short, clear title, e.g. \"Add a dark/light theme switch\".\n"
            "- Say what you expected and what happened instead.\n"
            "- Don't include passwords or other private details."
        )
        return {
            "topic": "tickets",
            "sender_label": "Siraugga Help",
            "model_badge": "Built-in",
            "status_label": "Ready",
            "title": "Tickets",
            "announce": "Tickets",
            "replace_existing": True,
            "markdown": md,
            "button_groups": [
                {
                    "title": "Actions",
                    "buttons": [
                        _panel_btn("🎫 Send a ticket", "ticket"),
                        _card_btn("⬅️ Back to Help Menu", "menu"),
                    ],
                }
            ],
            "iframes": [],
        }

    if t == "media":
        md = (
            "# Siraugga Media Player Guide\n\n"
            "- Type **/media** to open the player, or **/media play [song]** to search for a video.\n"
            "- The player remembers where you were, so you can say **\"resume my video\"**.\n"
            "- Ask to **add or remove items** from your playlist.\n"
            "- Some videos can only be played on their own website because of copyright rules; those open in a new tab."
        )
        return {
            "topic": "media",
            "sender_label": "Siraugga Help",
            "model_badge": "Built-in",
            "status_label": "Ready",
            "title": "Siraugga Media Player Guide",
            "announce": "Siraugga Media Player Guide",
            "replace_existing": True,
            "markdown": md,
            "button_groups": [
                {
                    "title": "Navigate",
                    "buttons": [_card_btn("⬅️ Back to Help Menu", "menu")],
                }
            ],
            "iframes": [],
        }

    exam_tip = (
        "put files in the exam content folder."
        if is_admin
        else "upload them under **Settings & Sessions → 📁 My Exam Content**, or use **📎 Attach** next to the chat box."
    )
    tail_tips = (
        "## On a phone or tablet\n- Tap **Execute** to send. The keyboard's Enter key adds a new line."
        if touch
        else (
            "## Keyboard shortcuts\n"
            "- **Alt+H**: this Help menu\n"
            "- **Alt+C**: jump to the chat box\n"
            "- **Alt+E**: jump to the latest exam\n"
            "- **Enter**: send\n"
            "- **Shift+Enter**: new line"
        )
    )
    md = (
        "# Siraugga Help Menu\n\n"
        "Choose a guide, or just type what you need in the chat box.\n\n"
        '<div data-card-buttons="1"></div>\n\n'
        "## Quick tips\n"
        "- **Make an exam:** \"Make a 5-question quiz on photosynthesis.\"\n"
        f"- **Use your own notes:** {exam_tip}\n"
        "- **Bring your own key:** **🔑 Authenticate Subscription** in the top bar.\n"
        "- **See usage:** type **/usage** (or use **📊 Usage & limits** above) to see your prompts left today and which models are available.\n"
        "- **Terms & Privacy:** type **/terms** to see what we collect and why.\n"
        "- **Report a problem:** type **/ticket**, or use **🎫 Send a ticket** above.\n\n"
        + _help_open_tip()
        + tail_tips
    )
    return {
        "topic": "menu",
        "sender_label": "Siraugga Help",
        "model_badge": "Built-in",
        "status_label": "Ready",
        "title": "Siraugga Help Menu",
        "announce": "Siraugga Help Menu",
        "replace_existing": True,
        "markdown": md,
        "button_groups": [
            {
                "title": "Guides",
                "buttons": [
                    _card_btn("📝 Exam Generator Guide", "exam"),
                    _card_btn("🎬 Media Player Guide", "media"),
                    _card_btn("🎓 Practical Course Guide", "course"),
                ],
            },
            {
                "title": "Get support",
                "buttons": [
                    _panel_btn("🎫 Send a ticket", "ticket"),
                    _card_btn("❓ How tickets work", "tickets"),
                ],
            },
            {
                "title": "Your account",
                "buttons": [
                    _card_btn("🏅 Tiers: what you can do", "tiers"),
                    _card_btn("📊 Usage & limits", "usage"),
                    _card_btn("🔒 Terms & Privacy", "privacy"),
                ],
            },
        ],
        "iframes": [],
    }


def resolve_card(body: dict, security_mgr=None, headers=None, remote_addr: str = "") -> tuple:
    body = body if isinstance(body, dict) else {}
    topic = (body.get("topic") or "").strip().lower()
    prompt = body.get("prompt") or ""
    if not topic and prompt:
        topic = CARD_TRIGGERS.get(normalize_prompt(prompt), "")
    if not topic:
        return 200, {"ok": True, "matched": False}
    card = build_card(
        topic,
        security_mgr=security_mgr,
        headers=headers,
        remote_addr=remote_addr,
        client_id=str(body.get("client_id") or ""),
        touch=bool(body.get("touch")),
    )
    return 200, {"ok": True, "matched": True, "card": card}


def build_featured_card() -> dict:
    feat_path = os.path.join(_repo_root(), "sandbox", "static", "featured_exam.json")
    if not os.path.isfile(feat_path):
        return {"ok": False}
    try:
        with open(feat_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"ok": False}
    if not isinstance(data, dict) or not data.get("quiz"):
        return {"ok": False}
    title = str(data.get("title") or "Exam").strip() or "Exam"
    q_count = data.get("questions")
    url = f"/plugin/exam?quiz={quote(str(data['quiz']))}&title={quote(title)}"
    embed_url = f"{url}&autofocus=0"
    q_suffix = f" ({q_count} questions)." if q_count else "."
    md = (
        f"📝 A new exam has just been generated: **{title}**{q_suffix}\n\n"
        f"You can start it right here, or [open it in a new tab]({url})."
    )
    return {
        "ok": True,
        "card": {
            "id": "featured-exam-card",
            "topic": "featured_exam",
            "sender_label": "New exam ready",
            "status_label": "Just generated",
            "title": title,
            "markdown": md,
            "iframes": [
                {
                    "src": embed_url,
                    "title": title,
                    "class_name": "w-full min-h-[600px] border-0 rounded-lg",
                    "dataset": {"featured": "1"},
                }
            ],
        },
    }
