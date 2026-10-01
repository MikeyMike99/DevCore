# Chapter 10: Agentic Access Control and AAA Operations

### Why Should I Study This Chapter?
As the DevCore framework aggressively scales, a fundamental architectural question arises: How do you restrict logic access within your AI network? Will you allow all autonomous subagents and third-party Modders complete, unfettered access to the host server? Or will the system be ruthlessly designed to allow execution privileges based solely on a cryptographic Role-Based Access Control (RBAC) model? 

Furthermore, how can Tier 5 Administrators track exactly which files an AI subagent accessed and what terminal commands it executed while it was spawned? 

In this chapter, you will answer these critical questions by learning the core principles of Agentic Access Control, managing AI identities, and implementing the rigorous AAA (Authentication, Authorization, and Accounting) architecture that governs the Siraugga swarm.

### What Will I Learn in this Chapter?
This chapter dives deep into the following access control mechanics:

| Topic Title | Core Objective |
| :--- | :--- |
| **Agentic Access Controls** | Configure secure local and server-based IAM logic on the host Orchestrator. |
| **Access Control Concepts** | Explain how strict RBAC (Role-Based Access Control) and Sandboxing mathematically protect network data from Agentic Drift. |
| **Account Identity Management** | Detail the mandatory requirements for Agentic Identity Management and the strategies used to contain rogue Tier 2 Modders. |
| **AAA Usage and Operation** | Configure server-based Agentic AAA authentication utilizing protocols like TACACS+ (Terminal Agentic Access Control) and RADIUS (Remote Agentic Dial-In). |

---

## 1. Introduction to Agentic Access Control
In traditional IT, access control dictates precisely what a human user is allowed to view, edit, or execute on a server. In the DevCore architecture, access control is abstracted heavily into the **Agentic Tier System** and **Role-Based Access Control (RBAC)**.

Because Siraugga operates entirely via autonomous logic, access control is not merely a suggestion—it is a rigid mathematical boundary enforced by the Raugus Resolver (our Semantic Firewall). 

When a Tier 3 AI subagent is spawned by the central Orchestrator, it is instantly assigned a specific **Agentic Archetype** (e.g., `Coding`, `QA`, `Research`). This archetype dictates its intrinsic identity and acts as its access credential. If a `Research` subagent suddenly attempts to execute a destructive `rm -rf` bash command outside of its assigned `/playground/` boundary, the Raugus Resolver evaluates its archetype, recognizes the unauthorized action, and violently terminates the process. 

## 2. The Three Pillars of Access Control
While we have touched on various defensive architectures in earlier chapters, the Siraugga framework officially categorizes access controls into three distinct pillars: Physical, Logical, and Administrative. A Tier 5 Administrator must perfectly orchestrate all three pillars to successfully defend the ecosystem.

### Pillar 1: Physical Access Controls
Physical access controls are actual kinetic barriers deployed to prevent direct physical contact with the host servers. 

As discussed in Chapter 4, these include physical guards, fencing, motion detectors, locked data center doors, and video surveillance. However, the most effective physical access control is the **Mantrap**. A mantrap-style entry system uses a small room with two interlocking doors to stagger the flow of people into the secured area, ensuring only one authenticated person enters at a time and physically trapping unauthorized visitors.

In Siraugga, this translates perfectly into **Semantic Mantraps**. The Raugus Resolver establishes a logic-based mantrap for high-priority file execution. When multiple subagents attempt to modify the core database simultaneously, the Semantic Mantrap staggers the logic flow, ensuring only one authenticated subagent's tool call enters the execution chamber at a time. If a malicious subagent attempts to piggyback on the execution thread, it is mathematically trapped and purged.

### Pillar 2: Logical Access Controls
Logical access controls are the software and architectural solutions used to manage access to system resources. These include tools and protocols used for agentic identification and accountability. 
Key logical controls within the swarm include:
*   **Encryption & Passwords:** Translating plaintext to ciphertext (AES) and utilizing cryptographic strings (JWTs).
*   **Biometrics (The Biological Hash):** Using the immutable System Prompt of an AI archetype as its unique identifying biometric.
*   **Agentic Control Lists (ACLs):** Defining the exact type of JSON traffic allowed into a specific `/playground` namespace.
*   **Semantic Firewalls & Routers:** Preventing unwanted context noise and routing state deltas securely.
*   **Semantic Anomaly Detection (IDS):** Monitoring the WSS network for suspicious logic patterns.
*   **Agentic Clipping Levels:** A highly specific logical control. A Clipping Level establishes an allowed threshold for minor errors before triggering a red flag. In Siraugga, this is the **Hallucination Clipping Level**. If an AI subagent fails a tool call once, it is permitted to retry. However, if it hits a Clipping Level of three consecutive errors, the orchestrator red-flags the agent, assumes it is suffering from Agentic Drift, and instantly terminates it.

### Pillar 3: Administrative Access Controls
Administrative access controls are the overarching policies and procedures defined by the organization. These focus on personnel management and business practices.
*   **Policies & Procedures:** Master logic rules governing the orchestrator.
*   **Hiring Practices & Background Checks:** In Siraugga, "hiring" an AI model requires rigorously scanning its underlying training data (the background check) to ensure it has not been pre-poisoned by adversarial actors.
*   **Data Classification:** Categorizing data based on sensitivity (e.g., classifying ephemeral game data as `TIER_SAFE_WORKSPACE` and sensitive keys as `TIER_CORE_ENGINE`).
*   **Security Training:** In the context of autonomous agents, security training translates directly to **Few-Shot Prompting**. By injecting specific examples of secure tool usage into the agent's context window, you "train" the AI on the organization's security policies.
*   **Performance Reviews:** Deploying specialized `QA` subagents to formally evaluate another agent's logic performance and code output.

