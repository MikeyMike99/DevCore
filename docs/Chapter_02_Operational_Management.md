# Chapter 2: Operational Management & The Configuration Crucible

Security does not end when the code compiles. The most impenetrable architecture in the world will rot from the inside out if the daily operational management is flawed. In the Siraugga framework, an administrator must master specific, high-stakes operational processes to ensure the Zero-Trust grid remains lethal against adversaries, rather than becoming a cage for its own developers. 

We will begin by stripping down the absolute requirements of **Configuration Management**—the ruthless process of maintaining the exact, mathematical state of the environment against entropy and unauthorized mutation.

### The Mathematical Baseline
Configuration management is not a suggestion; it is the absolute discipline of identifying, controlling, and violently auditing every single change made to a system’s established baseline. 

The **Baseline Configuration** is the DNA of the security architecture. It includes every environment variable, every RBAC permission, and every path-resolution rule configured for the host. This baseline acts as an immutable template for all deployments.

For instance, in traditional IT, a baseline might define how a standard Windows workstation is provisioned for an intern. In the Siraugga framework, the baseline dictates exactly how a new `TIER_SAFE_WORKSPACE` is forged for a Tier 2 Modder or an autonomous AI Agent. Before the entity is ever granted a WebSocket connection, the system must rigidly assemble the workspace, inject the required JSON configurations, and lock the sandbox down according to the exact parameters of the documented baseline. 

If a workspace environment deviates from this baseline by even a single unapproved byte, it is considered compromised and must be purged.

### The Siraugga Baseline Configurations (Governance & Policy)
A baseline is not just a technical setting; it is the very foundation of discipline and principles. Baselines form the absolute starting point of our governance and policies. Without a mathematical baseline, it is impossible to define discipline, and without discipline, you cannot govern security policies.

In our architecture, the established baselines are non-negotiable and are hardcoded directly into the orchestration engine and the security routing logic:

1. **The Working Directory Baseline (CWD)**: When a non-admin entity (Tier 1-3) connects, their execution baseline is anchored strictly to `/sandbox/projects/<assigned_project_id>`. The OS-level environment is scrubbed of all external path context.
2. **The Agent Execution Baseline**: Any autonomous AI invoked within the framework is forcefully injected with the `--sandbox` flag. The baseline explicitly blocks `--dangerously-skip-permissions` for all non-admin roles.
3. **The RBAC Authorization Baseline**: Upon authentication, every session must map mathematically to an established tier: `admin` -> Tier 5, `dev` -> Tier 3, `mod` -> Tier 2. There is no gray area or default privilege.
4. **The Network Continuity Baseline**: The WebSocket server enforces a brutal 4-second keep-alive heartbeat. If a client fails to ping the server within this baseline window, the connection is instantly severed to prevent orphaned, zombie execution loops.
