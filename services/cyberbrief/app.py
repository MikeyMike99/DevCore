"""CyberBrief: the newsletter backend (moved from e-profile), hosted inside DevCore.

It stays a plain Flask app and is mounted into DevCore's Hypercorn/ASGI server by
`mount()`: requests whose path starts with one of NEWSLETTER_PREFIXES go to this
app (run in a worker thread through Hypercorn's WSGI adapter); everything else goes
to the normal DevCore Quart app untouched.

Public traffic arrives from the e-profile Cloudflare Pages site, whose Pages
Function forwards only these same prefixes through the tunnel.
"""
from datetime import timedelta

from flask import Flask

from .config import Config, _env

# Paths owned by CyberBrief. Keep in sync with the e-profile Pages Function allowlist.
NEWSLETTER_PREFIXES = (
    "/newsletter/",      # story, preferences, unsubscribe, download, r/<link> tracking
    "/api/newsletter/",
    "/api/subscribe",
    "/subscribe",
    "/api/hub/",
    "/hub",
    "/admin/notify",
    "/chat/",            # visitor chat (sign-up, confirm, messages) and owner inbox /chat/admin
)
NEWSLETTER_EXACT = ("/newsletter", "/chat")


def owns(path: str) -> bool:
    return path in NEWSLETTER_EXACT or path.startswith(NEWSLETTER_PREFIXES)


def create_app() -> Flask:
    from .newsletter_mod import newsletter_bp
    from .chat_mod import chat_bp
    from .notify_mod import notify_bp

    app = Flask(
        __name__,
        template_folder=str(Config.TEMPLATES_DIR),
        static_folder=str(Config.STATIC_DIR),
        static_url_path="/static",
    )
    app.secret_key = _env("CYBERBRIEF_SECRET_KEY") or _env("SECRET_KEY") or "cyberbrief-dev-only"
    app.config.update(
        SESSION_COOKIE_NAME="cyberbrief_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    app.register_blueprint(newsletter_bp)
    app.register_blueprint(notify_bp)
    app.register_blueprint(chat_bp)

    # base.html (copied from e-profile) expects the same filter and globals that
    # e-profile's server.py provides.
    @app.template_filter("clean_text")
    def clean_text_filter(s):
        return s.replace("_", " ").title() if isinstance(s, str) else s

    @app.context_processor
    def inject_system():
        from flask import session
        return dict(
            config=Config(), theme=Config.THEME, sys_logs=[],
            global_blogs=[], global_blog_logs=[],
            label=session.get("label", "Guest"),
            username=session.get("username", "Guest"),
            permissions=session.get("permissions", []),
            is_admin=session.get("admin", False),
        )
    return app


def mount(asgi_app, max_body_size: int = 2 * 1024 * 1024, start_scheduler: bool = True):
    """Wrap DevCore's ASGI app so CyberBrief paths are served by the Flask app."""
    from hypercorn.middleware import AsyncioWSGIMiddleware

    from . import admin_gate, scheduler

    flask_asgi = AsyncioWSGIMiddleware(create_app(), max_body_size=max_body_size)
    if start_scheduler:
        scheduler.start()
    security_mgr = getattr(asgi_app, "security_mgr", None)

    async def router(scope, receive, send):
        if scope["type"] == "http" and owns(scope.get("path", "")):
            await flask_asgi(admin_gate.strip_and_mark(scope, security_mgr), receive, send)
        else:
            await asgi_app(scope, receive, send)

    return router
