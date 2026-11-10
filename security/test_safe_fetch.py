"""Tests for security/safe_fetch.py (no network: DNS and HTTP are faked).
Run from the DevCore root:  python -m unittest security.test_safe_fetch"""
import socket
import unittest

from security import safe_fetch as sf


def fake_dns(table):
    def resolve(host, port, proto=None):
        if host not in table:
            raise socket.gaierror("nx")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in table[host]]
    return resolve


DNS = fake_dns({
    "example.com": ["93.184.215.14"],
    "evil-rebind.com": ["93.184.215.14", "127.0.0.1"],
    "internal.example.com": ["192.168.1.10"],
    "redir.example.com": ["93.184.215.15"],
    "cgnat.example.com": ["100.64.0.5"],
})


class FakeResp:
    def __init__(self, status, headers, body=b""):
        self.status, self._h, self._b = status, headers, body

    def getheader(self, k, d=None):
        return self._h.get(k, d)

    def read(self, n):
        return self._b[:n]


class FakeConn:
    def __init__(self, routes, key):
        self.routes, self.key = routes, key

    def request(self, method, path, headers=None):
        assert method == "GET"
        self.path = path

    def getresponse(self):
        return self.routes[(self.key, self.path)]

    def close(self):
        pass


class VetTests(unittest.TestCase):
    def blocked(self, url):
        with self.assertRaises(sf.FetchBlocked, msg=url):
            sf.vet_url(url, DNS)

    def test_blocks_local_and_private(self):
        for url in ["http://localhost:5000/", "http://127.0.0.1:5100/admin", "http://[::1]/",
                    "http://192.168.1.1/", "http://10.0.0.5/", "http://169.254.169.254/latest/meta-data",
                    "http://0.0.0.0/", "http://internal.example.com/", "http://cgnat.example.com/",
                    "http://router.local/", "http://printer/", "http://[::ffff:127.0.0.1]/"]:
            self.blocked(url)

    def test_blocks_schemes_ports_credentials(self):
        for url in ["file:///etc/passwd", "ftp://example.com/", "gopher://example.com/",
                    "http://example.com:22/", "http://example.com:5000/", "http://user:pw@example.com/"]:
            self.blocked(url)

    def test_dns_rebinding_any_private_address_blocks(self):
        self.blocked("https://evil-rebind.com/")

    def test_allows_public(self):
        scheme, host, port, path, ip = sf.vet_url("https://example.com/docs?q=1", DNS)
        self.assertEqual((scheme, host, port, path, ip), ("https", "example.com", 443, "/docs?q=1", "93.184.215.14"))


class FetchTests(unittest.TestCase):
    def test_redirect_to_private_is_blocked(self):
        routes = {("redir.example.com", "/go"): FakeResp(302, {"Location": "http://127.0.0.1:5100/admin"})}
        with self.assertRaises(sf.FetchBlocked):
            sf.fetch("https://redir.example.com/go", resolve=DNS,
                     opener=lambda s, h, ip, p: FakeConn(routes, h))

    def test_follows_public_redirect_and_strips_html(self):
        routes = {
            ("redir.example.com", "/go"): FakeResp(301, {"Location": "https://example.com/page"}),
            ("example.com", "/page"): FakeResp(200, {"Content-Type": "text/html; charset=utf-8"},
                                               b"<html><head><title>x</title></head><body><script>bad()</script>"
                                               b"<h1>Hello</h1><p>World &amp; more</p></body></html>"),
        }
        r = sf.fetch("https://redir.example.com/go", resolve=DNS, opener=lambda s, h, ip, p: FakeConn(routes, h))
        self.assertEqual(r["status"], 200)
        self.assertEqual(r["url"], "https://example.com/page")
        self.assertIn("Hello", r["text"])
        self.assertIn("World & more", r["text"])
        self.assertNotIn("bad()", r["text"])

    def test_connects_to_vetted_ip(self):
        seen = {}
        routes = {("example.com", "/"): FakeResp(200, {"Content-Type": "application/json"}, b'{"ok":1}')}

        def opener(s, h, ip, p):
            seen["ip"] = ip
            return FakeConn(routes, h)
        r = sf.fetch("https://example.com/", resolve=DNS, opener=opener)
        self.assertEqual(seen["ip"], "93.184.215.14")
        self.assertEqual(r["text"], '{"ok":1}')

    def test_redirect_loop_limit(self):
        routes = {("example.com", "/a"): FakeResp(302, {"Location": "/a"})}
        with self.assertRaises(sf.FetchBlocked):
            sf.fetch("https://example.com/a", resolve=DNS, opener=lambda s, h, ip, p: FakeConn(routes, h))


if __name__ == "__main__":
    unittest.main()
