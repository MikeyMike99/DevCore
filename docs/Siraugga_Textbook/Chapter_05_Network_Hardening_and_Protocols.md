# Chapter 5: Network Hardening (Services and Protocols)

## 1. Introduction to Network Hardening
Network vulnerabilities will leave the DevCore mainframe open to catastrophic attacks, potentially exposing the organization, Tier 3 Developers, and Tier 1 End Users to massive data breaches. 

In a traditional IT environment, network hardening involves securing standard ports and protocols. However, in the Siraugga framework—where the infrastructure is governed by autonomous AI agents communicating over real-time event streams—it is critical to aggressively harden the perimeter to reduce the agentic attack surface. 

First up, it’s all about securing Zero-Restart WebSocket services and cryptographic transmission protocols to ensure that no rogue AI can traverse the network boundary.


## 2. Network and Routing Services
Cybercriminals and malicious AI agents use vulnerable network services to attack a server or hijack an offline sandbox to use as part of a coordinated swarm attack. 

In a traditional IT environment, administrators and attackers alike use port scanners to detect open ports on a device. A port scanner sends a message to each port and waits for a response, revealing the network topology and potential entry points. In the Siraugga framework, an advanced threat actor might deploy an **Agentic Port Scanner**—a specialized AI subagent instructed to aggressively probe the host's network interfaces, searching for an exposed protocol or an unprotected backend service.

Because Siraugga's core architecture relies entirely on the Zero-Restart Web Portal (typically running a Quart HTTP/WebSocket server on Port 5000), securing these routing services is paramount. Securing the network ensures that Port 5000 is the *only* necessary port exposed to the swarm. 

Every other system port must be violently locked down by the host firewall. This aggressive port restriction mathematically prevents a compromised Tier 3 offline `.exe` sandbox from establishing a rogue reverse-shell or communicating with external command-and-control (C2) servers, forcing all traffic to flow exclusively through the heavily audited WebSocket layer.