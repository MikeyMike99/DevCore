# Chapter 3: The Mandate of Governance (Business Policies)

Before we can enforce physical security or build cryptographic walls, we must define the rules of engagement. In a corporate environment, "business policies" are the guidelines developed by an organization to govern human action. They define the absolute standards of correct behavior for the business and its employees. 

In the Siraugga framework, policies are not just corporate HR documents; they are the architectural blueprints that define exactly what activities are mathematically permitted within the environment. This establishes a rigid baseline of acceptable use for both human operators and autonomous AI agents. 

If behavior that violates this policy is detected on the Zero-Trust grid—whether by a Tier 2 Modder attempting path traversal or a hallucinating sub-agent trying to execute an unauthorized script—it is not treated as a user error; it is treated as an active security breach.

To govern a hostile environment effectively, the architecture must enforce several guiding mandates, as listed below:

### 1. Framework Policies (Company Policies)
In a traditional business, company policies dictate human responsibilities (e.g., dress code, privacy, and corporate ethics). In Siraugga, Framework Policies establish the absolute rules of conduct and the responsibilities of both the human operators and the autonomous swarm. 
* They protect the intellectual property of the core engine while simultaneously guaranteeing the functional rights of Tier 2 Modders operating within their designated sandboxes.
* These policies define exactly what constitutes acceptable system interaction, dictating data privacy standards and strict terms of engagement for any entity generating or executing code on the platform.

### 2. Entity Mandates (Employee Policies)
Traditional HR policies identify human salary, benefits, and vacation time. In our Zero-Trust architecture, human developers and AI subagents are both treated equally as operational 'entities.' Entity Mandates define the exact resource constraints for these actors.
* For humans, these mandates define operational scopes, deployment schedules, and authorization limits.
* For AI agents, these policies are codified directly into the orchestration engine as strict CPU limits, API token budgets, execution timeouts, and lifecycle boundaries. Before a sub-agent is ever spawned, it must mathematically "sign" these limits by inheriting its rigid system prompt.

### 3. Security Policies (The Prime Directives)
Security policies are the crown jewels of organizational governance. They identify the absolute security objectives of the Siraugga framework, defining rigid, non-negotiable rules of behavior for everyone—from Tier 1 end-users to Tier 5 SysAdmins.
* They explicitly specify the baseline system requirements required to operate (such as the presence of the offline `.devcore_master.key` and the Semantic Sniffer).
* These objectives, rules, and requirements are not merely suggestions; they are the mathematical laws that collectively ensure the survival of the network and the underlying computer systems.

### The Benefits of Absolute Governance
In Siraugga, a comprehensive security policy is not a bureaucratic checklist; it is the survival mechanism of the architecture. Enforcing these prime directives yields several critical benefits:
* **The Cryptographic Commitment**: It mathematically demonstrates the framework's absolute commitment to Zero-Trust security, proving to stakeholders that no entity is above the law.
* **Deterministic Execution**: It sets the rigid boundaries for expected behavior, ensuring that if an AI hallucinates, it hits a hard architectural wall rather than a soft suggestion.
* **Operational Consistency**: It ensures perfect consistency in backend system operations, strictly controlling how software dependencies are acquired, how virtual resources are allocated, and how the Raugus Resolver is maintained.
* **The Consequence of Violation**: It defines the immediate, automated consequences of a breach—ranging from the instant `SIGKILL` of an offending process group to the permanent cryptographic blacklisting of a rogue developer's access token.
* **The Authority of Tier 5**: It grants Tier 5 SysAdmins the absolute, unquestionable architectural backing to sever WebSocket connections, purge telemetry, or permanently isolate exploited workspaces during an active crisis.

### The Architecture of a Security Policy
In the Siraugga framework, Security Policies are not passive documents; they are active architectural contracts. They are used to rigidly inform human operators, autonomous swarms, and Tier 5 SysAdmins of the exact mathematical requirements for protecting the backend infrastructure and intellectual property assets. 

Furthermore, these policies explicitly specify the *mechanisms* required to enforce those requirements—such as the Raugus Resolver and the Semantic Firewall. They establish the absolute baseline from which all virtual environments are acquired, configured, and audited for cryptographic compliance.

The following sections detail the specific doctrines that must be included in a complete Zero-Trust Security Policy:

| Core Doctrine | Architectural Enforcement |
| :--- | :--- |
| **Identification & Authentication Policy** | Governs the strict verification of identity. Specifies that all session tokens must be mathematically verified via `scrypt` hashing and SHA-256 before an entity is assigned its RBAC Tier. |
| **Cryptographic Key (Password) Policies** | Ensures that cryptographic keys (such as the KMS Data Encryption Keys and the Master Key) meet extreme entropy requirements and are rotated automatically to defeat brute-force exhaustion. |
| **Acceptable Use Policy (AUP)** | Enforced dynamically by the Semantic Firewall. It explicitly defines which commands and system calls are acceptable for a sandboxed agent. Violations result in immediate WebSocket termination. |
| **Remote Access Policy** | Dictates that all external Web UI access must pass through the dual-binding Hypercorn TLS proxy on Port 5001. Internal `localhost` debug access is restricted to the isolated Port 5000. |
| **Maintenance & Patching Policy** | Specifies the exact procedures for updating the underlying host environment and the Raugus routing map (`system_aliases.json`) without breaking active agent sandboxes. |
| **Incident Response Protocol** | Dictates the automated sequence of events when a breach occurs, including freezing `tmpfs` RAM-disks, triggering the Reaper Daemon, and escalating encrypted telemetry to Tier 5 Admins. |

### The Acceptable Use Policy (AUP)
One of the most critical components of the Siraugga governance model is the **Acceptable Use Policy (AUP)**. In legacy corporate systems, an AUP is a physical piece of paper signed by an employee stating they will not browse bandwidth-intensive websites while on the corporate network. 

In a Zero-Trust orchestration environment, the AUP defines the absolute, explicit boundaries of what human operators and autonomous AI agents are allowed to execute on the backend. Because ambiguity in AI instructions can lead to catastrophic system damage (Agentic Drift), the AUP must be mathematically explicit to avoid any misunderstanding.

For example, the Siraugga AUP explicitly lists the exact Bash commands (e.g., `rm -rf`, `chmod 777`), Python modules (e.g., `os.system()`, `subprocess`), and unauthorized outbound API endpoints that are strictly prohibited from being executed by a sandboxed agent. 

Rather than relying on a physical signature, every AI subagent "signs" the AUP instantly upon initialization by inheriting it as its core System Prompt. This immutable, cryptographic signature is retained in the `transcript.jsonl` for the absolute lifetime of the session. This guarantees that if the agent attempts to violate the policy, the Semantic Firewall has the full architectural mandate to instantly terminate the process.
