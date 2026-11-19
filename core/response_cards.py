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
    "course": "course",
    "the course": "course",
    "open course": "course",
    "open the course": "course",
    "start course": "course",
    "start the course": "course",
    "show course": "course",
    "show the course": "course",
    "show me the course": "course",
    "give me the course": "course",
    "take the course": "course",
    "do the course": "course",
    "continue the course": "course",
    "resume the course": "course",
    "launch the course": "course",
    "load the course": "course",
    "bicep course": "course",
    "the bicep course": "course",
    "open the bicep course": "course",
    "start the bicep course": "course",
    "i want to do the course": "course",
    "i want to take the course": "course",
    "can i do the course": "course",
    "can i take the course": "course",
    "where is the course": "course",
    "preview": "course",
    "show preview": "course",
    "show me the preview": "course",
    "show course preview": "course",
    "preview course": "course",
    "preview the course": "course",
    "course preview": "course",
    "preview bicep course": "course",
    "preview the bicep course": "course",
    "/course preview": "course",
    "full preview": "course",
    "full course preview": "course",
    "full preview course": "course",
    "full preview of the course": "course",
    "evaluate course": "course",
    "evaluate the course": "course",
    "evaluate course content": "course",
    "preview course content": "course",
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
    "newsletter": "cyberbrief",
    "/newsletter": "cyberbrief",
    "the newsletter": "cyberbrief",
    "cyber brief": "cyberbrief",
    "the cyber brief": "cyberbrief",
    "/cyberbrief": "cyberbrief",
    "cyberbrief": "cyberbrief",
    "subscribe": "cyberbrief",
    "/subscribe": "cyberbrief",
    "subscribe newsletter": "cyberbrief",
    "subscribe to newsletter": "cyberbrief",
    "threat feed": "cyberbrief",
    "intel feed": "cyberbrief",
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


_COURSE_DEFAULT_ID = "alp_phase2_bicep_course"
_course_cache = {"sig": None, "courses": []}


