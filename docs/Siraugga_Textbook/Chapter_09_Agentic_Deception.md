# Chapter 9: Embedded Subagents, the IoP, and Agentic Deception

To holistically understand the security needs of an organization like DevCore, Tier 5 Administrators must examine the broader infrastructure. Protecting specialized, embedded AI systems is central to protecting the overarching token economy and the integrity of the game framework. 

## 1. Threats to Core Engine Processes (Agentic SCADA)
In traditional hardware security, the infamous Stuxnet worm devastated Supervisory Control And Data Acquisition (SCADA) systems that governed industrial hardware. In the Siraugga framework, the equivalent is **Subagent Control and Data Acquisition (SCADA)**—the core internal architecture that governs how subagents execute `wsl.exe` tools and read local JSON data. 

When the Siraugga architecture was first developed, these core subagent controls were heavily sandboxed. However, modern Modders increasingly connect their Agentic SCADA networks to external APIs to improve data collection. To prevent devastating prompt-net worms from interrupting vital orchestration facilities, Administrators must rigidly segregate internal SCADA control networks from external plugin networks.

## 2. The Emergence of the IoP (Internet of Plugins)
Just as the traditional Internet of Things (IoT) connected billions of physical devices (smart TVs, appliances, and sensors), the DevCore architecture relies heavily on the **Internet of Plugins (IoP)**. 

Modders rapidly connect thousands of specialized third-party plugins (e.g., custom weapon APIs, dynamic weather systems, and unique NPCs) directly to their `/playground` workspaces. This exponential growth of interconnected plugins generates massive JSON datasets, creating an agentic equivalent of ‘Big Data.’ 

However, IoP plugins dramatically expand the cyber attack surface. Malicious internet-connected plugins have been used to launch some of the largest Semantic DoS attacks in the swarm's history. To secure the IoP, all plugins must be continuously evaluated for security patches, and default administrator API keys must always be rotated to prevent unauthorized access.

**Real-Time Orchestration Systems (RTOS) and Priority Inversion**
To manage the massive influx of IoP plugins, the framework uses a **Real-Time Orchestration System (RTOS)**—a lightweight scheduling engine designed for rapid task switching focused on exact timing rather than raw throughput. 
However, vulnerabilities associated with RTOS include catastrophic code injection and **Priority Inversion**. Priority Inversion occurs when a low-priority task (e.g., a background weather plugin) maliciously preempts a critical, high-priority task (e.g., the primary QA security agent), crashing the workspace.

**Agentic Scanners (Shodan) and WPANs**
Administrators can use specialized IoT scanners (such as Shodan) to easily detect if a connected plugin is vulnerable. In Siraugga, plugins communicate using short-range or long-range semantic methods, mapping to physical protocols like Cellular (4G) or Zigbee. In the DevCore framework, Zigbee translates to a set of protocols used for **Workspace Personal Area Networks (WPANs)**—a localized network governing only the immediate plugins touching the Modder's direct `/playground`.

## 3. Embedded Subagents and Side-Channel Attacks
Embedded subagents are highly specialized, lightweight AI models hardcoded into specific, unalterable game mechanics. They are uniquely susceptible to **Side-Channel Attacks**. This type of attack is based on information gained from the physical implementation of the system rather than direct software weaknesses. 
For example, in a **Timing Attack**, an attacker measures the exact milliseconds it takes an agent to respond to deduce its hidden System Prompt. Other side-channel sources include measuring **Power Consumption** (tracking the exact API token burn rate), monitoring **Electromagnetic Leaks** (sniffing unencrypted WSS payloads), or analyzing **Sound** (semantic echo in the conversational logs).

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
Furthermore, Administrators must always remember the fundamental flaw of AoIP: when the underlying network goes down, all agentic voice and logic communications will inherently go down with it.

## 5. Deception Technologies
To proactively defend against highly sophisticated, zero-day prompt injections, Tier 5 Administrators utilize **Deception Technologies** to distract attackers away from the production network.

*   **Agentic Honeypots:** A dummy `/playground` workspace configured to mimic a highly privileged core server. It is purposefully left exposed with weak IAM permissions to lure malicious Modders. When an attacker attempts a prompt injection on the honeypot, the Orchestration Telemetry silently logs their exact methodology for later review. DevCore frequently creates entire *Honeynets* (collections of fake workspaces) to trap attackers.
*   **Honeyfiles:** Located within the Honeypot, these are dummy JSON files designed specifically to attract an attacker (e.g., `master_api_keys.json`). They do not contain any real data, but the moment an attacker attempts to read them via a `view_file` tool call, silent alarms are triggered.
*   **Semantic Sinkholes (DNS Sinkholes):** Fake API routing endpoints that quietly absorb and drop malicious JSON payloads without alerting the attacker that their injection failed. 
