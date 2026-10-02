# Chapter 14: Introduction to Agentic Control Lists (ACLs)

## 14.1 The Agentic Gateman (Why ACLs are Necessary)

Imagine the highly secure, isolated directories where your core game engine logic resides. Much like an armed guard standing at the entrance to a physical gated community, the Siraugga Orchestrator must enforce uncompromising rules for who can enter and leave those digital premises. The guard will not raise the gate to let a visitor in until their identity is mathematically confirmed against a strict, pre-approved visitor list. 

In the DevCore ecosystem, this concept is implemented via **Agentic Control Lists (ACLs)**. 

Whenever a Tier 2 Modder or an autonomous AI subagent attempts to pass JSON state data or terminal commands through the Zero-Restart Web Portal, that traffic hits an interface configured with an Agentic ACL. The ACL acts as a rigid, unfeeling filter. It scans the incoming traffic and immediately categorizes it into two actions: **Permitted** or **Denied**. 

But how are these rigid lists configured? How does a Tier 5 Admin modify an active ACL if the Raugus Resolver is accidentally dropping legitimate AI traffic, or if a new game mod requires a structural change? Chapter 14 introduces the fundamental mechanics of defining, building, and deploying these filters.

---

## 14.2 Module Objectives & Master Syllabus

This module is the definitive guide to implementing Agentic Control Lists to filter AI swarm traffic and mitigate hostile network attacks (such as Prompt Injections or Semantic DoS). 

The following core topics dictate the architecture of DevCore's filtering engine:

1.  **Introduction to Agentic Control Lists:** The critical differences between Standard ACLs (filtering solely by Agent UUID) and Extended ACLs (filtering by UUID, Archetype, specific Tool, and exact filepath).
2.  **Semantic Wildcard Masks:** Understanding how the Orchestrator uses regex and wildcard variables to blanket-approve or blanket-deny an AI’s access to a sprawling project directory (e.g., `allow: /game_demo/docs/*.md`).
3.  **Configuring ACLs:** The exact syntax and hierarchy required to build airtight security rules in `agent_manager.py` without accidentally locking out the entire swarm.
4.  **Modifying ACLs:** Utilizing Sequence Numbers to dynamically edit existing Agentic ACLs on the fly, without needing to reboot the `server.py` engine.
5.  **Implementing ACLs:** Deploying the filters onto the live WebSocket interfaces and observing the resulting traffic flow.
6.  **Mitigating Attacks with ACLs:** Deploying specifically tailored Extended ACLs to neutralize common adversarial threats, including rogue subagents attempting path-traversal attacks.
7.  **Next-Gen Swarm ACLs (IPv6 Equivalent):** Configuring advanced, high-density ACLs via the CLI to handle massive swarms of thousands of concurrent AI subagents.

The survival of the core game state depends entirely on the mathematical perfection of these lists. An AI agent is only as safe as the ACL that binds it.
