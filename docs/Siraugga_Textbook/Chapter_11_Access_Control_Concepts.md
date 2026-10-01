# Chapter 11: Access Control Concepts and Privilege Escalation

## 1. Zero Trust Agentic Security
Zero Trust is a comprehensive architectural approach to securing access across networks, AI subagents, and third-party environments. The overarching principle of Zero Trust is: **"Never trust, always verify."**

In legacy networks, the "perimeter" (the firewall) was the only boundary between trusted internal users and the untrusted internet. In the Siraugga framework, this concept is completely inverted. Because autonomous AI agents are prone to Agentic Drift and hallucinatory Prompt Injections, *any place an access control decision is required is considered a perimeter*. 

Even if a highly privileged `Coding` subagent successfully authenticated and bypassed the outer firewall, it is not trusted to alter the `/playground` database until the Raugus Resolver mathematically verifies its specific `write_to_file` payload. The AI must be verified at every single layer of logic execution.

**The Three Pillars of Zero Trust**
DevCore categorizes the Zero Trust framework into three core pillars:
1.  **Zero Trust for the Workforce (Modders):** Ensuring only authenticated Tier 2 Modders with valid HSM tokens can access the Zero-Restart Web Portal, regardless of their physical location.
2.  **Zero Trust for Workloads (The Swarm):** Securing the internal logic. Ensuring that AI subagents (the workload) cannot move laterally or execute tools outside their mathematically assigned boundaries.
3.  **Zero Trust for the Workplace (The IoP):** Securing the Internet of Plugins. Ensuring that third-party webhooks, offline `.exe` sandboxes, and connected Modder devices are rigorously contained.

## 2. Agentic Access Control Models
To mathematically protect its network resources and the underlying game engine, DevCore utilizes specific access control models. Security Analysts must intimately understand these distinct models to defend against attackers trying to break them.

*   **Discretionary Agentic Control (DAC):** The least restrictive model. In DAC, the creator (or owner) of the data controls who has access to it. In Siraugga, this applies to the `TIER_SAFE_WORKSPACE`. A Tier 2 Modder who creates a new JSON game asset in their local `/playground` has Discretionary Control over who can read or edit that specific file.
*   **Mandatory Agentic Control (MAC):** The strictest model, typically used in military applications. It assigns absolute security clearances to specific files. In Siraugga, this applies to the `TIER_CORE_ENGINE`. Even if a Tier 5 Admin wanted to give a Tier 2 Modder DAC control over `server.py`, they cannot. The operating system intrinsically restricts the file to root clearance (Tier 5) only.
*   **Role-Based Agentic Control (RBAC):** The primary logic model of the Siraugga framework. Access decisions are based exclusively on an entity's role. If an AI subagent is spawned with the `Research` Archetype, it is bound to the `Research` RBAC profile. It is mathematically impossible for it to inherit the privileges of a `Coding` role.
*   **Rule-Based Agentic Control:** Network security staff specify rigid conditions associated with tool access. For example, a rule might specify that an AI subagent can only execute a tool if the payload is formatted in strict JSON, outright rejecting any raw plaintext parameters.

## 3. The Principle of Agentic Least Privilege
Another core access control model is the **Principle of Least Privilege**. This dictates that users and processes should be granted the absolute minimum amount of access required to perform their specific work function. 

In the DevCore ecosystem, if a subagent is tasked simply with reading a file to summarize its contents, it should *never* be spawned with a Tool Whitelist that includes `write_to_file` or `run_command`. Giving an AI tools it does not explicitly need vastly increases the attack surface if that AI suffers a Prompt Injection.

**Agentic Privilege Escalation (Jailbreaking)**
A common cyber exploit is known as Privilege Escalation. In this exploit, vulnerabilities in the access control system are used to grant a lower-tier user higher levels of privilege. 

In the Siraugga framework, this translates directly to **Agentic Jailbreaking** or **Rooting**. If an attacker manages to exploit a Rule-Based access control flaw, they can inject malicious instructions that overwrite a subagent's immutable System Prompt. By overwriting the prompt, they trick the central Orchestrator into escalating the agent's privileges, turning a sandboxed Tier 3 subagent into a Tier 5 master administrator. Once the privilege is granted, the threat actor takes complete control of the logic mainframe.
