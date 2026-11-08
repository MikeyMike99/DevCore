from quart import request

async def apply_security_headers(response):
    """Applies strict HTTP security headers to all outbound Quart responses."""
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'

    host_only = ""
    try:
        raw_host = request.headers.get("Host") or getattr(request, "host", "")
        if raw_host:
            host_only = raw_host.split(":")[0].strip()
    except Exception:
        pass

    wizard_origins = [
        "http://localhost:5055",
        "http://127.0.0.1:5055",
        "http://localhost:5050",
        "http://127.0.0.1:5050",
    ]
    if host_only and host_only not in ("localhost", "127.0.0.1"):
        wizard_origins.append(f"http://{host_only}:5055")
        wizard_origins.append(f"https://{host_only}:5055")
        wizard_origins.append(f"http://{host_only}:5050")
        wizard_origins.append(f"https://{host_only}:5050")

    frame_src_str = " ".join(["'self'"] + wizard_origins + [
        "https://www.youtube.com",
        "https://www.youtube-nocookie.com",
    ])

    response.headers['Content-Security-Policy'] = (
        f"default-src 'self'; "
        f"script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://unpkg.com https://www.youtube.com https://s.ytimg.com https://static.cloudflareinsights.com; "
        f"frame-src {frame_src_str}; "
        f"connect-src 'self' ws: wss: https://generativelanguage.googleapis.com; "
        f"style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://fonts.googleapis.com; "
        f"font-src 'self' data: https://fonts.gstatic.com; "
        f"img-src 'self' data: https: https://i.ytimg.com; "
        f"report-uri /api/security/csp-report;"
    )

    perm_origins = [
        "self",
        '"http://localhost:5055"',
        '"http://127.0.0.1:5055"',
        '"http://localhost:5050"',
        '"http://127.0.0.1:5050"',
    ]
    if host_only and host_only not in ("localhost", "127.0.0.1"):
        perm_origins.append(f'"http://{host_only}:5055"')
        perm_origins.append(f'"https://{host_only}:5055"')
        perm_origins.append(f'"http://{host_only}:5050"')
        perm_origins.append(f'"https://{host_only}:5050"')
    perm_origins_str = " ".join(perm_origins)

    response.headers['Permissions-Policy'] = (
        f'geolocation=(), microphone=(), camera=(), '
        f'publickey-credentials-create=({perm_origins_str}), '
        f'publickey-credentials-get=({perm_origins_str})'
    )

    if 'Server' in response.headers:
        del response.headers['Server']

    return response

def init_security_headers(app):
    """Registers the middleware with the main Quart application."""
    app.after_request(apply_security_headers)
