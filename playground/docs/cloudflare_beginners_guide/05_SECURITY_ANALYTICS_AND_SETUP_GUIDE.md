[//]: # (DOC_ID: SIRA-ARCH-CF_05 | VERSION: v1.0 | SCOPE: Security Layers, Analytics, and Step-by-Step Setup)
# Chapter 05: Protecting Your Domain, Reading Analytics, and Setup Guide

Once your domain is proxied and encrypted, Cloudflare adds multiple layers of security in front of your origin server and gives you clear visibility in the dashboard.

[//]: # (SECTION_ID: SIRA-ARCH-CF_05-SEC-1)

> [!NOTE] Starting From Scratch
> Open a blank editor window (such as Notepad, TextEdit, or nano) or create a fresh blank file in your terminal before building this component.

## 1. Layered Edge Protection

1. **Automatic DDoS Protection**: Absorbs massive floods of fake traffic at the edge so your origin server stays online.
2. **Web Application Firewall (WAF)**: Inspects incoming HTTP requests and lets you block, challenge, or log suspicious patterns.
3. **Bot Fight Mode**: Challenges automated scrapers and bad bots before they waste your server resources.
4. **Rate Limiting**: Stops any single IP address from sending too many requests in a short window (such as brute-forcing `/login` or `/admin`).

[//]: # (SECTION_ID: SIRA-ARCH-CF_05-SEC-2)
## 2. Why Order Matters: Log or Challenge Before Block

When you create a new custom WAF rule, never jump straight to `block`. A typo in an expression can lock you out of your own site.

1. Start with `managed_challenge` or `log`.
2. Open **Security -> Events** in your dashboard to inspect which requests matched.
3. Confirm only unwanted traffic is caught before switching to `block`.

```json
{
  "description": "Protect admin login",
  "expression": "(http.request.uri.path contains \"/admin\")",
  "action": "managed_challenge"
}
```

[//]: # (SECTION_ID: SIRA-ARCH-CF_05-SEC-3)
## 3. Reading Web Analytics and Security Events

- **Web Analytics**: Shows real human page views, top countries, and page load times. With test `User-Agent` strings excluded via `disable_rum`, these metrics stay accurate.
- **Security Events**: Logs every request that triggered a WAF rule, Rate Limit, or Bot challenge, showing the client IP, country, and rule that fired.

[//]: # (SECTION_ID: SIRA-ARCH-CF_05-SEC-4)
## 4. From-Scratch Domain Onboarding Guide

Follow these steps in order when connecting a new domain:

1. **Create Account and Add Site**: Log in to Cloudflare, click **Add a Site**, enter your bare domain (`example.com`), and choose the Free plan.
2. **Review Imported DNS Records**: Confirm your `A` record (`@`) and `CNAME` (`www`) are orange-clouded, and your `MX`/`TXT` records are grey-clouded.
3. **Update Nameservers**: Copy the two Cloudflare nameservers into your registrar's custom nameserver settings.
4. **Verify Propagation**: Run `dig NS example.com` until Cloudflare's nameservers appear.
5. **Configure SSL/TLS**: Install an Origin Certificate on your server, set SSL/TLS mode to **Full (Strict)**, and enable **Always Use HTTPS**.
6. **Verify and Monitor**: Open your site with `https://`, check **Security Events**, and confirm **Web Analytics** records real traffic.

[//]: # (SECTION_ID: SIRA-ARCH-CF_05-SEC-5)
## 5. Cross-References & System Parallels

<details class="crossref-dropdown" style="border: 1px solid #38bdf8; border-radius: 6px; padding: 12px; margin: 20px 0; background: rgba(56, 189, 248, 0.05);">
<summary style="font-weight: bold; cursor: pointer; color: #38bdf8;">🔽 Cross-References & System Parallels (Click to Expand Dropdown)</summary>

| Related Project / Subsystem | Architectural Parallel & Shared Mechanism | Collection / Scope |
| :--- | :--- | :--- |
| **Cybersecurity Fundamentals** | Defense in depth, DDoS mitigation, and WAF rule design. | Siraugga Course |
| **Chapter 04 (Caching & Rules)** | Suppressing RUM beacons for automated tests to keep analytics clean. | This Guide |

</details>

[//]: # (SECTION_ID: SIRA-ARCH-CF_05-SEC-6)
## Beginner Coder Q&A

### What should I check first if my site suddenly feels slow?
Check three places in order: **Security Events** (to see if an attack is happening), **Caching** (to check your cache hit ratio), and your **origin server** health.

### Can attackers still find my server if they guess its IP directly?
If they know your old origin IP from before you joined Cloudflare, they could try connecting directly. On your origin server firewall, you can restrict web ports (80 and 443) to accept traffic only from Cloudflare's published IP ranges.

> [!WARNING] Line Ending Advisory (CRLF vs LF)
> If you are authoring this file on Windows for execution within Linux or WSL, ensure your text editor saves with Unix line endings (`LF`). Windows carriage returns (`CRLF`) will cause bash and Python interpreters to fail with unexpected syntax errors.


---

## 10-Second Verification Checklist

To verify that your newly created file is functioning properly:
- [ ] Confirm the file is saved with the exact filename and correct extension in the target directory.
- [ ] Run `python3 <filename> --help` or execute the script in dry-run mode to verify clean startup.
- [ ] Inspect console output to confirm there are no syntax errors or missing module tracebacks.

