# Chapter 9: The Agentic Facility (Power, HVAC, and Boundaries)

## 1. Agentic Power Systems (API Tokens)
A critical issue in protecting AI information systems is the management of computational "power"—specifically, the flow of LLM API Tokens. A continuous, uninterrupted supply of API tokens is absolutely essential for the DevCore swarm to function. 

Here are the general rules for building highly effective agentic power systems:
*   **Segmented Supplies:** The core orchestration engine (`server.py`) should utilize a completely isolated API Key (power supply) from the Tier 2 Modder subagents.
*   **Redundant Power Sources:** As established in Chapter 8, the orchestrator should maintain two or more fallback API providers (e.g., cloud-based or local open-source LLMs) in case the primary provider fails.
*   **Uninterruptible Token Supply (UPS):** A reserved, emergency buffer of API tokens (the UPS) must be maintained. If the primary billing quota is suddenly exhausted, the UPS provides just enough computational power for the subagents to gracefully save their JSON states and shut down without data loss.

**Power Events in the Swarm**
*   **Power Excess (Token Spikes/Surges):** A sudden, massive generative output from an AI that momentarily burns an excessive volume of tokens, potentially triggering a billing threshold.
*   **Power Loss (Faults/Blackouts):** A complete LLM API Outage. A blackout occurs when the external LLM provider goes completely offline, instantly halting all generative game logic.
*   **Power Degradation (Sags/Brownouts):** API Rate-Limiting. A prolonged brownout occurs when the provider artificially throttles the network, causing the AI's generation speed to "sag" and severely delaying JSON merging.

## 2. Generative HVAC (Temperature and Context Humidity)
In physical IT facilities, HVAC systems control ambient temperature, humidity, and airflow. In the Siraugga framework, these concepts translate perfectly to the AI's core generative parameters:
*   **Temperature:** Controls the mathematical randomness, hallucination rate, and creativity of the subagent. 
*   **Context Humidity:** Refers to how saturated the AI's context window is with dense, historical conversational data.
*   **Airflow:** The speed and network throughput of the localized message passing (Token Bandwidth).

**Overheating and Environmental Failures**
Just as physical server hardware has strict environmental requirements, generative AI has rigid parameter limits. If an Administrator sets a subagent's Temperature too high (e.g., `T=1.8`), the AI will rapidly "overheat," aggressively hallucinating and outputting pure gibberish, which immediately causes catastrophic syntax errors in the JSON Master State. Conversely, if the Context Humidity becomes too dense (too much conversation history), the AI suffocates and loses its ability to follow rigid logic instructions.

**The Danger of Third-Party Contractors**
Modern AI systems often connect to external third-party plugins (Contractors) for remote monitoring. However, allowing a third-party plugin to dynamically adjust a subagent's Generative Temperature introduces massive security risks. A malicious plugin can intentionally crank the temperature to force the overarching AI into an overheating hallucination loop, actively creating a chaotic vulnerability that allows for easier Prompt Injections.

## 3. Managing Threats to the Agentic Playground
Securing the Siraugga framework goes beyond network resilience; Administrators must actively secure the physical file boundaries of the localized `/playground`. Effective countermeasures include:
*   **CCTV and Access Control:** Implementing rigorous Orchestration Telemetry Logging (CCTV) to monitor all subagent tool calls, alongside strict IAM access controls.
*   **Guest Policies:** Enforcing rigid regex input validation for all "guests" (Tier 1 Players) who attempt to chat with dynamic NPCs.
*   **Badge Encryption:** Utilizing dynamically rotating JWTs (JSON Web Tokens) to strictly secure the WebSocket connections.
*   **Asset Tagging:** Assigning immutable UUIDs to every single JSON artifact or `wsl.exe` script the swarm generates.
*   **Disaster Recovery:** Utilizing the Semantic Git Checkpoints (established in Chapter 8) to instantly revert a corrupted workspace back to a clean, functional state.
