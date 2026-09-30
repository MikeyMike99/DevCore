# Chapter 6: Securing Network Devices (AI Subagents & Sandboxing)

## 1. Introduction to Agentic Security
In traditional IT architecture, securing your physical network devices—such as routers, switches, and load balancers—is the most fundamental way of protecting a network from a cyberattack. 

However, in the Siraugga framework, the structural "devices" on our network are not physical hardware components. Instead, the devices are the **AI Subagents** themselves. These autonomous logic nodes constantly spin up in the background, route prompt traffic, parse JSON state deltas, and gracefully collapse back into the void once their task is complete.

Because these subagents act as the dynamic infrastructure of the swarm, securing these "network devices" is absolutely paramount. If a single Tier 3 subagent is compromised via a sophisticated Prompt Injection, it can be weaponized to attack the core orchestration engine. 

In this chapter, we will explore the fundamental methods of securing, restricting, and sandboxing these agentic network devices to protect the Siraugga mainframe from collapse.
