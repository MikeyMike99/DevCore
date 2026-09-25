# Architecture Decision Record: Master Auto-Detect & Portable Security

## Context
As the DevCore platform transitions into a distributable, standalone executable (compiled via Nuitka), it requires a robust authentication system. The goal is to allow the application to be securely distributed to clients (running in a restricted/trial mode) while guaranteeing that the original developer is **never** locked out or forced to authenticate when running the application on their own personal machine.

## Decision
We implemented a **Cryptographic Master Signature Auto-Detect** system. Instead of relying on vulnerable environment variables or easily spoofed usernames, the application authenticates the host environment mathematically.

## Implementation Details
1. **The Raw Key (Local Only):** 
   A highly secure, 32-byte randomized cryptographic string was generated and saved to a hidden file named `.devcore_master.key` in the root of the DevCore folder.
2. **Version Control Protection:**
   This file was explicitly added to `.gitignore`. It is treated with the same severity as a GitHub Token or AWS Secret Key and will never be pushed to a remote repository.
3. **One-Way Hash Verification:**
   Inside `security_manager.py`, the `check_master_signature()` method reads this file at boot. However, the raw string is **not** stored in the source code. Instead, the application computes the SHA-256 hash of the local file's contents and compares it to a hardcoded Expected Hash.

## Security Advantages
- **Reverse-Engineering Proof:** Because Nuitka compiles Python to C, it is possible for a dedicated hacker to rip open the `.exe` and read the internal strings. If they do this, they will only discover the SHA-256 hash, not the raw key. Because SHA-256 is a one-way mathematical function, it is physically impossible for the attacker to reverse the hash and forge their own `.devcore_master.key` file.
- **Frictionless Developer Experience (Zero-Touch):** On the host machine, the application will silently detect the key, verify the hash, and grant Master Admin privileges instantly without ever displaying a login screen.
- **Seamless Client Distribution:** When the `.exe` is distributed to a client, it will check for the signature file, fail to find it, and gracefully fall back to the restricted Client/Trial mode, prompting them for their own API keys and tokens.