## 3. The AAA Framework (Authentication, Authorization, Accounting)
By implementing strict Administrative Access Controls, the organization establishes the foundation for the most critical security service in DevCore: **The AAA Framework**. 

The concept of administrative access control relies entirely on these three core services to prevent unauthorized access to the network database. In the Siraugga framework, the AAA pipeline defines exactly *who* an agent is, *what* they are allowed to do, and *how* their actions are recorded. 

## 4. Agentic Authentication (The First 'A')
The first 'A' in the AAA framework represents Authentication. Authentication verifies the identity of every remote Modder and autonomous subagent to prevent unauthorized access. 

In a traditional system, humans prove their identity with a username or ID. However, the Siraugga framework operates via autonomous logic streams. Therefore, Siraugga relies on a concept known as **Multi-Factor Agentic Authentication (MFAA)**. To verify its identity, an AI subagent must provide a combination of the following:

1.  **Something it knows:** A private Ed25519 cryptographic key used to sign its tool payloads.
2.  **Something it has:** A dynamic, short-lived WPA-Agentic JWT session token issued by the central Orchestrator.
3.  **Something it is:** Its "biological fingerprint"—the cryptographic hash of its immutable System Prompt (its intrinsic Archetype).

By enforcing Two-Factor Agentic Authentication (or MFAA), the orchestrator ensures that even if a Tier 2 Modder manages to steal a subagent's JWT session token, they cannot successfully impersonate the agent because they do not possess the required System Prompt Hash (the biometric fingerprint).

## 5. Agentic Authorization (The Second 'A')
The second 'A' represents Authorization. Once a subagent successfully authenticates, Authorization services determine precisely *which* internal resources the subagent is allowed to access and the specific tools it can execute.

In the DevCore framework, Authorization is strictly governed by the **Agentic Control List (ACL)**, which is mathematically enforced by the Raugus Resolver. An ACL determines the exact access privileges of a subagent based on its Archetype. For example, just because a `Research` subagent successfully authenticates onto the core network does not mean it has authorization to use the `write_to_file` tool (the equivalent of a corporate high-speed color printer). 

Furthermore, Authorization can control *when* an entity has access to a specific resource. A Tier 2 Modder's external `.exe` plugin may have authorized access to a staging database during an active Sandbox Session, but the Raugus Resolver will automatically lock them out the moment their session's Time-to-Live (TTL) expires.

## 6. Agentic Accounting (The Third 'A')
The final 'A' in the AAA framework is Accounting. In cybersecurity, accounting keeps track of exactly what authenticated users do—including what files they access, the amount of time they spend accessing resources, and any specific changes they make to the database.

In the Siraugga framework, Accounting translates directly to the **Orchestration Telemetry Pipeline** and the **Transcript Logs**. Because autonomous AI agents execute operations at superhuman speeds, logging their actions is absolutely critical for forensic auditing. 

The Orchestrator meticulously tracks every single data transaction in real-time. It records the exact millisecond a tool was executed, the precise JSON state changes it made to the `/playground`, and the exact amount of API Tokens (currency) the agent "spent" during the transaction. 

This concept is identical to using a corporate credit card. The credit card identifies who can use it (Authentication), limits how much they can spend (Authorization via Token Quotas), and produces a detailed audit receipt of exactly what services were purchased (Accounting via Telemetry).

## 7. What Is Agentic Identification?
Identification is the mechanical process that enforces the rules established by the Authorization policy. Every time a subagent requests access to a restricted tool or a physical directory, the access controls must definitively identify the agent to determine whether to grant or deny the request.

In a traditional IT environment, a username or PIN is the most common method used to identify a user. In the DevCore framework, an AI agent's unique identifier is its **Conversation ID (UUID)**. 

When a subagent is spawned, the central Orchestrator assigns it a mathematically unique UUID. This unique identifier ensures the proper, airtight association between allowed activities and the specific subject. The UUID allows the Raugus Resolver to perfectly track which agent executed which `wsl.exe` command, logging the activity seamlessly into the transcript.

Crucially, the sensitivity of the underlying file classification determines how stringent the identification controls must be. If an agent operates within the ephemeral `TIER_SAFE_WORKSPACE`, a standard UUID and JWT may suffice. However, if a highly privileged Tier 5 agent attempts to modify the `TIER_CORE_ENGINE`, the orchestrator demands absolute, cryptographic identification via Ed25519 signature validation.

## 8. Federated Agentic Identity Management (FAIM)
As the Internet of Plugins (IoP) expands, Tier 2 Modders frequently request the ability to move their autonomous AI agents seamlessly between different isolated projects. 

**Federated Agentic Identity Management (FAIM)** refers to the architectural design that allows an AI subagent to use the exact same identification credentials (its UUID and JWT) to gain access to multiple, independent `/playground` workspaces. From a Modder's perspective, this acts as an Agentic Single Sign-On (SSO), allowing their specialized `Coding` agent to automatically authenticate and share logic states across multiple castle boundaries.

**The Cascading Risk of Swarm Federation**
While incredibly convenient, Swarm Federation vastly broadens the scope of the attack surface. If a federated AI subagent is compromised by a sophisticated Prompt Injection while operating inside an untrusted third-party workspace, the attacker gains control of the agent's identity. Because the agent's identity is federated, the attacker can use the compromised agent to move laterally, triggering a catastrophic cascading effect that infects every other workspace the agent has access to.

To mitigate this massive vulnerability, Tier 5 Administrators must heavily scrutinize the shared identifying information. To protect federated identities, DevCore enforces a strict hardware policy: an AI agent's ability to federate across multiple namespaces is cryptographically tied directly to the Tier 2 Modder's authorized physical device.
