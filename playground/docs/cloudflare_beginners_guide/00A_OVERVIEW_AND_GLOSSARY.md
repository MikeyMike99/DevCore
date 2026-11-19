[//]: # (DOC_ID: SIRA-ARCH-CF_00A | VERSION: v1.0 | SCOPE: Cloudflare Overview and Beginner Glossary)
# Chapter 00A: System Overview and Beginner Glossary

Take your time. You cannot break anything while learning how Cloudflare works. When you buy a domain name, it is normal to wonder where your website files actually live and what Cloudflare does in the middle.

[//]: # (SECTION_ID: SIRA-ARCH-CF_00A-SEC-1)
## 1. What Cloudflare Actually Is

Cloudflare is not a web host where you upload HTML files or databases. Instead, Cloudflare is a global **edge network** that stands in front of your real web server (called your **origin server**).

When a visitor types your domain name into their browser:

1. Their browser asks **DNS** for the address of your website.
2. Because your domain uses Cloudflare, the request goes to the nearest Cloudflare data center instead of directly to your server.
3. Cloudflare checks if the request is safe, serves cached images or pages if it already has them, and forwards anything else to your origin server.

[//]: # (SECTION_ID: SIRA-ARCH-CF_00A-SEC-2)
## 2. Why Order Matters When Learning Cloudflare

Setting up a domain follows a strict dependency chain:

1. **Ownership (Registrar)** comes first: you must own the domain.
2. **Routing (Nameservers and DNS)** comes second: the internet must know to ask Cloudflare.
3. **Encryption (SSL/TLS)** comes third: traffic must be encrypted before visitors trust the site.
4. **Speed and Security (Caching, Rules, WAF)** come fourth: edge rules only run after traffic flows through Cloudflare's proxy.

Skipping steps—such as writing a firewall rule before your DNS record is proxied—causes rules to never fire.

[//]: # (SECTION_ID: SIRA-ARCH-CF_00A-SEC-3)
## 3. Plain-English Glossary

| Term | Plain-English Meaning |
| :--- | :--- |
| **Registrar** | The company where you rent your domain name (for example, Namecheap, Porkbun, or Cloudflare Registrar). |
| **DNS** | Domain Name System; the internet phonebook that turns `example.com` into a numeric IP address. |
| **Origin Server** | Your actual web server or hosting computer where your website files and code live. |
| **Reverse Proxy** | A middle server that accepts visitor connections on behalf of your origin server. |
| **Edge** | Cloudflare's data centers located around the world, close to your visitors. |
| **TTL** | Time to Live; how many seconds a DNS answer is remembered before checking again. |
| **WAF** | Web Application Firewall; a filter that blocks malicious web requests at the edge. |
| **RUM** | Real User Monitoring; a lightweight script used by Cloudflare Web Analytics to count real visits. |

[//]: # (SECTION_ID: SIRA-ARCH-CF_00A-SEC-4)
## 4. Cross-References & System Parallels

<details class="crossref-dropdown" style="border: 1px solid #38bdf8; border-radius: 6px; padding: 12px; margin: 20px 0; background: rgba(56, 189, 248, 0.05);">
<summary style="font-weight: bold; cursor: pointer; color: #38bdf8;">🔽 Cross-References & System Parallels (Click to Expand Dropdown)</summary>

| Related Project / Subsystem | Architectural Parallel & Shared Mechanism | Collection / Scope |
| :--- | :--- | :--- |
| **Networking Fundamentals** | Domain resolution, IPv4/IPv6 addressing, and client-server routing. | Siraugga Course |
| **Cybersecurity Fundamentals** | Defense in depth, TLS encryption in transit, and firewall filtering. | Siraugga Course |
| **Chapter 01 (Domain & Proxy)** | Deep dive into registrars, nameservers, and the orange cloud toggle. | This Guide |

</details>

[//]: # (SECTION_ID: SIRA-ARCH-CF_00A-SEC-5)
## Beginner Coder Q&A

### Do I have to move my website files to Cloudflare?
No. Your website files stay on your web host (your origin server). Cloudflare sits in front of your host to protect it and speed it up.

### Is Cloudflare free for a beginner domain?
Yes. Cloudflare's Free plan includes DNS management, Universal SSL (HTTPS), automatic DDoS protection, basic caching, and Web Analytics.
