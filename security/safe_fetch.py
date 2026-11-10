"""Public-internet-only web fetch for agents below Tier 5.

Lets guest/low-tier agents do research (read web pages, docs, JSON APIs) without
giving them a shell. Because the agent runs on the owner's PC, an unrestricted
fetcher would let any visitor reach the PC's private services (DevCore and
e-profile on 127.0.0.1, the home router, cloud metadata, ...). This module only
talks to globally routable addresses:

  * http/https only, standard web ports only, GET only, no credentials in URLs;
  * the host name is resolved once and EVERY resolved address must be public
    (no loopback, private, link-local, CGNAT, multicast, reserved, metadata);
  * the connection goes to that vetted address (no DNS-rebinding race), with the
    real host name used for TLS (SNI + certificate check) and the Host header;
  * redirects are followed manually (max 5) and each hop is vetted again;
  * size (2 MB) and time (15 s per hop) limits; no cookies are sent or kept.
"""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
from html import unescape
from urllib.parse import urljoin, urlsplit

MAX_BYTES = 2 * 1024 * 1024
MAX_TEXT = 60_000
TIMEOUT = 15
MAX_REDIRECTS = 5
ALLOWED_PORTS = {80, 443, 8080, 8443}
BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".arpa", ".intranet")
USER_AGENT = "Mozilla/5.0 (compatible; SirauggaResearchAgent/1.0; +https://mikeytech.dev)"


class FetchBlocked(Exception):
    """The URL is not allowed (private address, bad scheme, ...)."""


def _vet_address(ip: str) -> None:
    addr = ipaddress.ip_address(ip.split("%")[0])
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    if (not addr.is_global or addr.is_loopback or addr.is_private or addr.is_link_local
            or addr.is_multicast or addr.is_reserved or addr.is_unspecified):
        raise FetchBlocked(f"address {addr} is not on the public internet")


def vet_url(url: str, resolve=socket.getaddrinfo) -> tuple:
    """Return (scheme, host, port, path_with_query, vetted_ip) or raise FetchBlocked."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise FetchBlocked("only http:// and https:// URLs are allowed")
    if parts.username or parts.password:
        raise FetchBlocked("credentials in URLs are not allowed")
    host = (parts.hostname or "").strip(".").lower()
    if not host:
        raise FetchBlocked("URL has no host")
    if host == "localhost" or host.endswith(BLOCKED_HOST_SUFFIXES) or "." not in host and not _is_ip(host):
        raise FetchBlocked(f"host '{host}' is not a public internet name")
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError:
        raise FetchBlocked("invalid port")
    if port not in ALLOWED_PORTS:
        raise FetchBlocked(f"port {port} is not allowed (web ports only)")
    try:
        infos = resolve(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise FetchBlocked(f"could not resolve '{host}'")
    ips = sorted({i[4][0] for i in infos})
    if not ips:
        raise FetchBlocked(f"could not resolve '{host}'")
    for ip in ips:          # every address must be public, not just the first
        _vet_address(ip)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return scheme, host, port, path, ips[0]


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|section|article)>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def fetch(url: str, *, raw: bool = False, resolve=socket.getaddrinfo, opener=None) -> dict:
    """GET a public URL. Returns {status, url, content_type, text, truncated} or raises FetchBlocked.
    `opener(scheme, host, ip, port)` is injectable for tests."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        scheme, host, port, path, ip = vet_url(current, resolve)
        cls = _PinnedHTTPS if scheme == "https" else _PinnedHTTP
        conn = opener(scheme, host, ip, port) if opener else cls(host, ip, port, TIMEOUT)
        try:
            conn.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "*/*",
                                              "Accept-Encoding": "identity", "Connection": "close"})
            resp = conn.getresponse()
            if resp.status in (301, 302, 303, 307, 308) and resp.getheader("Location"):
                current = urljoin(current, resp.getheader("Location"))
                continue
            body = resp.read(MAX_BYTES + 1)
            ctype = resp.getheader("Content-Type", "") or ""
            status = resp.status
        finally:
            conn.close()
        truncated = len(body) > MAX_BYTES
        body = body[:MAX_BYTES]
        m = re.search(r"charset=([\w-]+)", ctype)
        text = body.decode(m.group(1) if m else "utf-8", errors="replace")
        if "html" in ctype.lower() and not raw:
            text = html_to_text(text)
        if len(text) > MAX_TEXT:
            text, truncated = text[:MAX_TEXT], True
        return {"status": status, "url": current, "content_type": ctype, "text": text, "truncated": truncated}
    raise FetchBlocked(f"too many redirects (more than {MAX_REDIRECTS})")
