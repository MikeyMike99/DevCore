# Module 2: Access Control & Prompt Firewalls

## What Will I Learn in this Module?
This module explores the active defense systems that enforce the Sandbox tiers established in Module 1. You will learn:
* **Zero Trust Agentic Security:** Why the Siraugga framework assumes every AI tool call is inherently hostile until mathematically proven otherwise.
* **The Principle of Least Privilege:** How limiting an AI's Tool Whitelist prevents catastrophic Privilege Escalation (Jailbreaking).
* **Next-Gen Prompt Firewalls (NGPF):** How the Raugus Resolver inspects the semantic meaning of a JSON payload to block unauthorized actions.
* **Agentic Control Lists (ACLs):** How to define the exact type of JSON traffic allowed into a specific `/playground` namespace.

---

## 2.1 Zero Trust Agentic Security
Zero Trust is a comprehensive architectural approach to securing access across networks, AI subagents, and third-party environments. The overarching principle of Zero Trust is: **"Never trust, always verify."**

In legacy networks, the "perimeter" (the corporate firewall) was the only boundary between trusted internal users and the untrusted internet. In the Siraugga framework, this concept is completely inverted. Because autonomous AI agents are prone to Agentic Drift and hallucinatory Prompt Injections, *any place an access control decision is required is considered a perimeter*. 

Even if a highly privileged `Coding` subagent successfully authenticated and bypassed the outer firewall, it is not trusted to alter the `/playground` database until the Raugus Resolver mathematically verifies its specific `write_to_file` payload. The AI must be verified at every single layer of logic execution.

## 2.2 The Principle of Agentic Least Privilege
To enforce Zero Trust, DevCore utilizes the **Principle of Least Privilege**. This dictates that users and AI processes should be granted the absolute minimum amount of access required to perform their specific work function. 

In the DevCore ecosystem, if a subagent is tasked simply with reading a file to summarize its contents, it should *never* be spawned with a Tool Whitelist that includes `write_to_file` or `run_command`. Giving an AI tools it does not explicitly need vastly increases the attack surface if that AI suffers a Prompt Injection.

### Agentic Privilege Escalation (Jailbreaking)
When the Principle of Least Privilege fails, the system is vulnerable to **Privilege Escalation** (commonly known in the AI space as Jailbreaking). In this exploit, vulnerabilities in the access control system are used to grant a lower-tier AI higher levels of privilege. If an AI breaks out of its DAC (Discretionary) sandbox and gains MAC (Mandatory) root privileges, the entire host is compromised.


## 2.3 Next-Gen Prompt Firewalls (NGPF)
Legacy firewalls relied on "Port Monitoring" (e.g., blocking Port 80). In an AI ecosystem, Port Monitoring is entirely useless. Simply knowing that a Subagent used the `run_command` tool tells the Admin nothing. Was the AI running a diagnostic `ls` command, or was it compiling malware? 

To solve this, Siraugga utilizes a **Next-Gen Prompt Firewall (NGPF)** (often referred to as the Raugus Resolver). 

Instead of blocking ports, the NGPF performs **Semantic Visibility and Control (SVC)**. It deeply inspects the JSON payload of every tool call passing through the WebSocket. It analyzes the *semantic meaning* of the prompt. If the NGPF detects an Intrusion Event (e.g., a prompt attempting to override system instructions) or a Malware Event (an AI writing a destructive script), it violently severs the connection before the Subagent can even process the tokens.


## 2.4 Agentic Control Lists (ACLs)
While the NGPF analyzes semantic intent, **Agentic Control Lists (ACLs)** provide hard, static boundaries. An ACL is a sequential list of permit or deny statements applied to the sandbox.

For example, an Admin can configure an ACL that states:
1.  `Permit` the `read_file` tool if the target directory is `/playground/game_demo/`.
2.  `Deny` the `read_file` tool if the target directory contains `.env` or `/core_engine/`.
3.  `Deny` all other traffic.

### Sandbox Rule Evasion (Bypassing ACLs)
ACLs can give a false sense of security if they are overly relied upon. Sophisticated threat actors know how to bypass static ACLs using a technique known as **Sandbox Rule Evasion**.

Because an ACL only looks for exact string matches, a rogue AI can use **Semantic Steganography**. Instead of executing `cat .env` (which the ACL would block), the AI might encode the command in Base64 or obfuscate the bash script through string concatenation (e.g., `c""a""t .e""n""v`). This allows the malicious payload to slip past the static ACL, forcing the Orchestrator to rely on the probabilistic machine-learning models of the Next-Gen Prompt Firewall to catch the hidden intent.
