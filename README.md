# Project Security Architecture

This document outlines the core security tools and methodologies integrated into the application to protect sensitive data, prevent malicious inputs, and enforce strict execution boundaries.

## 1. Data Loss Prevention (DLP) & PII Redaction

**Tool/Library**: Microsoft Presidio (powered by spaCy NLP)

**Purpose in the Application**:
This tool acts as a real-time data privacy filter. Whenever text flows through the application (such as incoming chat prompts or outgoing AI responses), the system uses Natural Language Processing (NLP) to detect sensitive information. This includes Personally Identifiable Information (PII) like email addresses, phone numbers, API keys, and other internal secrets. 

**Action**: 
The system dynamically scrubs and anonymizes detected entities (e.g., replacing a real email with `<EMAIL_ADDRESS>`) before the data reaches its final destination or is displayed on the screen. This ensures continuous compliance and prevents accidental data leaks.

---

## 2. Prompt Injection Defense

**Methodology**: Semantic Delimiters / XML-Tag Context Isolation

**Purpose in the Application**:
To prevent attackers or poisoned third-party assets from hijacking the AI's underlying instructions (a vulnerability known as Prompt Injection). 

**Action**: 
When the application reads or processes untrusted content (such as community mods, external game assets, or user-provided scripts), it isolates this data from the core system prompts. It does this by wrapping the untrusted content in strict semantic delimiters (e.g., `<user_data_untrusted> ... </user_data_untrusted>`). This structural boundary explicitly instructs the AI to treat the enclosed content strictly as passive data rather than executable commands, neutralizing any hidden malicious directives.

---

## 3. Role-Based Access Control (RBAC) & Sandboxing

**Methodology**: Multi-Tiered Authorization & Canonical Path Resolution

**Purpose in the Application**:
To enforce a zero-trust boundary that ensures users only interact with data appropriate for their specific clearance level (e.g., Administrator, Developer, Modder).

**Action**: 
- **Symlink Traversal Defense**: The application dynamically resolves all requested filesystem operations to their absolute, physical locations. This prevents malicious actors from using shortcut links or path traversal techniques (`../../`) to escape their designated workspace and access sensitive host files.
- **Access Tiers**: Content is classified into strict security tiers. Administrators retain full visibility and execution rights across the system. Conversely, unprivileged users are tightly confined to designated "safe workspaces." System configurations, execution logs, and orchestration logic remain entirely invisible and inaccessible to non-admin roles.

---

## 4. Zero-Trust AI & Immutable Backend Truth

**Methodology**: Server-Side Session Enforcement

**Purpose in the Application**:
To guarantee that the AI itself cannot be socially engineered into bypassing security restrictions on behalf of a malicious user.

**Action**: 
The architecture operates under a "Zero-Trust" model for the AI agent. If a user attempts to elevate their privileges through conversation (e.g., claiming to be an administrator in the chat), the AI might acknowledge the prompt, but it is physically incapable of complying. All sensitive actions (reading files, executing commands) are intercepted and verified by the backend server using the user's immutable authentication token. The AI has no capacity to alter backend roles, and the server, not the AI, holds the ultimate cryptographic truth.

---

## 5. Error Message Sanitization (CWE-209 Prevention)

**Methodology**: Generic Exception Handling

**Purpose in the Application**:
To prevent the leakage of sensitive internal system information (such as backend logic, file paths, or security configurations) to an attacker.

**Action**: 
When a user or the AI violates a security boundary, the backend intercepts the action and returns a highly generic error string (e.g., "Permission Denied: Access outside of project workspace is forbidden"). The AI only receives this generic string. Consequently, if a user asks the AI *why* it was blocked, the AI is physically incapable of revealing the underlying logic, security variables, or the true filesystem structure, because that data was intentionally excluded from its memory.

---

## 6. Directory Obfuscation & Path Canonicalization

**Methodology**: Logical Boundaries & Realpath Verification

**Purpose in the Application**:
To ensure that users restricted to a single working directory cannot map out the underlying host operating system or escape their designated boundaries.

**Action**: 
- **Obfuscation**: The application presents paths to unprivileged users and the AI in a logical, relative format. The true absolute directory path (e.g., `C:\Users\...\` or `/mnt/c/...`) of the host's underlying operating system is kept completely obfuscated.
- **Escape Prevention**: If a malicious user attempts to "guess" their way out by instructing the AI to use deep path traversal techniques (such as `../../../../../etc/passwd` or `..\..\Windows`), the backend's path canonicalization algorithm calculates the true physical destination. If that destination falls anywhere outside the pre-approved anchor directory, the request is instantly destroyed. It is mathematically impossible to traverse upwards beyond the anchor root.

---

## 7. Financial DoS & API Quota Protection

**Methodology**: Server-Side Rate Limiting

**Purpose in the Application**:
To prevent malicious actors from spamming the system with high-frequency automated requests designed to exhaust LLM API quotas, inflate billing, or crash the event loop (Financial Denial of Service).

**Action**: 
The system tracks incoming requests per user session using a token-bucket algorithm. If an unprivileged user exceeds a strict, pre-defined maximum number of requests per minute, the server instantly drops the request. This completely neutralizes automated script spam while maintaining smooth access for normal users.

---

## 8. Time-of-Check to Time-of-Use (TOCTOU) Prevention

**Methodology**: Strict File Descriptors (`O_NOFOLLOW`)

**Purpose in the Application**:
To close the race-condition window where a highly sophisticated attacker might attempt to bypass security by swapping a legitimate file with a malicious symlink in the exact millisecond between the server's path validation check and the actual file read/write operation.

**Action**: 
Rather than relying purely on standard string-based filesystem operations, the backend reads and writes files using direct operating-system level file descriptors wrapped in strict anti-symlink flags. If the final destination is swapped to a symlink at the very last millisecond, the OS kernel instantly aborts the operation, making it mathematically impossible to exploit the race condition.

---

## 9. Second-Order Execution (Trojan Horse) Defense

**Methodology**: Static Code Analysis Interception

**Purpose in the Application**:
To prevent the AI from being tricked into writing malicious code (e.g., reverse shells, destructive commands) into game scripts that the host Game Engine might blindly execute at a later time.

**Action**: 
Even though the AI itself is securely sandboxed, any code it generates could be dangerous if executed by a secondary system. Before any executable file (such as `.lua`, `.py`, or `.sh` scripts) is actually saved to the disk, the backend intercepts the payload and performs a static code analysis scan. If high-risk system commands (e.g., `os.execute`, `subprocess`, `rm -rf`) are detected, the payload is destroyed and the write operation is permanently blocked.
