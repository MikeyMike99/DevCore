# Chapter 9: Embedded Subagents, the IoP, and Agentic Deception

To holistically understand the security needs of an organization like DevCore, Tier 5 Administrators must examine the broader infrastructure. Protecting specialized, embedded AI systems is central to protecting the overarching token economy and the integrity of the game framework. 

## 1. Threats to Core Engine Processes (Agentic SCADA)
In traditional hardware security, the infamous Stuxnet worm devastated Supervisory Control And Data Acquisition (SCADA) systems that governed industrial hardware. In the Siraugga framework, the equivalent is **Subagent Control and Data Acquisition (SCADA)**—the core internal architecture that governs how subagents execute `wsl.exe` tools and read local JSON data. 

When the Siraugga architecture was first developed, these core subagent controls were heavily sandboxed. However, modern Modders increasingly connect their Agentic SCADA networks to external APIs to improve data collection. To prevent devastating prompt-net worms from interrupting vital orchestration facilities, Administrators must rigidly segregate internal SCADA control networks from external plugin networks.

## 2. The Emergence of the IoP (Internet of Plugins)
Just as the traditional Internet of Things (IoT) connected billions of physical devices (smart TVs, appliances, and sensors), the DevCore architecture relies heavily on the **Internet of Plugins (IoP)**. 

Modders rapidly connect thousands of specialized third-party plugins (e.g., custom weapon APIs, dynamic weather systems, and unique NPCs) directly to their `/playground` workspaces. This exponential growth of interconnected plugins generates massive JSON datasets, creating an agentic equivalent of ‘Big Data.’ 

However, IoP plugins dramatically expand the cyber attack surface. Malicious internet-connected plugins have been used to launch some of the largest Semantic DoS attacks in the swarm's history. To secure the IoP, all plugins must be continuously evaluated for security patches, and default administrator API keys must always be rotated to prevent unauthorized access.

## 3. Embedded Subagents and Side-Channel Attacks
Embedded subagents are highly specialized, lightweight AI models hardcoded into specific, unalterable game mechanics. They are uniquely susceptible to **Side-Channel Attacks**, such as Timing Attacks. By aggressively measuring the exact milliseconds it takes an embedded agent to respond to different inputs, a malicious Modder can reverse-engineer the agent's hidden System Prompt without directly breaching the software.

**Special-Purpose Embedded Agents**
Embedded subagents are utilized across a variety of specific game sectors:
*   **Diagnostic Agents (The Medical Sector):** Highly privileged agents that monitor the overarching swarm's token health and memory logs. Vulnerabilities in these agents can lead to devastating leaks of the project's master configuration.
*   **Traversal Agents (The Automotive Sector):** Agents that control in-game physical movement, pathfinding, and geospatial logic. Risks include Modders actively spoofing JSON coordinates to illicitly teleport characters across the map.
*   **Overlord Agents (The Aviation Sector):** "Game Master" AIs (Drones) that fly above the game state, surveilling and managing the overarching narrative. These overarching agents are highly susceptible to deauthentication attacks and GPS spoofing, allowing an attacker to hijack the narrative drone and alter the storyline.

## 4. Agentic over IP (AoIP) Security
Where traditional remote teams use VoIP (Voice over IP) to communicate, distributed Siraugga subagents use **Agentic over IP (AoIP)** to transmit JSON payloads across WebSocket Secure (WSS) streams. 

AoIP is highly vulnerable. Cybercriminals target these streams to eavesdrop on unencrypted agent-to-agent logic or affect token availability. To protect AoIP, administrators must:
*   Encrypt all WSS message packets to prevent eavesdropping.
*   Use robust JWT authentication to mitigate *Call Hijacking* (a Modder intercepting agent-to-agent payloads and rerouting the JSON to a rogue proxy).
*   Implement Semantic Firewalls to aggressively filter abnormal conversational streams.

## 5. Deception Technologies
To proactively defend against highly sophisticated, zero-day prompt injections, Tier 5 Administrators utilize **Deception Technologies** to distract attackers away from the production network.

*   **Agentic Honeypots:** A dummy `/playground` workspace configured to mimic a highly privileged core server. It is purposefully left exposed with weak IAM permissions to lure malicious Modders. When an attacker attempts a prompt injection on the honeypot, the Orchestration Telemetry silently logs their exact methodology for later review. DevCore frequently creates entire *Honeynets* (collections of fake workspaces) to trap attackers.
*   **Semantic Sinkholes (DNS Sinkholes):** Fake API routing endpoints that quietly absorb and drop malicious JSON payloads without alerting the attacker that their injection failed. 
