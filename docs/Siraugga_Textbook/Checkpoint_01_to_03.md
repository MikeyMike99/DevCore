# CHECKPOINT: The Siraugga Defensive Doctrine (Modules 1-3)

*A comprehensive summary of the textbook modules constructed for the DevCore Siraugga Architecture.*

---

## Module 1: Asset Management & The Architecture of Paranoia
**Core Theme:** Defining the threat landscape and engineering layered, immutable defenses to protect the host infrastructure from both external attackers and internal autonomous AI agents.

### Key Concepts:
1. **Threat Identification:**
   * **Internal Threats:** Rogue Tier 2 Modders attempting path traversal, or legitimate Tier 3 Agents suffering from "Agentic Drift" (hallucinations resulting in destructive system calls).
   * **External Threats:** Adversaries attempting prompt injections via the WebSocket stream to hijack the Main Agent.
2. **Defense-in-Depth (The Onion Architecture):**
   * **The Semantic Firewall:** The outermost layer. An ultra-fast Evaluator LLM that intercepts prompts, filtering out hostile intent before the Main Agent ever sees the payload.
   * **The Raugus Checkpoint (Path Resolver):** The innermost layer. A rigid middleware that intercepts outbound File I/O requests, stripping absolute paths and mathematically confining agents to their assigned `TIER_SAFE_WORKSPACE`.
3. **Strategic Doctrines:**
   * **Hostile Layering:** Assuming every layer will eventually fail, requiring the next layer to operate independently.
   * **True Cryptography vs. Obscurity:** Rejecting "security through obscurity" (e.g., hiding a file) in favor of mathematical certainty (AES-256 encryption and `.devcore_master.key` derivation).

---

## Module 2: Operational Management & The Forensic Paradox
**Core Theme:** Controlling the execution environment, managing volatile telemetry, and deploying active interception tools to monitor the Zero-Trust grid.

### Key Concepts:
1. **The Mathematical Baseline:**
   * Absolute enforcement of system state, including sandboxed `cwd` paths, strict `O_NOFOLLOW` file descriptors, and the 4-second TCP keep-alive heartbeat.
2. **The Forensic Paradox & Cold Storage:**
   * **The Paradox:** Cryptographically shredding logs protects against symlink attacks and data leaks, but destroys the forensic evidence needed by incident responders.
   * **The Resolution (Cold Storage):** Before the Reaper Daemon shreds the physical plaintext logs, a Lifecycle Hook instantly AES-encrypts the telemetry using dynamically rotated keys (KMS), preserving the ciphertext exclusively for Tier 5 Admins.
3. **The Telemetry Taxonomy:**
   * **OS Logs (Tier 4):** Tracks WebSocket handshakes and resource utilization.
   * **Application Security Logs (Tier 4):** Tracks Semantic Firewall drops and prompt injection blocks.
   * **Application Error Logs (Tier 3):** Employs the *Secure Listener* pattern to trap stack traces internally while sending sanitized errors to the UI.
   * **CSP Logs (Tier 4):** Captures browser-level Cross-Site Scripting (XSS) blocks.
   * **Chatlogs (Tier 1-5):** The "Agentic Memory" of the swarm, protected by dynamic Agentic Sanitization.
4. **The Semantic Sniffer (Ingress & Egress):**
   * An active protocol analyzer that parses raw JSON traffic to detect architectural intrusions. It is decentralized into **Ingress** (Semantic Firewall) and **Egress** (Raugus Resolver). If a breach is detected, it triggers the Reaper Protocol to isolate the compromised process group.

---

## Module 3: The Mandate of Governance (Business Policies)
**Core Theme:** Establishing the absolute rules of engagement for both human operators and autonomous AI agents through rigid, mathematically enforced policies.

### Key Concepts:
1. **The Three Pillars of Governance:**
   * **Framework Policies (Company Policies):** Dictate acceptable system interaction and data privacy for the overall ecosystem.
   * **Entity Mandates (Employee Policies):** Define resource constraints. For AI agents, this means hardcoded API token budgets, CPU limits, and lifecycle timeouts.
   * **Security Policies (Prime Directives):** The non-negotiable architectural laws, including Cryptographic Key rotation, dual-binding TLS Remote Access (Port 5001), and Incident Response automation.
2. **The Acceptable Use Policy (AUP):**
   * A mathematically explicit list of forbidden commands (e.g., `rm -rf`). AI agents "sign" the AUP instantly upon boot by inheriting it into their System Prompt.
3. **The BYOD/C Policy (Bring Your Own Device & Code):**
   * Specifically tailored for third-party Modders connecting to the in-game plugin. It governs the importation of untested playground scripts and physical device connections.
   * It enforces strict socket control, Raugus path limits, Tier 5 Overwatch, and forces all imported code to synchronize with the core **SDK (Software Development Kit)** to guarantee security middleware routing.
4. **Regulatory Compliance:**
   * Acknowledges the legal liability of the game studio. Defines the architecture's obligation to protect Personally Identifiable Information (PII) and payment telemetry through immutable logs and encrypted transport layers.
