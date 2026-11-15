(function () {
    'use strict';

    const PBKDF2_ITERATIONS = 600000;
    const MRSV_MAGIC = new Uint8Array([0x4d, 0x52, 0x53, 0x56, 0x01, 0x02, 0x03, 0x04]);
    const MRSV_SEP = '||X_SHI3LD_X||';
    const enc = new TextEncoder();
    const dec = new TextDecoder();

    const zkSession = {
        active: false,
        workspaceId: '',
        alias: '',
        method: 'password',
        authB64: '',
        revision: 0,
        keyVersion: 1,
        dek: null,
        privateKeyJwk: null,
        publicKeyRawB64: '',
        members: [],
        lastEnvArtifacts: null
    };

    function bytesToB64(bytes) {
        let bin = '';
        const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
        for (let i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
        return btoa(bin);
    }

    function b64ToBytes(b64) {
        const clean = String(b64 || '').replace(/-/g, '+').replace(/_/g, '/');
        const pad = clean + '='.repeat((4 - (clean.length % 4)) % 4);
        const bin = atob(pad);
        const out = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
        return out;
    }

    function randBytes(n) {
        const b = new Uint8Array(n);
        window.crypto.getRandomValues(b);
        return b;
    }

    function generateUnlockKey() {
        const words = [
            'shield', 'nomvula', 'bicep', 'popia', 'vault', 'canary', 'cobalt', 'cipher',
            'quorum', 'ledger', 'bastion', 'argon', 'vector', 'granite', 'harbor', 'zenith',
            'anchor', 'prism', 'ember', 'falcon', 'solace', 'matrix', 'vortex', 'sierra'
        ];
        const picks = [];
        const rnd = randBytes(12);
        for (let i = 0; i < 8; i++) {
            const w = words[rnd[i] % words.length];
            const num = String(rnd[(i + 4) % 12]).padStart(2, '0');
            picks.push(`${w}-${num}`);
        }
        return 'SHI3LD-' + picks.join('-');
    }

    async function deriveKekAndAuth(secretStr, saltBytes, iterations) {
        const baseKey = await window.crypto.subtle.importKey(
            'raw', enc.encode(secretStr), 'PBKDF2', false, ['deriveBits']
        );
        const bits = await window.crypto.subtle.deriveBits(
            { name: 'PBKDF2', salt: saltBytes, iterations: iterations || PBKDF2_ITERATIONS, hash: 'SHA-256' },
            baseKey, 512
        );
        const all = new Uint8Array(bits);
        const kekRaw = all.slice(0, 32);
        const authRaw = all.slice(32, 64);
        const kek = await window.crypto.subtle.importKey(
            'raw', kekRaw, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']
        );
        return { kek, authB64: bytesToB64(authRaw) };
    }

    async function aesGcmEncrypt(key, plainBytes) {
        const iv = randBytes(12);
        const ct = await window.crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, plainBytes);
        return { iv: bytesToB64(iv), ct: bytesToB64(new Uint8Array(ct)) };
    }

    async function aesGcmDecrypt(key, box) {
        const iv = b64ToBytes(box.iv);
        const ct = b64ToBytes(box.ct);
        const pt = await window.crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct);
        return new Uint8Array(pt);
    }

    async function generateMemberEcdh() {
        const kp = await window.crypto.subtle.generateKey(
            { name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveKey', 'deriveBits']
        );
        const pubRaw = await window.crypto.subtle.exportKey('raw', kp.publicKey);
        const privJwk = await window.crypto.subtle.exportKey('jwk', kp.privateKey);
        return { publicKeyRawB64: bytesToB64(pubRaw), privateKeyJwk: privJwk };
    }

    async function wrapDekForMemberPublic(dekRawBytes, memberPubRawB64, keyVersion) {
        const recipPub = await window.crypto.subtle.importKey(
            'raw', b64ToBytes(memberPubRawB64), { name: 'ECDH', namedCurve: 'P-256' }, false, []
        );
        const eph = await window.crypto.subtle.generateKey(
            { name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveKey']
        );
        const epkRaw = await window.crypto.subtle.exportKey('raw', eph.publicKey);
        const wrapKey = await window.crypto.subtle.deriveKey(
            { name: 'ECDH', public: recipPub }, eph.privateKey,
            { name: 'AES-GCM', length: 256 }, false, ['encrypt']
        );
        const box = await aesGcmEncrypt(wrapKey, dekRawBytes);
        return { key_version: keyVersion, epk: bytesToB64(epkRaw), iv: box.iv, ct: box.ct };
    }

    async function unwrapDekWithMemberPrivate(keyWrap, privJwk) {
        const privKey = await window.crypto.subtle.importKey(
            'jwk', privJwk, { name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveKey']
        );
        const epk = await window.crypto.subtle.importKey(
            'raw', b64ToBytes(keyWrap.epk), { name: 'ECDH', namedCurve: 'P-256' }, false, []
        );
        const wrapKey = await window.crypto.subtle.deriveKey(
            { name: 'ECDH', public: epk }, privKey,
            { name: 'AES-GCM', length: 256 }, false, ['decrypt']
        );
        const dekRaw = await aesGcmDecrypt(wrapKey, keyWrap);
        const dekKey = await window.crypto.subtle.importKey(
            'raw', dekRaw, { name: 'AES-GCM' }, true, ['encrypt', 'decrypt']
        );
        return { dekRaw, dekKey };
    }

    function getMergedRequirements() {
        if (!progressState.step_requirements || typeof progressState.step_requirements !== 'object') {
            progressState.step_requirements = {};
        }
        const merged = {
            venv_name: 'alp-env',
            python_version: '3.14.4',
            host_platform: 'WSL2 Ubuntu on Windows',
            extra_packages: 'pip-tools==7.6.2',
            vm_hypervisor: 'WSL2 Lightweight Utility VM',
            vm_guest_os: 'ubuntu/noble64 (Ubuntu 24.04 LTS)',
            vm_cpus: '2',
            vm_ram_mb: '4096',
            vm_disk_gb: '32',
            vm_network_mode: 'NAT + Host-Only Private Network',
            vm_cli_tools: 'bicep, az, git, jq, curl',
            project_title: 'NomvulaAgriFinance',
            mod1_audit_tag: 'phase2-mod1-verified',
            org_prefix: 'nomvula',
            default_env: 'dev',
            mod2_rec_target: 'mod2_task2_parameters',
            azure_location: 'southafricanorth',
            storage_account_name: 'stnomvulafica001',
            storage_sku: 'Standard_GRS',
            storage_regulation: 'POPIA Section 19 (South Africa)',
            vnet_cidr: '10.10.0.0/16',
            web_subnet_cidr: '10.10.1.0/24',
            app_subnet_cidr: '10.10.2.0/24',
            data_subnet_cidr: '10.10.3.0/24',
            nsg_posture: 'Zero-Trust Deny-By-Default (Explicit Allow Only)',
            keyvault_name: 'kv-nomvula-fica-01',
            siem_retention_days: '90',
            landing_zone_bicep: 'architecture/landing-zone.bicep',
            checkov_framework: 'arm',
            checkov_mode: '--compact --quiet',
            ca_policy_file: 'architecture/conditional-access.json',
            mfa_grant_control: 'mfa + compliantDevice (Phishing-Resistant)',
            doc_preview_lines: '35',
            compliance_frameworks: 'ISO 27001:2022, NIST CSF 2.0, POPIA Section 19',
            mermaid_file: 'architecture/architecture.mmd',
            package_release_tag: 'alp-phase2-v1.0-verified'
        };
        Object.values(progressState.step_requirements).forEach((stepAns) => {
            if (stepAns && typeof stepAns === 'object') {
                Object.entries(stepAns).forEach(([k, v]) => {
                    if (k !== '_confirmed' && v != null && String(v).trim() !== '') {
                        merged[k] = String(v).trim();
                    }
                });
            }
        });
        return merged;
    }

    function interpolateTemplate(str, vars) {
        if (!str || typeof str !== 'string') return str || '';
        return str.replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, (_, key) => {
            return vars[key] != null ? vars[key] : `{{${key}}}`;
        });
    }

    function applyStepTailoring(sec) {
        if (!sec) return;
        const vars = getMergedRequirements();
        if (!sec._orig_code_snippet) sec._orig_code_snippet = sec.code_snippet || '';
        if (!sec._orig_starter_code) sec._orig_starter_code = sec.starter_code || '';
        if (!sec._orig_expected_command) sec._orig_expected_command = sec.expected_command || '';
        if (!sec._orig_task_prompt) sec._orig_task_prompt = sec.task_prompt || '';

        const tplSnippet = sec.template_code_snippet || sec._orig_code_snippet;
        const tplStarter = sec.template_starter_code || sec._orig_starter_code;
        const tplCmd = sec.template_expected_command || sec._orig_expected_command;

        sec.code_snippet = interpolateTemplate(tplSnippet, vars);
        if (tplStarter) sec.starter_code = interpolateTemplate(tplStarter, vars);
        if (tplCmd) sec.expected_command = interpolateTemplate(tplCmd, vars);
        sec.task_prompt = interpolateTemplate(sec._orig_task_prompt, vars);
    }

    async function syncEncryptedWorkspaceSave() {
        if (!zkSession.active || !zkSession.dek) return;
        const plainPayload = JSON.stringify({
            progressState,
            savedAt: new Date().toISOString(),
            savedBy: zkSession.alias
        });
        const box = await aesGcmEncrypt(zkSession.dek, enc.encode(plainPayload));
        const res = await fetch('/api/course/workspace/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                workspace_id: zkSession.workspaceId,
                alias: zkSession.alias,
                method: zkSession.method,
                auth: zkSession.authB64,
                base_revision: zkSession.revision,
                blob: { key_version: zkSession.keyVersion, iv: box.iv, ct: box.ct }
            })
        });
        const data = await res.json();
        if (data.ok) {
            zkSession.revision = data.revision;
            updateZkBanner();
        }
    }

    function injectTopEncryptedWorkspaceCard() {
        if (document.getElementById('zk-workspace-card')) return;
        const nav = document.querySelector('nav[aria-label="Course Module and Section Navigation"]');
        if (!nav) return;

        const section = document.createElement('section');
        section.id = 'zk-workspace-card';
        section.setAttribute('aria-labelledby', 'zk-heading');
        section.className = 'bg-slate-900 border-2 border-indigo-600/80 rounded-xl p-4 md:p-5 shadow-lg space-y-3';
        section.innerHTML = `
            <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <span class="text-xs font-mono uppercase px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-700">Zero-Knowledge Pair &amp; Group Encryption • MRSV ||X_SHI3LD_X|| .vault</span>
                    <h2 id="zk-heading" class="text-base md:text-lg font-bold text-indigo-300 mt-1">Encrypted Pair/Group Package Workspace (Client-Side Keys Only)</h2>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                    <span id="zk-status-badge" class="text-xs font-mono px-2.5 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700">Mode: Local Unencrypted</span>
                    <button id="zk-toggle-btn" type="button" class="text-xs bg-indigo-700 hover:bg-indigo-600 text-white font-bold px-3 py-1.5 rounded focus:outline-none focus:ring-2 focus:ring-indigo-300">
                        Open Pair &amp; Encryption Controls
                    </button>
                </div>
            </div>
            <p class="text-xs text-slate-300 leading-relaxed">
                Work solo or in pairs on the same course package. Your password and one-time <strong>Unlock / Recovery Key</strong> derive AES-256-GCM &amp; ECDH P-256 keys strictly inside your browser (<code class="text-indigo-300">PBKDF2-SHA256 600,000 iterations</code>). The server never receives your password, Unlock Key, or plaintext work—even the server administrator cannot read your work or reset a lost key if both your password and Unlock Key are lost.
            </p>
            <div id="zk-controls-body" class="hidden pt-2 border-t border-slate-800 space-y-4">
                <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                    <div class="bg-slate-950 border border-slate-800 rounded-lg p-3 space-y-2">
                        <h3 class="font-bold text-cyan-300 text-sm">A. Create Encrypted Pair/Group Package</h3>
                        <label class="block text-slate-300">Your Member Alias (lowercase):
                            <input id="zk-create-alias" type="text" value="michael" class="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100 font-mono" />
                        </label>
                        <label class="block text-slate-300">Set Workspace Password (client-only):
                            <input id="zk-create-pass" type="password" placeholder="Minimum 8 characters" class="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100 font-mono" />
                        </label>
                        <button id="zk-create-btn" type="button" class="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-1.5 px-3 rounded">
                            Create Encrypted Workspace &amp; Generate Unlock Key
                        </button>
                    </div>

                    <div class="bg-slate-950 border border-slate-800 rounded-lg p-3 space-y-2">
                        <h3 class="font-bold text-teal-300 text-sm">B. Unlock Workspace (Password or Unlock Key)</h3>
                        <label class="block text-slate-300">Workspace ID:
                            <input id="zk-unlock-wsid" type="text" placeholder="Paste Workspace ID" class="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100 font-mono" />
                        </label>
                        <label class="block text-slate-300">Your Member Alias:
                            <input id="zk-unlock-alias" type="text" value="michael" class="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100 font-mono" />
                        </label>
                        <label class="block text-slate-300">Unlock Method:
                            <select id="zk-unlock-method" class="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100">
                                <option value="password">Password</option>
                                <option value="recovery">Forgotten Password — Use One-Time Unlock Key</option>
                            </select>
                        </label>
                        <label class="block text-slate-300">Password or SHI3LD Unlock Key:
                            <input id="zk-unlock-secret" type="password" placeholder="Never sent to server" class="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100 font-mono" />
                        </label>
                        <button id="zk-unlock-btn" type="button" class="w-full bg-teal-600 hover:bg-teal-500 text-white font-bold py-1.5 px-3 rounded">
                            Decrypt &amp; Load Shared Package
                        </button>
                    </div>

                    <div class="bg-slate-950 border border-slate-800 rounded-lg p-3 space-y-2">
                        <h3 class="font-bold text-amber-300 text-sm">C. Pair Collaboration (Invite / Join / .vault)</h3>
                        <button id="zk-invite-btn" type="button" class="w-full bg-amber-600 hover:bg-amber-500 text-black font-bold py-1.5 px-3 rounded">
                            Generate Partner Invite Code
                        </button>
                        <div class="pt-1 border-t border-slate-800 space-y-1.5">
                            <input id="zk-join-wsid" type="text" placeholder="Partner Workspace ID" class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100 font-mono" />
                            <input id="zk-join-code" type="text" placeholder="Partner Invite Code (inviteId.secret)" class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100 font-mono" />
                            <input id="zk-join-alias" type="text" placeholder="Your Partner Alias (e.g. partner2)" class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100 font-mono" />
                            <input id="zk-join-pass" type="password" placeholder="Set Your Partner Password" class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100 font-mono" />
                            <button id="zk-join-btn" type="button" class="w-full bg-emerald-700 hover:bg-emerald-600 text-white font-bold py-1.5 px-3 rounded">
                                Join Partner Workspace
                            </button>
                        </div>
                        <div class="pt-1 border-t border-slate-800 flex gap-2">
                            <button id="zk-export-vault-btn" type="button" class="flex-1 bg-slate-800 hover:bg-slate-700 text-indigo-300 border border-indigo-700 py-1 px-2 rounded font-semibold">
                                Export .vault
                            </button>
                            <button id="zk-sync-btn" type="button" class="flex-1 bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-cyan-700 py-1 px-2 rounded font-semibold">
                                Sync Pair State
                            </button>
                        </div>
                    </div>
                </div>

                <div id="zk-recovery-modal" class="hidden bg-amber-950/60 border-2 border-amber-500 rounded-lg p-3.5 space-y-2 text-xs">
                    <div class="font-bold text-amber-300 text-sm">SAVE YOUR ONE-TIME UNLOCK / RECOVERY KEY NOW (SHOWN ONCE — NEVER SENT TO SERVER)</div>
                    <p class="text-slate-200">If you forget your password, this Unlock Key is the ONLY way to decrypt your work and set a new password. The server administrator never sees this key and cannot recover your work if you lose both.</p>
                    <pre id="zk-recovery-display" class="bg-black text-emerald-300 p-2.5 rounded border border-amber-600 font-mono text-xs select-all overflow-x-auto"></pre>
                    <div class="flex flex-wrap gap-2">
                        <button id="zk-copy-recovery-btn" type="button" class="bg-amber-500 hover:bg-amber-400 text-black font-bold px-3 py-1 rounded">Copy Unlock Key</button>
                        <button id="zk-hide-recovery-btn" type="button" class="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1 rounded border border-slate-600">I Saved It Offline — Hide</button>
                    </div>
                </div>

                <div id="zk-reset-pw-panel" class="hidden bg-teal-950/50 border border-teal-600 rounded-lg p-3 flex flex-wrap items-center gap-2 text-xs">
                    <span class="font-bold text-teal-300">Unlocked with Recovery Key! Set a New Password:</span>
                    <input id="zk-new-password-inp" type="password" placeholder="New password (min 8 chars)" class="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-slate-100 font-mono" />
                    <button id="zk-save-new-pw-btn" type="button" class="bg-teal-600 hover:bg-teal-500 text-white font-bold px-3 py-1 rounded">Update Password (Zero-Knowledge)</button>
                </div>

                <p id="zk-feedback-status" role="status" class="text-xs font-mono text-indigo-300"></p>
            </div>
        `;
        nav.insertAdjacentElement('beforebegin', section);

        document.getElementById('zk-toggle-btn').addEventListener('click', () => {
            const body = document.getElementById('zk-controls-body');
            body.classList.toggle('hidden');
        });

        document.getElementById('zk-copy-recovery-btn').addEventListener('click', () => {
            const txt = document.getElementById('zk-recovery-display').innerText;
            navigator.clipboard.writeText(txt).then(() => announce('One-time Unlock Key copied to clipboard.'));
        });

        document.getElementById('zk-hide-recovery-btn').addEventListener('click', () => {
            document.getElementById('zk-recovery-modal').classList.add('hidden');
        });

        document.getElementById('zk-create-btn').addEventListener('click', handleCreateWorkspace);
        document.getElementById('zk-unlock-btn').addEventListener('click', handleUnlockWorkspace);
        document.getElementById('zk-invite-btn').addEventListener('click', handleCreateInvite);
        document.getElementById('zk-join-btn').addEventListener('click', handleJoinWorkspace);
        document.getElementById('zk-sync-btn').addEventListener('click', handleSyncWorkspace);
        document.getElementById('zk-export-vault-btn').addEventListener('click', handleExportMrsvVault);
        document.getElementById('zk-save-new-pw-btn').addEventListener('click', handleResetPasswordWithRecovery);
    }

    function setZkStatus(msg, isError) {
        const el = document.getElementById('zk-feedback-status');
        if (el) {
            el.className = isError ? 'text-xs font-mono text-rose-300' : 'text-xs font-mono text-emerald-300';
            el.textContent = msg;
        }
        announce(msg);
    }

    function updateZkBanner() {
        const badge = document.getElementById('zk-status-badge');
        if (!badge) return;
        if (zkSession.active) {
            const memList = (zkSession.members || []).map(m => m.alias).join(', ') || zkSession.alias;
            badge.textContent = `E2EE Workspace: ${zkSession.workspaceId} • Members: ${memList} (Rev ${zkSession.revision})`;
            badge.className = 'text-xs font-mono px-2.5 py-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-700';
        }
    }

    async function buildMemberRegistration(alias, password, dekRawBytes, keyVersion) {
        const { publicKeyRawB64, privateKeyJwk } = await generateMemberEcdh();
        const privBytes = enc.encode(JSON.stringify(privateKeyJwk));

        const pwSalt = randBytes(16);
        const pwDerived = await deriveKekAndAuth(password, pwSalt, PBKDF2_ITERATIONS);
        const pwEncPriv = await aesGcmEncrypt(pwDerived.kek, privBytes);

        const unlockKey = generateUnlockKey();
        const recSalt = randBytes(16);
        const recDerived = await deriveKekAndAuth(unlockKey, recSalt, PBKDF2_ITERATIONS);
        const recEncPriv = await aesGcmEncrypt(recDerived.kek, privBytes);

        const keyWrap = await wrapDekForMemberPublic(dekRawBytes, publicKeyRawB64, keyVersion);

        return {
            unlockKey,
            privateKeyJwk,
            publicKeyRawB64,
            pwAuthB64: pwDerived.authB64,
            memberPayload: {
                alias,
                public_key: publicKeyRawB64,
                pw: {
                    salt: bytesToB64(pwSalt),
                    iterations: PBKDF2_ITERATIONS,
                    auth: pwDerived.authB64,
                    enc_private: pwEncPriv
                },
                rec: {
                    salt: bytesToB64(recSalt),
                    auth: recDerived.authB64,
                    enc_private: recEncPriv
                },
                key_wrap: keyWrap
            }
        };
    }

    async function handleCreateWorkspace() {
        try {
            const alias = (document.getElementById('zk-create-alias').value || '').trim().toLowerCase();
            const pass = document.getElementById('zk-create-pass').value || '';
            if (pass.length < 8) {
                setZkStatus('Password must be at least 8 characters.', true);
                return;
            }
            setZkStatus('Deriving client-side keys (PBKDF2 600,000 iterations + AES-256-GCM)...', false);
            const dekRaw = randBytes(32);
            const dekKey = await window.crypto.subtle.importKey('raw', dekRaw, { name: 'AES-GCM' }, true, ['encrypt', 'decrypt']);
            const reg = await buildMemberRegistration(alias, pass, dekRaw, 1);

            const blobBox = await aesGcmEncrypt(dekKey, enc.encode(JSON.stringify({
                progressState,
                savedAt: new Date().toISOString(),
                savedBy: alias
            })));

            const res = await fetch('/api/course/workspace/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    course_id: courseId,
                    member: reg.memberPayload,
                    blob: { key_version: 1, iv: blobBox.iv, ct: blobBox.ct }
                })
            });
            const data = await res.json();
            if (!data.ok) {
                setZkStatus(data.error || 'Failed to create encrypted workspace', true);
                return;
            }
            zkSession.active = true;
            zkSession.workspaceId = data.workspace_id;
            zkSession.alias = alias;
            zkSession.method = 'password';
            zkSession.authB64 = reg.pwAuthB64;
            zkSession.revision = data.revision;
            zkSession.keyVersion = data.key_version;
            zkSession.dek = dekKey;
            zkSession.privateKeyJwk = reg.privateKeyJwk;
            zkSession.publicKeyRawB64 = reg.publicKeyRawB64;
            zkSession.members = [{ alias, public_key: reg.publicKeyRawB64 }];
            progressState.encrypted_workspace_id = data.workspace_id;
            document.getElementById('zk-unlock-wsid').value = data.workspace_id;

            const recModal = document.getElementById('zk-recovery-modal');
            document.getElementById('zk-recovery-display').textContent =
                `Workspace ID : ${data.workspace_id}\nMember Alias : ${alias}\nUnlock Key   : ${reg.unlockKey}`;
            recModal.classList.remove('hidden');
            document.getElementById('zk-create-pass').value = '';
            updateZkBanner();
            setZkStatus(`Encrypted workspace ${data.workspace_id} created! Save your one-time Unlock Key above.`, false);
        } catch (err) {
            setZkStatus('Encryption error: ' + err.message, true);
        }
    }

    async function handleUnlockWorkspace() {
        try {
            const wsId = (document.getElementById('zk-unlock-wsid').value || '').trim();
            const alias = (document.getElementById('zk-unlock-alias').value || '').trim().toLowerCase();
            const method = document.getElementById('zk-unlock-method').value;
            const secret = document.getElementById('zk-unlock-secret').value || '';
            if (!wsId || !alias || !secret) {
                setZkStatus('Enter Workspace ID, alias, and your password or Unlock Key.', true);
                return;
            }
            const preRes = await fetch('/api/course/workspace/prelogin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ workspace_id: wsId, alias, method })
            });
            const pre = await preRes.json();
            if (!pre.ok) {
                setZkStatus(pre.error || 'Prelogin failed', true);
                return;
            }
            const derived = await deriveKekAndAuth(secret, b64ToBytes(pre.salt), pre.iterations);
            const unlRes = await fetch('/api/course/workspace/unlock', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ workspace_id: wsId, alias, method, auth: derived.authB64 })
            });
            const unl = await unlRes.json();
            if (!unl.ok) {
                setZkStatus(unl.error || 'Unlock failed', true);
                return;
            }
            const privBytes = await aesGcmDecrypt(derived.kek, unl.enc_private);
            const privJwk = JSON.parse(dec.decode(privBytes));
            const { dekKey } = await unwrapDekWithMemberPrivate(unl.key_wrap, privJwk);
            const plainBytes = await aesGcmDecrypt(dekKey, unl.blob);
            const parsed = JSON.parse(dec.decode(plainBytes));
            if (parsed && parsed.progressState) {
                progressState = Object.assign(progressState, parsed.progressState);
                progressState.encrypted_workspace_id = wsId;
            }
            zkSession.active = true;
            zkSession.workspaceId = wsId;
            zkSession.alias = alias;
            zkSession.method = method;
            zkSession.authB64 = derived.authB64;
            zkSession.revision = unl.revision;
            zkSession.keyVersion = unl.key_version;
            zkSession.dek = dekKey;
            zkSession.privateKeyJwk = privJwk;
            zkSession.publicKeyRawB64 = unl.public_key;
            zkSession.members = unl.members || [];

            document.getElementById('zk-unlock-secret').value = '';
            const resetPanel = document.getElementById('zk-reset-pw-panel');
            if (method === 'recovery') {
                resetPanel.classList.remove('hidden');
            } else {
                resetPanel.classList.add('hidden');
            }
            updateZkBanner();
            renderStepperOptions();
            renderCurrentStep(false);
            setZkStatus(`Unlocked shared workspace ${wsId} as ${alias} (Revision ${unl.revision}).`, false);
        } catch (err) {
            setZkStatus('Decryption failed — check your password or Unlock Key.', true);
        }
    }

    async function handleResetPasswordWithRecovery() {
        try {
            const newPass = document.getElementById('zk-new-password-inp').value || '';
            if (newPass.length < 8) {
                setZkStatus('New password must be at least 8 characters.', true);
                return;
            }
            const privBytes = enc.encode(JSON.stringify(zkSession.privateKeyJwk));
            const pwSalt = randBytes(16);
            const pwDerived = await deriveKekAndAuth(newPass, pwSalt, PBKDF2_ITERATIONS);
            const pwEncPriv = await aesGcmEncrypt(pwDerived.kek, privBytes);

            const res = await fetch('/api/course/workspace/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    workspace_id: zkSession.workspaceId,
                    alias: zkSession.alias,
                    method: zkSession.method,
                    auth: zkSession.authB64,
                    new_pw: {
                        salt: bytesToB64(pwSalt),
                        iterations: PBKDF2_ITERATIONS,
                        auth: pwDerived.authB64,
                        enc_private: pwEncPriv
                    }
                })
            });
            const data = await res.json();
            if (!data.ok) {
                setZkStatus(data.error || 'Could not update password', true);
                return;
            }
            zkSession.method = 'password';
            zkSession.authB64 = pwDerived.authB64;
            document.getElementById('zk-new-password-inp').value = '';
            document.getElementById('zk-reset-pw-panel').classList.add('hidden');
            setZkStatus('Password updated in zero-knowledge mode! Your new password is active.', false);
        } catch (err) {
            setZkStatus('Failed to update password: ' + err.message, true);
        }
    }

    async function handleCreateInvite() {
        if (!zkSession.active || !zkSession.dek) {
            setZkStatus('Create or unlock an encrypted workspace first before inviting a partner.', true);
            return;
        }
        try {
            const dekRaw = new Uint8Array(await window.crypto.subtle.exportKey('raw', zkSession.dek));
            const inviteSecret = bytesToB64(randBytes(18)).replace(/[+/=]/g, 'x');
            const invSalt = randBytes(16);
            const invDerived = await deriveKekAndAuth(inviteSecret, invSalt, PBKDF2_ITERATIONS);
            const invBox = await aesGcmEncrypt(invDerived.kek, dekRaw);

            const res = await fetch('/api/course/workspace/invite', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    workspace_id: zkSession.workspaceId,
                    alias: zkSession.alias,
                    method: zkSession.method,
                    auth: zkSession.authB64,
                    invite: {
                        salt: bytesToB64(invSalt),
                        iv: invBox.iv,
                        ct: invBox.ct,
                        auth: invDerived.authB64,
                        key_version: zkSession.keyVersion
                    }
                })
            });
            const data = await res.json();
            if (!data.ok) {
                setZkStatus(data.error || 'Invite creation failed', true);
                return;
            }
            const fullCode = `${data.invite_id}.${inviteSecret}`;
            const recModal = document.getElementById('zk-recovery-modal');
            document.getElementById('zk-recovery-display').textContent =
                `Share with your Partner (Expires ${data.expires_at}):\nWorkspace ID : ${zkSession.workspaceId}\nInvite Code  : ${fullCode}`;
            recModal.classList.remove('hidden');
            setZkStatus('Partner Invite Code generated! Share the Workspace ID and Invite Code with your partner.', false);
        } catch (err) {
            setZkStatus('Invite error: ' + err.message, true);
        }
    }

    async function handleJoinWorkspace() {
        try {
            const wsId = (document.getElementById('zk-join-wsid').value || '').trim();
            const fullCode = (document.getElementById('zk-join-code').value || '').trim();
            const alias = (document.getElementById('zk-join-alias').value || '').trim().toLowerCase();
            const pass = document.getElementById('zk-join-pass').value || '';
            if (!wsId || !fullCode.includes('.') || !alias || pass.length < 8) {
                setZkStatus('Provide Workspace ID, Invite Code (inviteId.secret), partner alias, and 8+ char password.', true);
                return;
            }
            const [inviteId, inviteSecret] = fullCode.split('.', 2);
            const infoRes = await fetch('/api/course/workspace/invite-info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ workspace_id: wsId, invite_id: inviteId })
            });
            const info = await infoRes.json();
            if (!info.ok) {
                setZkStatus(info.error || 'Invite not found', true);
                return;
            }
            const invDerived = await deriveKekAndAuth(inviteSecret, b64ToBytes(info.salt), PBKDF2_ITERATIONS);
            const dekRaw = await aesGcmDecrypt(invDerived.kek, { iv: info.iv, ct: info.ct });
            const dekKey = await window.crypto.subtle.importKey('raw', dekRaw, { name: 'AES-GCM' }, true, ['encrypt', 'decrypt']);

            const reg = await buildMemberRegistration(alias, pass, dekRaw, info.key_version);
            const joinRes = await fetch('/api/course/workspace/join', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    workspace_id: wsId,
                    invite_id: inviteId,
                    invite_auth: invDerived.authB64,
                    member: reg.memberPayload
                })
            });
            const joined = await joinRes.json();
            if (!joined.ok) {
                setZkStatus(joined.error || 'Join failed', true);
                return;
            }
            const plainBytes = await aesGcmDecrypt(dekKey, joined.blob);
            const parsed = JSON.parse(dec.decode(plainBytes));
            if (parsed && parsed.progressState) {
                progressState = Object.assign(progressState, parsed.progressState);
                progressState.encrypted_workspace_id = wsId;
            }
            zkSession.active = true;
            zkSession.workspaceId = wsId;
            zkSession.alias = alias;
            zkSession.method = 'password';
            zkSession.authB64 = reg.pwAuthB64;
            zkSession.revision = joined.revision;
            zkSession.keyVersion = joined.key_version;
            zkSession.dek = dekKey;
            zkSession.privateKeyJwk = reg.privateKeyJwk;
            zkSession.publicKeyRawB64 = reg.publicKeyRawB64;
            zkSession.members = joined.members || [];

            const recModal = document.getElementById('zk-recovery-modal');
            document.getElementById('zk-recovery-display').textContent =
                `Partner Joined Workspace : ${wsId}\nYour Partner Alias       : ${alias}\nYour One-Time Unlock Key : ${reg.unlockKey}`;
            recModal.classList.remove('hidden');
            updateZkBanner();
            renderStepperOptions();
            renderCurrentStep(false);
            setZkStatus(`Joined partner workspace ${wsId} as ${alias}! Save your one-time Unlock Key above.`, false);
        } catch (err) {
            setZkStatus('Could not join workspace: ' + err.message, true);
        }
    }

    async function handleSyncWorkspace() {
        if (!zkSession.active) {
            setZkStatus('Unlock or join a workspace first to sync partner state.', true);
            return;
        }
        try {
            const res = await fetch('/api/course/workspace/state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    workspace_id: zkSession.workspaceId,
                    alias: zkSession.alias,
                    method: zkSession.method,
                    auth: zkSession.authB64
                })
            });
            const data = await res.json();
            if (!data.ok) {
                setZkStatus(data.error || 'Sync failed', true);
                return;
            }
            const plainBytes = await aesGcmDecrypt(zkSession.dek, data.blob);
            const parsed = JSON.parse(dec.decode(plainBytes));
            if (parsed && parsed.progressState) {
                progressState = Object.assign(progressState, parsed.progressState);
            }
            zkSession.revision = data.revision;
            zkSession.keyVersion = data.key_version;
            zkSession.members = data.members || [];
            updateZkBanner();
            renderStepperOptions();
            renderCurrentStep(false);
            setZkStatus(`Synced latest encrypted pair state (Revision ${data.revision}).`, false);
        } catch (err) {
            setZkStatus('Sync error: ' + err.message, true);
        }
    }

    async function handleExportMrsvVault() {
        try {
            const key = zkSession.dek || await window.crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']);
            const payloadBytes = enc.encode(JSON.stringify({
                courseId,
                progressState,
                exportedAt: new Date().toISOString()
            }));
            const box = await aesGcmEncrypt(key, payloadBytes);
            const header = JSON.stringify({
                format: 'MRSV-ZERO-KNOWLEDGE-VAULT-V2',
                workspace_id: zkSession.workspaceId || 'local-vault',
                key_version: zkSession.keyVersion || 1,
                cipher: 'AES-256-GCM',
                iv: box.iv,
                members: zkSession.members || []
            });
            const headerBytes = enc.encode(header + MRSV_SEP);
            const ctBytes = b64ToBytes(box.ct);
            const full = new Uint8Array(MRSV_MAGIC.length + headerBytes.length + ctBytes.length);
            full.set(MRSV_MAGIC, 0);
            full.set(headerBytes, MRSV_MAGIC.length);
            full.set(ctBytes, MRSV_MAGIC.length + headerBytes.length);

            const blob = new Blob([full], { type: 'application/octet-stream' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${courseId}_${zkSession.alias || 'learner'}.vault`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            setZkStatus('Downloaded encrypted .vault file (MRSV ||X_SHI3LD_X|| signature).', false);
        } catch (err) {
            setZkStatus('Vault export failed: ' + err.message, true);
        }
    }

    function renderRequirementsCheckCard(sec) {
        let card = document.getElementById('requirements-check-section');
        if (card) card.remove();
        const reqCfg = sec && sec.requirements_check;
        if (!reqCfg) return;

        if (!progressState.step_requirements || typeof progressState.step_requirements !== 'object') {
            progressState.step_requirements = {};
        }
        const savedStepAns = progressState.step_requirements[sec.id] || {};
        const merged = getMergedRequirements();
        const isConfirmed = Boolean(savedStepAns._confirmed);

        card = document.createElement('section');
        card.id = 'requirements-check-section';
        card.setAttribute('aria-labelledby', 'req-check-heading');
        card.className = 'bg-slate-900 border-2 border-cyan-600/80 rounded-xl p-5 shadow-lg space-y-4';

        const stdPkgsHtml = Array.isArray(reqCfg.standard_packages) && reqCfg.standard_packages.length
            ? `<div class="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs font-mono text-emerald-300">
                   <strong class="text-slate-200">Standard Listed Packages in Course Baseline:</strong> ${reqCfg.standard_packages.map(escapeHtml).join(', ')}
               </div>`
            : '';

        const archNoteHtml = reqCfg.architecture_note
            ? `<div class="bg-cyan-950/40 border border-cyan-700/80 rounded-lg p-3 text-xs md:text-sm text-cyan-100">
                   <strong class="text-cyan-300">Architecture &amp; Layer Note:</strong> ${escapeHtml( interpolateTemplate(reqCfg.architecture_note, merged) )}
               </div>`
            : '';

        const fieldsHtml = (reqCfg.fields || []).map((f) => {
            const val = savedStepAns[f.key] != null ? savedStepAns[f.key] : (merged[f.key] != null ? merged[f.key] : (f.default || ''));
            const inputId = `req-field-${sec.id}-${f.key}`;
            let control = '';
            if (f.type === 'select' && Array.isArray(f.options)) {
                const opts = f.options.map(o => `<option value="${escapeHtml(o)}" ${o === val ? 'selected' : ''}>${escapeHtml(o)}</option>`).join('');
                control = `<select id="${inputId}" data-req-key="${escapeHtml(f.key)}" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-cyan-400">${opts}</select>`;
            } else {
                control = `<input id="${inputId}" data-req-key="${escapeHtml(f.key)}" type="text" value="${escapeHtml(val)}" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 font-mono focus:outline-none focus:border-cyan-400" />`;
            }
            return `
                <div class="space-y-1">
                    <label for="${inputId}" class="block text-xs md:text-sm font-semibold text-cyan-200">${escapeHtml(f.label)}</label>
                    ${control}
                    <p class="text-xs text-slate-400">${escapeHtml(f.help || '')}</p>
                </div>
            `;
        }).join('');

        card.innerHTML = `
            <div class="flex flex-wrap items-center justify-between gap-2">
                <h3 id="req-check-heading" class="text-base md:text-lg font-bold text-cyan-300">0. ${escapeHtml(reqCfg.heading || 'Pre-Step Tailored Requirements Check')}</h3>
                <span id="req-check-badge" class="text-xs font-mono px-2.5 py-1 rounded ${isConfirmed ? 'bg-emerald-950 text-emerald-300 border border-emerald-700' : 'bg-amber-950 text-amber-300 border border-amber-700'}">
                    ${isConfirmed ? 'Requirements Tailored &amp; Locked ✓' : 'Confirm Your Requirements Before Running'}
                </span>
            </div>
            <p class="text-sm text-slate-200 leading-relaxed">${escapeHtml(interpolateTemplate(reqCfg.prompt || '', merged))}</p>
            ${stdPkgsHtml}
            ${archNoteHtml}
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">${fieldsHtml}</div>
            <div class="flex flex-wrap items-center gap-3 pt-1">
                <button id="save-step-req-btn" type="button" class="bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs md:text-sm px-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-cyan-300">
                    Save &amp; Tailor Step + Generate Lockfile
                </button>
                <span id="req-lock-status" role="status" class="text-xs font-mono text-emerald-300">
                    ${progressState.env_lock_sha256 ? 'Environment Lock SHA-256: ' + progressState.env_lock_sha256.slice(0, 16) + '...' : ''}
                </span>
            </div>
            <div id="req-artifacts-preview" class="${zkSession.lastEnvArtifacts && (sec.id === 'm1_s1' || sec.id === 'm1_s2') ? '' : 'hidden'} space-y-2 pt-2 border-t border-slate-800">
                <div class="text-xs font-mono text-amber-300">Generated Pair Lockfile &amp; VM Config Preview (Identical Environment Guarantee):</div>
                <pre id="req-artifacts-pre" class="bg-black text-slate-200 p-3 rounded border border-slate-800 font-mono text-xs max-h-48 overflow-x-auto whitespace-pre-wrap"></pre>
            </div>
        `;

        const card1 = document.querySelector('section[aria-labelledby="section-heading"]');
        if (card1) {
            card1.insertAdjacentElement('afterend', card);
        }

        document.getElementById('save-step-req-btn').addEventListener('click', async () => {
            const inputs = card.querySelectorAll('[data-req-key]');
            const stepObj = { _confirmed: true, _updated_at: new Date().toISOString() };
            inputs.forEach(inp => {
                stepObj[inp.getAttribute('data-req-key')] = inp.value.trim();
            });
            progressState.step_requirements[sec.id] = stepObj;
            const statusEl = document.getElementById('req-lock-status');
            try {
                const res = await fetch('/api/course/requirements', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        answers: getMergedRequirements(),
                        write_to_sandbox: true
                    })
                });
                const data = await res.json();
                if (!data.ok) {
                    statusEl.className = 'text-xs font-mono text-rose-300';
                    statusEl.textContent = data.error || 'Invalid requirement input';
                    announce(statusEl.textContent);
                    return;
                }
                zkSession.lastEnvArtifacts = data;
                progressState.env_lock_sha256 = data.env_lock_sha256;
                await saveProgress();
                if (zkSession.active) {
                    await syncEncryptedWorkspaceSave();
                }
                renderCurrentStep(false);
                const previewWrap = document.getElementById('req-artifacts-preview');
                const previewPre = document.getElementById('req-artifacts-pre');
                if (previewWrap && previewPre) {
                    previewWrap.classList.remove('hidden');
                    previewPre.textContent = sec.id === 'm1_s2'
                        ? data.vagrantfile + '\n' + JSON.stringify(data.vm_spec, null, 2)
                        : data.requirements_lock_txt;
                }
                announce(`Step requirements saved and tailored! Environment Lock SHA-256: ${data.env_lock_sha256.slice(0, 12)}.`);
            } catch (e) {
                statusEl.className = 'text-xs font-mono text-rose-300';
                statusEl.textContent = 'Error validating requirements: ' + e.message;
            }
        });
    }

    const origRenderCurrentStep = window.renderCurrentStep;
    if (typeof origRenderCurrentStep === 'function') {
        window.renderCurrentStep = function () {
            injectTopEncryptedWorkspaceCard();
            const item = flatSteps[currentStepIndex];
            if (item && item.section) {
                applyStepTailoring(item.section);
            }
            const out = origRenderCurrentStep.apply(this, arguments);
            if (item && item.section) {
                renderRequirementsCheckCard(item.section);
            }
            return out;
        };
    }

    const origSaveProgress = window.saveProgress;
    if (typeof origSaveProgress === 'function') {
        window.saveProgress = async function () {
            const res = await origSaveProgress.apply(this, arguments);
            if (zkSession.active) {
                try { await syncEncryptedWorkspaceSave(); } catch (e) {}
            }
            return res;
        };
    }

    if (document.readyState !== 'loading') {
        injectTopEncryptedWorkspaceCard();
        if (flatSteps && flatSteps.length) {
            window.renderCurrentStep(false);
        }
    }
})();
