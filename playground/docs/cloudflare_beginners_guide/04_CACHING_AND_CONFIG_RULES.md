[//]: # (DOC_ID: SIRA-ARCH-CF_04 | VERSION: v1.0 | SCOPE: Edge Caching and Configuration Rules)
# Chapter 04: Speed, Edge Caching, and Configuration Rules

Cloudflare speeds up your website by storing copies of static files at edge data centers close to your visitors, and lets you customize edge behavior with **Configuration Rules**.

[//]: # (SECTION_ID: SIRA-ARCH-CF_04-SEC-1)
## 1. How Edge Caching Works

By default, Cloudflare caches static file extensions (`.css`, `.js`, `.png`, `.jpg`, `.svg`, `.woff2`) and bypasses dynamic HTML pages so logged-in or personalized content is never mixed up between users.

You can check whether a file came from Cloudflare's cache by looking at the `CF-Cache-Status` HTTP response header:

| Header Value | Meaning |
| :--- | :--- |
| **HIT** | Served directly from Cloudflare's edge cache without contacting your server. |
| **MISS** | Not in cache yet; fetched from your origin server and stored for next time. |
| **DYNAMIC** | Cloudflare does not cache this file type by default and passed it through. |
| **BYPASS** | Caching was skipped due to a header or rule. |

If you update a CSS or image file and visitors still see the old version, use **Purge Cache** in the Cloudflare dashboard.

[//]: # (SECTION_ID: SIRA-ARCH-CF_04-SEC-2)
## 2. Configuration Rules and Excluding Test Traffic

Every Cloudflare rule follows one pattern: **If** a request matches an expression, **then** apply an action.

A practical example is keeping automated browser tests out of your **Web Analytics** dashboard. Cloudflare Web Analytics injects a lightweight Real User Monitoring (**RUM**) beacon (`/cdn-cgi/rum`). If an automated agent visits your site using a dedicated `User-Agent` such as `DevCore-Agent-Tester`, a Configuration Rule can suppress the beacon at the edge:

```json
{
  "description": "Exclude DevCore Agent Tests from Web Analytics",
  "expression": "(http.user_agent contains \"DevCore-Agent-Tester\")",
  "action": "set_config",
  "action_parameters": {
    "disable_rum": true
  }
}
```

[//]: # (SECTION_ID: SIRA-ARCH-CF_04-SEC-3)
## 3. Why Order Matters: Proxy First, Rules Second

Configuration Rules execute inside Cloudflare's edge proxy (`http_config_settings` phase). If your DNS record is grey-clouded or your test script connects directly to your origin IP, the request never passes through Cloudflare's edge and `disable_rum` will not run.

[//]: # (SECTION_ID: SIRA-ARCH-CF_04-SEC-4)
## 4. Cross-References & System Parallels

<details class="crossref-dropdown" style="border: 1px solid #38bdf8; border-radius: 6px; padding: 12px; margin: 20px 0; background: rgba(56, 189, 248, 0.05);">
<summary style="font-weight: bold; cursor: pointer; color: #38bdf8;">🔽 Cross-References & System Parallels (Click to Expand Dropdown)</summary>

| Related Project / Subsystem | Architectural Parallel & Shared Mechanism | Collection / Scope |
| :--- | :--- | :--- |
| **DevCore Agent Testing** | Automated browser tests send `DevCore-Agent-Tester` so Cloudflare suppresses RUM beacons. | DevCore Rules |
| **Chapter 05 (Security & Analytics)** | Viewing clean Web Analytics alongside Security Events. | This Guide |

</details>

[//]: # (SECTION_ID: SIRA-ARCH-CF_04-SEC-5)
## Beginner Coder Q&A

### Does caching break login pages or dynamic APIs?
Not by default, because Cloudflare does not cache HTML or JSON API responses unless you explicitly create a Cache Rule telling it to do so.

### What happens when I click Purge Everything?
Cloudflare clears all cached static files from its edge. The next visitor triggers a `MISS`, and Cloudflare fetches fresh copies from your origin server.
