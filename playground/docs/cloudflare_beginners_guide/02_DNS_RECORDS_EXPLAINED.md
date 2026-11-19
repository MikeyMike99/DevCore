[//]: # (DOC_ID: SIRA-ARCH-CF_02 | VERSION: v1.0 | SCOPE: DNS Records and TTL Explained)
# Chapter 02: DNS Records Made Simple

Your Cloudflare DNS table is a list of short instructions. Each row has a **Type**, a **Name**, a **Content** value, a **Proxy status**, and a **TTL**.

[//]: # (SECTION_ID: SIRA-ARCH-CF_02-SEC-1)
## 1. The Five Core DNS Record Types

| Record Type | What It Does | Example Content | Proxy Allowed? |
| :--- | :--- | :--- | :--- |
| **A** | Points a domain to an IPv4 address | `198.51.100.25` | Yes (Orange or Grey) |
| **AAAA** | Points a domain to an IPv6 address | `2001:db8::1` | Yes (Orange or Grey) |
| **CNAME** | Points one hostname to another hostname | `example.com` | Yes (Orange or Grey) |
| **MX** | Routes incoming email to your mail provider | `mail.example.com` | No (Grey Only) |
| **TXT** | Stores verification strings and SPF/DKIM rules | `"v=spf1 -all"` | No (Grey Only) |

In Cloudflare, the `@` symbol in the **Name** field is shorthand for your root domain (such as `example.com` without `www`).

[//]: # (SECTION_ID: SIRA-ARCH-CF_02-SEC-2)
## 2. Why Order Matters: A Records Before CNAME Aliases

If you point `www` to `@` using a `CNAME` record, your root domain (`@`) must already have a valid `A` or `AAAA` record pointing to your origin server. Otherwise, `www` points to an address that does not resolve.

```json
{
  "type": "CNAME",
  "name": "www",
  "content": "example.com",
  "proxied": true
}
```

[//]: # (SECTION_ID: SIRA-ARCH-CF_02-SEC-3)
## 3. Understanding TTL (Time to Live)

**TTL** is the number of seconds other DNS resolvers remember an answer before asking Cloudflare again.

- A TTL of `300` means 5 minutes.
- A lower TTL helps DNS changes spread faster when you are migrating servers.
- Proxied (orange cloud) records in Cloudflare automatically use **Auto** TTL.

You can inspect public `TXT` or `A` records safely using:

```bash
dig TXT example.com
nslookup www.example.com
```

[//]: # (SECTION_ID: SIRA-ARCH-CF_02-SEC-4)
## 4. Cross-References & System Parallels

<details class="crossref-dropdown" style="border: 1px solid #38bdf8; border-radius: 6px; padding: 12px; margin: 20px 0; background: rgba(56, 189, 248, 0.05);">
<summary style="font-weight: bold; cursor: pointer; color: #38bdf8;">🔽 Cross-References & System Parallels (Click to Expand Dropdown)</summary>

| Related Project / Subsystem | Architectural Parallel & Shared Mechanism | Collection / Scope |
| :--- | :--- | :--- |
| **Chapter 01 (Domain & Proxy)** | Explains why web records use Orange Cloud and mail records stay Grey. | This Guide |
| **Chapter 03 (SSL/TLS)** | Securing the hostnames defined in your DNS table with HTTPS. | This Guide |

</details>

[//]: # (SECTION_ID: SIRA-ARCH-CF_02-SEC-5)
## Beginner Coder Q&A

### Can I put an IP address inside a CNAME record?
No. A `CNAME` record must always point to another domain name (like `example.com`), never a numeric IP address. Use an `A` or `AAAA` record for IP addresses.

### Why did my email break after moving DNS to Cloudflare?
Email breaks if `MX` records were not copied over from your old DNS provider, or if a mail subdomain was accidentally orange-clouded. Keep mail records grey-clouded.
