# Chapter 16: Configuring Agentic Control Lists

## 16.1 Crafting the Agentic Policy

Before a Tier 5 Admin configures a complex Agentic Control List (ACL) in the live engine, strict deployment procedures must be followed. A single typo in an ACL can instantly sever the connection for an entire Modder Swarm or accidentally grant an AI root terminal access.

When configuring an ACL for the `agent_manager.py`, it is mandated that you:
1.  **Draft Offline:** Use a text editor to write out the specifics of the security policy.
2.  **Add Remarks:** Always include explicit `remark` commands to document *why* the ACL was created.
3.  **Test in the Crucible:** Always thoroughly test the ACL in the Staging Crucible to ensure it doesn't trigger an accidental Semantic Mantrap lock-out.

## 16.2 Standard and Extended ACL Syntax (`agy` CLI)

DevCore allows Admins to configure these lists via the native `agy` Command Line Interface. While legacy configurations used arbitrary numbers, **Named ACLs** are the absolute standard.

### Standard Named Agentic ACLs
Standard ACLs filter strictly based on the Agent's identity (UUID) or the Modder's subnet. To enter the standard configuration mode:

```bash
agy(config)# acl standard NO-ACCESS
agy(config-std-nacl)# remark Deny all rogue agents from Modder Block 192.168.1.0
agy(config-std-nacl)# deny 192.168.1.0 0.0.0.255
agy(config-std-nacl)# permit any
agy(config-std-nacl)# exit
```

### Extended Named Agentic ACLs
Extended ACLs are significantly more complex. They filter by Identity (UUID) *and* by Tool Intent (similar to network Protocols and Ports). 

```bash
agy(config)# acl extended NO-CLI-ACCESS
agy(config-ext-nacl)# remark Deny terminal execution for this specific agent
agy(config-ext-nacl)# deny tool host Agent-104 any eq run_command
agy(config-ext-nacl)# permit tool host Agent-104 any eq view_file
```
*Note: The `log` keyword can be appended to the end of any ACE. This forces the Orchestrator to generate an informational message in `transcript.jsonl` every time the rule is matched. Because logging is computationally expensive, it should only be used for active security auditing.*

## 16.3 Translating Ports to Agentic Tools

In traditional networking, extended ACLs filter based on Internet Protocols (TCP, UDP) and Port Numbers (80 for HTTP, 22 for SSH). In DevCore, these concepts translate directly to **Agentic Tools**.

When defining an Extended ACL, the Orchestrator maps standard ports to explicit sandbox capabilities:
*   **Port 80 / 443 (HTTP/HTTPS) $\rightarrow$ `view_file` & `web_search`**: Standard read-only tools used by Research Archetypes.
*   **Port 22 (SSH) $\rightarrow$ `run_command`**: Secure shell execution. The most dangerous tool, heavily restricted to highly trusted Coding Archetypes.
*   **Port 21 (FTP) $\rightarrow$ `write_to_file`**: File transfer and modification capabilities.

An Admin can configure the ACL using either the native tool name or its mapped port number. Both commands achieve the exact same restriction:
```bash
agy(config)# acl extended 100 permit tool any any eq view_file
!or...
agy(config)# acl extended 100 permit tool any any eq 80
```

## 16.4 Stateful Agentic Firewalls (The `established` Keyword)

Perhaps the most critical security feature in the DevCore filtering engine is the `established` keyword, a 1st-generation firewall feature adapted to prevent **Prompt Injections**.

If an AI subagent is permitted to search the web or query an external API (like an untrusted Modder's database), the system faces a severe vulnerability: the external server could send back a malicious payload designed to hijack the AI's context window.

By appending the `established` keyword to an inbound ACL, the Orchestrator implements a **Stateful Agentic Firewall**. 
*   The AI is permitted to send a request *out* to the public network.
*   The web server is permitted to send the exact returning reply *in*.
*   However, if the external web server (or a malicious user) attempts to arbitrarily initiate a *new* connection to inject commands into the AI's prompt, **it is violently denied.** 

The `established` parameter dictates that a match only occurs if the returning JSON segment belongs to an existing, AI-initiated thought process. Without this parameter, the AI would be completely exposed to external hijackers.
