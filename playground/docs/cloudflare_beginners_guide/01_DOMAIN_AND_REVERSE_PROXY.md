[//]: # (DOC_ID: SIRA-ARCH-CF_01 | VERSION: v1.0 | SCOPE: Domain Connection, Nameservers, and Reverse Proxy)
# Chapter 01: Connecting Your Domain and the Reverse Proxy

Putting a website online involves three separate roles: your **registrar**, your **DNS provider**, and your **web host**. Understanding how they hand off work to each other prevents almost every beginner setup mistake.

[//]: # (SECTION_ID: SIRA-ARCH-CF_01-SEC-1)
## 1. Registrar vs DNS vs Web Host

1. **Registrar**: Holds the legal registration of your domain name (`example.com`).
2. **DNS**: Answers the question, "Which IP address belongs to `example.com`?"
3. **Web Host (Origin Server)**: Runs your website and sends HTML, images, and API responses.

When you add your domain to Cloudflare, you do not transfer ownership away from your registrar. You only update your **nameservers** at the registrar so the internet asks Cloudflare for your DNS records.

[//]: # (SECTION_ID: SIRA-ARCH-CF_01-SEC-2)
## 2. Why Order Matters: Nameservers Before Rules

You must update your nameservers at your registrar and wait for Cloudflare to show your domain as **Active** before any SSL, caching, or firewall settings take effect. Until nameservers point to Cloudflare, visitor traffic bypasses Cloudflare completely and goes straight to your old DNS provider.

You can verify active nameservers safely from any terminal:

```bash
dig NS example.com
```

[//]: # (SECTION_ID: SIRA-ARCH-CF_01-SEC-3)
## 3. Orange Cloud vs Grey Cloud

In the Cloudflare DNS dashboard, each record has a cloud status icon:

### Orange Cloud (Proxied)
- Traffic flows through Cloudflare's global edge before reaching your origin server.
- Your origin server's real IP address is hidden from the public.
- Cloudflare provides free HTTPS, caching, DDoS mitigation, and firewall rules.
- Use this for website hostnames like `@` (root domain) and `www`.

### Grey Cloud (DNS Only)
- Cloudflare answers the IP lookup, and the visitor connects directly to your server IP.
- Caching, WAF, and IP hiding are turned off for that record.
- Use this for non-web services like email servers (`MX` records) or direct `SSH` connections.

[//]: # (SECTION_ID: SIRA-ARCH-CF_01-SEC-4)
## 4. Cross-References & System Parallels

<details class="crossref-dropdown" style="border: 1px solid #38bdf8; border-radius: 6px; padding: 12px; margin: 20px 0; background: rgba(56, 189, 248, 0.05);">
<summary style="font-weight: bold; cursor: pointer; color: #38bdf8;">🔽 Cross-References & System Parallels (Click to Expand Dropdown)</summary>

| Related Project / Subsystem | Architectural Parallel & Shared Mechanism | Collection / Scope |
| :--- | :--- | :--- |
| **Chapter 02 (DNS Records)** | Detailed breakdown of the records inside your Cloudflare DNS table. | This Guide |
| **Chapter 04 (Config Rules)** | Why orange-cloud proxying is required for edge rules to execute. | This Guide |
| **DevCore Web Portal** | Reverse proxy and gateway isolation protecting backend services. | DevCore Architecture |

</details>

[//]: # (SECTION_ID: SIRA-ARCH-CF_01-SEC-5)
## Beginner Coder Q&A

### Why does `dig` show Cloudflare IP addresses instead of my server IP?
When the orange cloud is on, `dig` returns Cloudflare's edge IP addresses. That proves your origin server's real IP is successfully hidden.

### How long do nameserver changes take?
Usually between 15 minutes and a few hours, though registrars sometimes quote up to 24 hours.