def list_courses() -> list:
    """Courses that exist on disk: [{id, title, words}]. Cached until a course file changes."""
    cdir = os.path.join(_repo_root(), "sandbox", "static", "courses")
    try:
        files = sorted(f for f in os.listdir(cdir) if f.endswith(".json") and not f.startswith("progress_"))
    except Exception:
        files = []
    sig = tuple((f, os.path.getmtime(os.path.join(cdir, f))) for f in files)
    if _course_cache["sig"] == sig:
        return _course_cache["courses"]
    courses = []
    for f in files:
        try:
            with open(os.path.join(cdir, f), "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        cid = str(data.get("course_id") or f[:-5]).strip()
        title = str(data.get("title") or cid).strip()
        words = set(re.findall(r"[a-z0-9]+", (cid + " " + title).lower())) - {"the", "and", "course", "practical", "interactive"}
        courses.append({"id": cid, "title": title, "words": words, "category": str(data.get("category") or "")})
    _course_cache["sig"] = sig
    _course_cache["courses"] = courses
    return courses


# Catalog categories shown in the help menu and the course list, in display order (with an icon each).
_CATEGORY_ORDER = ["Linux & Programming", "Cloud & Infrastructure", "Networking", "Security", "Professional Skills",
                   "Threat briefings", "Other courses"]
_CATEGORY_ICON = {"Linux & Programming": "🐧", "Cloud & Infrastructure": "☁️", "Networking": "🌐", "Security": "🛡️",
                  "Professional Skills": "📝", "Threat briefings": "🚨", "Other courses": "📚"}
# Automatic, nothing to maintain: a course can set its own "category" in its JSON file; otherwise it is placed by keywords
# in its id and title (first rule that matches wins); anything else lands in "Other courses".
_CATEGORY_RULES = [
    ("Threat briefings", ("cyberbrief", "threat defense")),
    ("Networking", ("network", "packet tracer", "cisco", "tcp", "dns", "routing")),
    ("Cloud & Infrastructure", ("azure", "bicep", "cloudflare", "opentofu", "terraform", "iac", "infrastructure", "aws",
                                "mermaid", "diagram", "cloud", "kubernetes", "docker")),
    ("Security", ("security", "cyber", "threat", "pentest", "cve", "forensic")),
    ("Linux & Programming", ("linux", "python", "bash", "shell", "programming", "pcep", "javascript", "git")),
    ("Professional Skills", ("english", "report", "writing", "communication", "interview", "career")),
]


def course_category(course) -> str:
    """Category of a course from list_courses(): its own 'category' if it has one, else chosen by keywords."""
    own = str(course.get("category") or "").strip()
    if own:
        return own[:40]
    text = (str(course.get("id", "")) + " " + str(course.get("title", ""))).lower().replace("_", " ").replace("-", " ")
    for cat, keys in _CATEGORY_RULES:
        if any(re.search(r"\b" + re.escape(k), text) for k in keys):
            return cat
    return "Other courses"


def course_catalog() -> list:
    """[(category, [course, ...])]: the usual categories in a fixed order, then any category a course named itself, then
    'Other courses'. Only categories that have courses; courses sorted by title."""
    groups = {}
    for c in list_courses():
        groups.setdefault(course_category(c), []).append(c)
    usual = [c for c in _CATEGORY_ORDER if c in groups and c != "Other courses"]
    own = sorted(c for c in groups if c not in _CATEGORY_ORDER)
    order = usual + own + (["Other courses"] if "Other courses" in groups else [])
    return [(cat, sorted(groups[cat], key=lambda c: c["title"].lower())) for cat in order]


def _course_button(c: dict) -> dict:
    title = c["title"]
    return _card_btn(title if len(title) <= 60 else title[:57] + "...", "course:" + c["id"], "teal")


def _find_course(course_id: str = "") -> dict:
    courses = list_courses()
    cid = (course_id or "").strip().lower()
    for c in courses:
        if c["id"].lower() == cid:
            return c
    for c in courses:
        if c["id"] == _COURSE_DEFAULT_ID:
            return c
    return courses[0] if courses else {"id": _COURSE_DEFAULT_ID, "title": "Interactive Practical Course", "words": set()}


def _build_course_card(preview: bool = False, course_id: str = "") -> dict:
    """The course application embedded in a response card (exam-style). Only the card is shown, and it takes focus."""
    course = _find_course(course_id)
    cid, ctitle = course["id"], course["title"]
    title = ctitle + (" (Preview — No Saving or Recording)" if preview else "")
    url = "/plugin/course?course=" + quote(cid) + "&title=" + quote(ctitle)
    if preview:
        url += "&preview=1"
    if preview:
        md = (
            "👁️ **Course Preview Ready**\n\n"
            "Everything works interactively in-memory as a learner sees it — nothing is recorded or saved.\n\n"
            '<div data-card-buttons="1"></div>'
        )
        buttons = [
            _card_btn("🎓 Start Real Course (Save & Record)", "course:" + cid, "teal"),
            _card_btn("⬅️ Help Menu", "menu", "indigo"),
        ]
    else:
        md = (
            "🎓 **Interactive Practical Course Ready**\n\n"
            '<div data-card-buttons="1"></div>'
        )
        buttons = [
            _card_btn("⬅️ Help Menu", "menu", "teal"),
        ]
    return {
        "topic": "course",
        "sender_label": "",
        "model_badge": "Built-in",
        "status_label": "Preview" if preview else "Ready",
        "title": title,
        "announce": ("Course preview ready (no progress saved, no recording)" if preview else "Interactive course ready") + ": " + ctitle,
        "replace_existing": True,
        "plain": True,
        "markdown": md,
        "button_groups": [{"title": "Course Actions", "buttons": buttons}],
        "iframes": [
            {
                "heading": "",
                "src": url,
                "title": title,
                "class_name": "w-full min-h-[780px] border-0 rounded-lg shadow-xl",
                "focus": True,
            }
        ],
    }


def _menu_catalog_groups() -> list:
    """The course catalog for the help menu: one button group per category. Threat briefings (many, auto-made) are one
    button that opens the full catalog instead of a long list."""
    groups = []
    for cat, cs in course_catalog():
        icon = _CATEGORY_ICON.get(cat, "📚")
        if cat == "Threat briefings":
            buttons = [_card_btn("Open all " + str(len(cs)) + " threat briefings", "course_help", "indigo")]
        else:
            buttons = [_course_button(c) for c in cs]
        groups.append({"title": icon + " Courses: " + cat, "buttons": buttons})
    return groups


def _build_course_help_card(note: str = "") -> dict:
    courses = list_courses()
    lines = ["📚 **Available Courses**", ""]
    if note:
        lines += [note, ""]
    if not courses:
        lines.append("There are no courses available yet.")
    else:
        lines.append("Pick a course below, or type **/course** followed by its name (spelling does not have to be perfect).")
    lines += ["", '<div data-card-buttons="1"></div>']
    groups = [{"title": _CATEGORY_ICON.get(cat, "📚") + " " + cat + " (" + str(len(cs)) + ")",
               "buttons": [_course_button(c) for c in cs]} for cat, cs in course_catalog()]
    groups.append({"title": "Navigate", "buttons": [_card_btn("⬅️ Help Menu", "menu", "indigo")]})
    return {
        "topic": "course_help",
        "sender_label": "",
        "model_badge": "Built-in",
        "status_label": "Ready",
        "title": "Available Courses",
        "announce": "Available courses. " + (", ".join(c["title"] for c in courses) or "None yet."),
        "replace_existing": True,
        "plain": True,
        "markdown": "\n".join(lines),
        "button_groups": groups,
        "iframes": [],
    }


# ---- loose "give me the course" detection (typos allowed) ----
_COURSE_STOP = {
    "the", "a", "an", "my", "our", "me", "i", "we", "to", "for", "of", "on", "in", "it", "is", "please", "pls", "plz",
    "course", "courses", "preview", "full", "show", "give", "open", "start", "take", "do", "load", "launch", "continue",
    "resume", "want", "need", "get", "see", "view", "play", "render", "begin", "can", "could", "would", "you", "now",
    "okay", "ok", "okey", "yes", "yeah", "and", "just", "then", "evaluate", "content", "no", "not", "response", "reply",
    "your", "dont", "do", "n't", "when", "user", "asks", "ask", "that", "this", "up", "out", "there", "here",
    "run", "lets", "let's", "let", "us", "so", "go", "made", "check", "test", "try", "see", "all", "some", "any",
    "lab", "labs", "lesson", "lessons", "tutorial", "training", "class", "module", "with", "from", "by", "step",
}
_COURSE_ALIASES = {"labs", "lab", "lesson", "lessons", "tutorial", "training", "class", "module"}
_COURSE_VERBS = {"give", "show", "open", "start", "take", "do", "load", "launch", "continue", "resume", "want", "need",
                 "get", "see", "view", "play", "render", "begin", "preview", "evaluate", "access", "where", "bring", "let",
                 "try", "lets", "let's", "run", "check", "test", "go", "pull", "fetch", "display"}
_COURSE_BLOCK = {"fix", "change", "improve", "add", "bug", "ticket", "update", "edit", "implement", "make", "why", "how",
                 "error", "broken", "wrong", "remove", "delete", "rewrite", "refactor", "code", "file", "explain", "tell",
                 "what", "review", "debug", "create", "build", "write", "modify", "redesign", "design",
                 "issue", "problem", "investigate", "audit", "css", "html", "template", "route", "server"}


def _similar(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def _word_similarity(a: str, b: str) -> float:
    """Spelling similarity that also forgives wrong vowels ('lynex' for 'linux'): same consonants counts as a close match."""
    s = _similar(a, b)
    if len(a) >= 4 and len(b) >= 4:
        ka, kb = re.sub(r"[aeiouy]", "", a), re.sub(r"[aeiouy]", "", b)
        if len(ka) >= 3 and ka == kb:
            s = max(s, 0.88)
    return s


def _is_course_word(w: str) -> bool:
    return w in _COURSE_ALIASES or (len(w) >= 4 and _similar("course", w) >= 0.74)


def _is_preview_word(w: str) -> bool:
    return len(w) >= 5 and (_similar("preview", w) >= 0.78 or _similar("evaluate", w) >= 0.8)


def _match_course_name(tokens: list, minimum: float = 0.72):
    """Best course for the words the user typed (typos allowed), or None. Very short words are too vague to match."""
    courses = list_courses()
    spread = {}                                         # how many courses use each word: a rare word says more than a common one
    for c in courses:
        for w in c["words"]:
            spread[w] = spread.get(w, 0) + 1
    best, best_score = None, 0.0
    for c in courses:
        score, top = 0.0, 0.0
        for t in tokens:
            if len(t) < 4:
                continue
            one, weight = 0.0, 1.0
            for w in c["words"]:
                s = _word_similarity(t, w)
                if s > one:
                    one, weight = s, 1.0 / spread.get(w, 1)
            top = max(top, one)
            if one >= minimum:
                score += one * weight       # "linux" (one course) beats "fundamentals" (shared); "networking revision" beats "revision"
        if top >= minimum and score > best_score:
            best, best_score = c, score
    return best


def detect_course_request(prompt: str):
    """Returns a card topic for a course request, or None when the message should go to the agent.
    '/course <name>' (fuzzy) opens that course, or the course list when nothing matches.
    A short natural request like 'okey give me the course' opens the course. Change requests,
    questions about how it works and long messages are left to the agent."""
    text = normalize_prompt(prompt)
    if not text:
        return None
    words = re.findall(r"[a-z0-9']+", text)
    courses = list_courses()
    if text.startswith("/course") or text.startswith("/cours") or (words and words[0].startswith("/") and _is_course_word(words[0][1:])):
        rest = re.findall(r"[a-z0-9']+", text.split(None, 1)[1] if " " in text else "")
        preview = False
        name_tokens = [w for w in rest if w not in _COURSE_STOP and not _is_preview_word(w)]
        if not name_tokens:
            if len(courses) == 1:
                return ("course_preview:" if preview else "course:") + courses[0]["id"]
            return "course_help"
        hit = _match_course_name(name_tokens)
        if hit:
            return ("course_preview:" if preview else "course:") + hit["id"]
        return "course_help:" + " ".join(name_tokens)
    if len(words) > 20 or not words:
        return None
    idx = [i for i, w in enumerate(words) if _is_course_word(w) and not (i > 0 and words[i - 1] == "of")]
    if any(w in _COURSE_BLOCK for w in words):
        return None
    if not idx:
        # "open linux essentials" / "give me the networking revision": a short request that starts with a verb and
        # clearly names one course, without saying "course".
        if len(words) <= 6 and words[0] in _COURSE_VERBS | {"run"}:
            named = [w for w in words if w not in _COURSE_STOP and not _is_preview_word(w)]
            hit = _match_course_name(named, 0.85) if named else None
            if hit:
                return "course:" + hit["id"]
        return None
    if len(words) > 4 and not any(w in _COURSE_VERBS or _is_preview_word(w) for w in words):
        return None
    preview = False
    name_tokens = [w for w in words if w not in _COURSE_STOP and not _is_preview_word(w) and not _is_course_word(w)]
    hit = _match_course_name(name_tokens, 0.8) if name_tokens else None
    if hit:
        return ("course_preview:" if preview else "course:") + hit["id"]
    if len(courses) <= 1:
        return ("course_preview:" if preview else "course:") + (courses[0]["id"] if courses else _COURSE_DEFAULT_ID)
    return "course_help"


def build_card(topic: str, security_mgr=None, headers=None, remote_addr: str = "", client_id: str = "", touch: bool = False) -> dict:
    headers = headers or {}
    t = (topic or "menu").strip().lower()
    if t in ("usage", "tiers"):
        usage_data = _collect_usage_snapshot(security_mgr, headers, remote_addr, client_id)
        return _build_usage_card(usage_data) if t == "usage" else _build_tiers_card(usage_data)

    if t in ("cyberbrief", "newsletter", "subscribe"):
        return _build_cyberbrief_card()

    if t in ("course", "course_preview"):
        return _build_course_card(preview=False)
    if t.startswith("course:") or t.startswith("course_preview:"):
        kind, _, cid = t.partition(":")
        return _build_course_card(preview=False, course_id=cid)
    if t == "course_help" or t.startswith("course_help:"):
        said = t.partition(":")[2].strip()
        return _build_course_help_card(("I could not find a course called **" + html.escape(said) + "**. These are the courses you can open:") if said else "")

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
            *_menu_catalog_groups(),
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
            try:
                topic = detect_course_request(prompt) or ""
            except Exception:
                topic = ""
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


def _build_cyberbrief_card() -> dict:
    manifest_path = os.path.join(_repo_root(), "services", "cyberbrief", "cache", "current_digest_manifest.json")
    manifest = {}
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = {}

    items = manifest.get("items") or []
    dispatched = manifest.get("dispatched_at") or "Real-Time Feed"
    latest = items[0] if items else None

    highlight_md = ""
    if latest:
        ltitle = str(latest.get("title") or "Emerging Threat Advisory").strip()
        lscore = latest.get("score", 75)
        llevel = str(latest.get("threat_level") or "HIGH").upper()
        lsummary = str(latest.get("summary") or "").strip()
        if len(lsummary) > 220:
            lsummary = lsummary[:217].rsplit(" ", 1)[0] + "..."
        highlight_md = (
            f"> **⚡ Latest Threat Advisory**: **{ltitle}**  \n"
            f"> **Severity**: `{llevel}` · **Threat Score**: `{lscore}/100`  \n"
            f"> *{lsummary}*\n\n"
        )
    else:
        highlight_md = (
            "> **⚡ Active Threat Wire**: Real-time intelligence feed monitoring zero-days, CISA KEV alerts, and adversary campaigns.\n\n"
        )

    form_html = (
        '<div class="cyberbrief-card-widget my-3 p-4 rounded-xl bg-slate-950/80 border border-cyan-500/40 shadow-lg">'
        '<div class="flex items-center justify-between gap-2 mb-2">'
        '<div class="flex items-center gap-2">'
        '<span class="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>'
        '<span class="text-xs font-mono font-bold uppercase tracking-wider text-cyan-300">Subscribe to Intelligence Dispatches</span>'
        '</div>'
        '<span class="text-[11px] font-mono text-emerald-400 bg-emerald-950/50 border border-emerald-500/30 px-2 py-0.5 rounded">Free • No Spam</span>'
        '</div>'
        '<p class="text-xs text-slate-300 mb-3">'
        'Get tailored briefings on zero-days, CVEs, and adversary campaigns. Every dispatch includes direct links to the Threat Dossier and Accessible Audio Suite.'
        '</p>'
        '<form class="cyberbrief-subscribe-form flex flex-col gap-3" onsubmit="event.preventDefault();">'
        '<div>'
        '<label class="block text-xs font-mono text-slate-300 mb-1" for="cb-card-email">WORK / SECURITY EMAIL</label>'
        '<div class="flex gap-2 flex-wrap sm:flex-nowrap">'
        '<input type="email" id="cb-card-email" name="email" required placeholder="name@security-team.org" class="flex-1 min-w-[220px] px-3 py-2 text-sm bg-slate-900 border border-slate-700 rounded-md text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 font-mono">'
        '<button type="submit" class="cyberbrief-sub-btn px-4 py-2 bg-gradient-to-r from-cyan-500 to-teal-400 hover:from-cyan-400 hover:to-teal-300 text-slate-950 font-bold text-xs uppercase tracking-wider rounded-md transition-all shadow-md hover:shadow-cyan-500/20 flex items-center justify-center gap-1.5 whitespace-nowrap cursor-pointer">'
        '<span>⚡ Subscribe Free</span>'
        '</button>'
        '</div>'
        '</div>'
        '<div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-300 pt-1">'
        '<div class="flex items-center gap-2">'
        '<span class="font-mono text-slate-400 text-[11px]">CADENCE:</span>'
        '<label class="inline-flex items-center gap-1 cursor-pointer">'
        '<input type="radio" name="sub_frequency" value="daily" checked class="accent-cyan-400">'
        '<span>Daily Updates</span>'
        '</label>'
        '<label class="inline-flex items-center gap-1 cursor-pointer">'
        '<input type="radio" name="sub_frequency" value="weekly" class="accent-cyan-400">'
        '<span>Weekly Digest</span>'
        '</label>'
        '</div>'
        '<div class="flex items-center gap-2">'
        '<span class="font-mono text-slate-400 text-[11px]">APPETITE:</span>'
        '<label class="inline-flex items-center gap-1 cursor-pointer">'
        '<input type="radio" name="sub_appetite" value="cyber_thriller" checked class="accent-cyan-400">'
        '<span>Cyber Thriller</span>'
        '</label>'
        '<label class="inline-flex items-center gap-1 cursor-pointer">'
        '<input type="radio" name="sub_appetite" value="defense_playbook" class="accent-cyan-400">'
        '<span>Defense Playbook</span>'
        '</label>'
        '<label class="inline-flex items-center gap-1 cursor-pointer">'
        '<input type="radio" name="sub_appetite" value="deep_dive" class="accent-cyan-400">'
        '<span>Deep Dive</span>'
        '</label>'
        '</div>'
        '</div>'
        '<p class="text-[11px] text-slate-400 m-0">'
        'By clicking <strong>Subscribe Free</strong>, you agree to our <a href="/terms" target="_blank" class="text-cyan-400 underline">Terms and Conditions</a>.'
        '</p>'
        '<div class="cyberbrief-sub-status text-xs font-mono hidden" role="status" aria-live="polite"></div>'
        '</form>'
        '</div>'
    )

    md = (
        "### 🛡️ The Cyber Brief — Direct Intelligence to Your Inbox\n\n"
        "Stay ahead of emerging zero-days, critical CVEs, adversary tradecraft, and software supply chain threats. "
        "Curated intelligence briefings, incident breakdowns, and actionable defense playbooks delivered straight to your inbox.\n\n"
        + highlight_md
        + form_html
        + "\n\n<div data-card-buttons=\"1\"></div>"
    )

    return {
        "id": "featured-cyberbrief-card",
        "topic": "cyberbrief",
        "sender_label": "The Cyber Brief",
        "icon": "🛡️",
        "model_badge": "Live Feed",
        "status_label": f"Active Dispatch ({dispatched})",
        "title": "The Cyber Brief — Threat Intelligence & Incident Analysis",
        "announce": "The Cyber Brief newsletter subscription card",
        "replace_existing": True,
        "plain": False,
        "markdown": md,
        "button_groups": [
            {
                "title": "Explore Intel Feed",
                "buttons": [
                    _link_btn("🛡️ Read Live Threat Feed", "/newsletter", "teal"),
                    _link_btn("⚙️ Manage Preferences", "/newsletter/preferences", "indigo"),
                    _link_btn("📜 Terms & Privacy", "/terms", "indigo"),
                ],
            }
        ],
        "iframes": [],
    }


def build_featured_card() -> dict:
    feat_path = os.path.join(_repo_root(), "sandbox", "static", "featured_exam.json")
    if os.path.isfile(feat_path):
        try:
            with open(feat_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("quiz"):
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
        except Exception:
            pass

    return {"ok": True, "card": _build_cyberbrief_card()}
