[//]: # (DOC_ID: SIRA-ARCH-CF_00 | VERSION: v1.0 | SCOPE: Cloudflare Beginner Documentation Index)
# Cloudflare Infrastructure for Beginners: Master Documentation Index

Welcome to the companion documentation suite for the interactive **Cloudflare Infrastructure for Beginners** course. This guide is written for anyone who has registered a domain name and wants to understand how Cloudflare protects, speeds up, and routes traffic to their website.

[//]: # (SECTION_ID: SIRA-ARCH-CF_00-SEC-1)
## 1. How to Use This Documentation

Read the chapters in numerical order if you are setting up a domain for the first time. Each chapter focuses on one core layer of Cloudflare, explains technical terms in plain English, and ends with a **Beginner Coder Q&A** section.

| Chapter File | Focus Topic | Course Module |
| :--- | :--- | :--- |
| `00A_OVERVIEW_AND_GLOSSARY.md` | Mental model and plain-English glossary | Course Intro |
| `01_DOMAIN_AND_REVERSE_PROXY.md` | Registrars, nameservers, reverse proxy, orange vs grey cloud | Module 1 |
| `02_DNS_RECORDS_EXPLAINED.md` | A, AAAA, CNAME, MX, TXT records, and TTL | Module 2 |
| `03_SSL_TLS_AND_HTTPS.md` | Edge certificates, Full Strict mode, redirect loops | Module 3 |
| `04_CACHING_AND_CONFIG_RULES.md` | Edge caching, CF-Cache-Status, Configuration Rules, RUM | Module 4 |
| `05_SECURITY_ANALYTICS_AND_SETUP_GUIDE.md` | DDoS, WAF, Rate Limiting, Analytics, and step-by-step setup | Module 5 |

[//]: # (SECTION_ID: SIRA-ARCH-CF_00-SEC-2)
## 2. First-Time Domain Setup Checklist

Use this quick checklist as you work through the chapters:

1. Create a free Cloudflare account and add your domain name.
2. Copy the two Cloudflare nameservers into your domain registrar dashboard.
3. Verify your A, CNAME, MX, and TXT records in the Cloudflare DNS tab.
4. Confirm web records use the **Orange Cloud (Proxied)** and mail records use the **Grey Cloud (DNS Only)**.
5. Set SSL/TLS mode to **Full (Strict)** once your origin server has a valid certificate.
6. Enable **Always Use HTTPS** and set Minimum TLS Version to **1.2**.
7. Test new WAF or Configuration Rules with **Log** or **Managed Challenge** before blocking traffic.
