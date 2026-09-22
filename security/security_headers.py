from quart import request

async def apply_security_headers(response):
    """
    Applies strict HTTP security headers to all outbound Quart responses.
    Fixes OWASP ZAP Baseline DAST Warnings [10020, 10021, 10038, 10063, 90004].
    """
    # 1. Prevent Clickjacking (X-Frame-Options)
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    # 2. Prevent MIME-sniffing (X-Content-Type-Options)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # 3. Content Security Policy (CSP)
    # Smart CSP: Allows local execution + Tailwind/jsDelivr CDNs.
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: https:;"
    
    # 4. Permissions Policy
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    
    # 6. Remove Server Information (Quart Leakage)
    if 'Server' in response.headers:
        del response.headers['Server']
        
    return response

def init_security_headers(app):
    """Registers the middleware with the main Quart application."""
    app.after_request(apply_security_headers)
