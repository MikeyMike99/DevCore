# Chapter 5: Network Hardening (Services and Protocols)

## 1. Introduction to Network Hardening
Network vulnerabilities will leave the DevCore mainframe open to catastrophic attacks, potentially exposing the organization, Tier 3 Developers, and Tier 1 End Users to massive data breaches. 

In a traditional IT environment, network hardening involves securing standard ports and protocols. However, in the Siraugga framework—where the infrastructure is governed by autonomous AI agents communicating over real-time event streams—it is critical to aggressively harden the perimeter to reduce the agentic attack surface. 

First up, it’s all about securing Zero-Restart WebSocket services and cryptographic transmission protocols to ensure that no rogue AI can traverse the network boundary.


## 2. Network and Routing Services
Cybercriminals and malicious AI agents use vulnerable network services to attack a server or hijack an offline sandbox to use as part of a coordinated swarm attack. 

In a traditional IT environment, attackers use network port scanners to detect open vulnerabilities on a device. However, in the localized AI environment of the Siraugga framework, **files and folders serve as our logical "ports"**. 

An advanced threat actor will deploy an **Agentic Port Scanner**—a specialized AI subagent instructed to aggressively probe the host's directory structure (using path traversal techniques), searching for exposed folders or unprotected backend script files. 

Because Siraugga's core architecture relies entirely on the Zero-Restart Web Portal, securing these directory "ports" is paramount. Securing the environment ensures that only the strictly necessary project folders (the `TIER_SAFE_WORKSPACE`) are exposed to the swarm. Every other system folder—especially those containing environment variables or hidden `.git` directories—must be violently locked down by the OS-level firewall. This aggressive folder restriction mathematically prevents a compromised Tier 3 offline `.exe` from probing outside its sandbox.

## 3. Dynamic Host Configuration Protocol (Workspace Provisioning)
In standard networking, Dynamic Host Configuration Protocol (DHCP) uses a server to assign an IP address and configuration data to devices. In effect, the device gets a "permission slip" from the DHCP server to use the network. 

In the Siraugga framework, DHCP translates to **Workspace Provisioning**. When a Tier 2 Modder connects to the web portal, the `project_manager.py` (acting as the DHCP server) assigns them a localized game project folder (their IP address) and strictly confines them to that directory. 

Attackers can target the Workspace Provisioning module to deny access to legitimate developers, or attempt to spawn a "rogue DHCP server" (an unauthorized AI agent assigning itself malicious directory paths). To prevent this, Siraugga utilizes **Path Snooping** (the equivalent of DHCP snooping), where the Raugus Resolver continuously validates that all workspace creation messages originate strictly from the trusted `project_manager.py` core file.

**A Security Checklist for Workspace Provisioning (DHCP):**
* **Physically secure the Provisioning Server:** Ensure `project_manager.py` is locked within the `TIER_CORE_ENGINE` classification, inaccessible to Modders.
* **Apply any software patches:** Utilize the Zero-Restart in-memory reload API to hot-patch provisioning logic.
* **Locate the server behind a firewall:** Protect the workspace logic behind the Semantic Firewall to block prompt injections.
* **Monitor provisioning activity:** Continuously review the Tier 5 Admin logs for anomalous folder creation.
* **Uninstall unused services:** Strip deprecated AI subagents and dead code from the SDK Baseline.
* **Close unused ports:** Aggressively lock down and delete any unused or abandoned project folders to reduce the attack surface.