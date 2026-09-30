# Chapter 6: Securing Network Devices (AI Subagents & Sandboxing)

## 1. Introduction to Agentic Security
In traditional IT architecture, securing your physical network devices—such as routers, switches, and load balancers—is the most fundamental way of protecting a network from a cyberattack. 

However, in the Siraugga framework, the structural "devices" on our network are not physical hardware components. Instead, the devices are the **AI Subagents** themselves. These autonomous logic nodes constantly spin up in the background, route prompt traffic, parse JSON state deltas, and gracefully collapse back into the void once their task is complete.

Because these subagents act as the dynamic infrastructure of the swarm, securing these "network devices" is absolutely paramount. If a single Tier 3 subagent is compromised via a sophisticated Prompt Injection, it can be weaponized to attack the core orchestration engine. 

In this chapter, we will explore the fundamental methods of securing, restricting, and sandboxing these agentic network devices to protect the Siraugga mainframe from collapse.


## 2. Agentic Segmentation (Micro-Swarming)
In traditional IT infrastructure, segmentation involves physically or logically dividing a computer network into smaller parts (such as subnets or VLANs) to improve network performance and strictly limit the blast radius of a security breach. 

In the Siraugga framework, this concept translates directly to **Agentic Segmentation**, commonly referred to within the industry as *Micro-Swarming*. Rather than deploying a monolithic, highly privileged Artificial Intelligence to govern the entire application, the Siraugga core architecture mathematically segments execution logic into dozens of isolated, highly specialized subagents.

For example, an End User's complex natural language intent might be automatically segmented into a `Research` subagent, a `Coding` subagent, and a `QA_Testing` subagent. Each subagent is spawned dynamically with *only* the specific tool permissions necessary to complete its localized task. 

By segmenting the AI network logic, Siraugga achieves two critical benefits:
1. **Performance:** Specialized subagents running on optimized, low-latency models (such as the `flash` tier) consume vastly fewer tokens and execute at lightspeed compared to monolithic logic blocks.
2. **Containment:** If a sophisticated attacker successfully compromises a `QA_Testing` subagent with an adversarial Prompt Injection, the blast radius is strictly contained to that single node. The primary orchestrator and the other logic nodes remain mathematically untouched and mathematically uncompromised.