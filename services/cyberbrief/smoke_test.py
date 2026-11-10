"""Quick check that the CyberBrief backend renders. Run from the DevCore root:
    python -m services.cyberbrief.smoke_test
Uses MAIL_BACKEND as configured but only issues GET requests (sends no mail)."""
from .app import create_app, owns

PATHS = [
    "/newsletter",
    "/newsletter/preferences",
    "/newsletter/unsubscribe",
    "/newsletter/story/cve-2026-123158-openssh",
    "/api/newsletter/status",
    "/admin/notify",
]

if __name__ == "__main__":
    app = create_app()
    client = app.test_client()
    for p in PATHS:
        r = client.get(p)
        print(f"{p:45} {r.status_code} {len(r.get_data()):7} {r.headers.get('Location', '')}")
    print("owns /terms:", owns("/terms"), "| owns /login:", owns("/login"), "| owns /newsletter/x:", owns("/newsletter/x"))
