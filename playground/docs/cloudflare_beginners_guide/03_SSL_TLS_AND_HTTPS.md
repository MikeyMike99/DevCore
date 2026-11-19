[//]: # (DOC_ID: SIRA-ARCH-CF_03 | VERSION: v1.0 | SCOPE: SSL/TLS Encryption and HTTPS)
# Chapter 03: SSL/TLS Encryption and HTTPS

HTTPS encrypts data traveling between your visitor's browser and your server. Without HTTPS, passwords, cookies, and form inputs travel in plain text, and modern browsers display a "Not Secure" warning.

[//]: # (SECTION_ID: SIRA-ARCH-CF_03-SEC-1)
## 1. The Two Halves of a Proxied Connection

Because Cloudflare acts as a reverse proxy, every HTTPS request has two separate encrypted legs:

1. **Leg 1 (Visitor to Cloudflare Edge)**: Protected automatically by Cloudflare's free **Universal SSL Edge Certificate**.
2. **Leg 2 (Cloudflare Edge to Origin Server)**: Protected by the certificate installed on your origin server.

[//]: # (SECTION_ID: SIRA-ARCH-CF_03-SEC-2)
## 2. Choosing Your SSL/TLS Mode

| Mode | Leg 1 Encrypted? | Leg 2 Encrypted? | Origin Cert Checked? | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **Off** | No | No | No | Never use |
| **Flexible** | Yes | No (Plain HTTP) | No | Avoid; causes redirect loops |
| **Full** | Yes | Yes | No | Temporary fallback only |
| **Full (Strict)** | Yes | Yes | Yes | Recommended standard |

[//]: # (SECTION_ID: SIRA-ARCH-CF_03-SEC-3)
## 3. Why Order Matters: Origin Certificate Before Full Strict

If you turn on **Full (Strict)** before installing a certificate on your origin server, Cloudflare will reject the connection and show an **Error 526 (Invalid SSL Certificate)** page. Always install either a trusted Let's Encrypt certificate or a free **Cloudflare Origin Certificate** on your server first, then switch Cloudflare to **Full (Strict)**.

### Avoiding the Flexible Redirect Loop
If Cloudflare is set to **Flexible**, Cloudflare contacts your origin server over plain HTTP. If your origin server is configured to redirect HTTP to HTTPS, it sends a redirect back to Cloudflare, which sends HTTP again, triggering `ERR_TOO_MANY_REDIRECTS`. Switching to **Full (Strict)** resolves the loop immediately.

[//]: # (SECTION_ID: SIRA-ARCH-CF_03-SEC-4)
## 4. Recommended Baseline TLS Settings

```json
{
  "ssl_mode": "strict",
  "always_use_https": true,
  "min_tls_version": "1.2"
}
```

[//]: # (SECTION_ID: SIRA-ARCH-CF_03-SEC-5)
## 5. Cross-References & System Parallels

<details class="crossref-dropdown" style="border: 1px solid #38bdf8; border-radius: 6px; padding: 12px; margin: 20px 0; background: rgba(56, 189, 248, 0.05);">
<summary style="font-weight: bold; cursor: pointer; color: #38bdf8;">🔽 Cross-References & System Parallels (Click to Expand Dropdown)</summary>

| Related Project / Subsystem | Architectural Parallel & Shared Mechanism | Collection / Scope |
| :--- | :--- | :--- |
| **Cybersecurity Fundamentals** | Asymmetric TLS handshakes and certificate validation. | Siraugga Course |
| **Chapter 04 (Caching & Rules)** | Enforcing edge behavior after TLS terminates at Cloudflare. | This Guide |

</details>

[//]: # (SECTION_ID: SIRA-ARCH-CF_03-SEC-6)
## Beginner Coder Q&A

### What is a Cloudflare Origin Certificate?
It is a free certificate you generate inside the Cloudflare dashboard (SSL/TLS -> Origin Server) and install on your web host. It is trusted specifically by Cloudflare's edge for Full (Strict) mode.

### Should I turn on Always Use HTTPS?
Yes. It automatically redirects anyone typing `http://` to `https://` at the edge before the request reaches your server.
