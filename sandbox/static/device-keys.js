// Access keys (passkeys): shared browser helpers for /setup and the main app.
// The private key stays on this device; the server only ever sees signed answers.
(function () {
    'use strict';

    function b64uToBuf(s) {
        s = String(s).replace(/-/g, '+').replace(/_/g, '/');
        while (s.length % 4) s += '=';
        var bin = atob(s), out = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
        return out.buffer;
    }
    function bufToB64u(buf) {
        var bytes = new Uint8Array(buf), bin = '';
        for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }

    async function post(url, body) {
        var headers = { 'Content-Type': 'application/json' };
        try { var t = localStorage.getItem('agy_auth_token'); if (t) headers.Authorization = 'Bearer ' + t; } catch (_) {}
        var r = await fetch(url, {
            method: 'POST', credentials: 'same-origin', cache: 'no-store',
            headers: headers, body: JSON.stringify(body || {}),
        });
        var data = {};
        try { data = await r.json(); } catch (_) {}
        if (!r.ok || !data.success) throw new Error(data.error || ('Request failed (' + r.status + ')'));
        return data;
    }

    function friendly(err) {
        var n = err && err.name;
        if (n === 'NotAllowedError') return 'Cancelled, or the device did not confirm it was you. Try again.';
        if (n === 'InvalidStateError') return 'This device already has an access key for Siraugga. Use "Sign in with access key" instead.';
        if (n === 'SecurityError') return 'Access keys only work on the real Siraugga address (https).';
        if (n === 'NotSupportedError') return 'This browser or device cannot create access keys.';
        return (err && err.message) || String(err);
    }

    function saveSession(data, withKey) {
        try {
            localStorage.setItem('agy_auth_token', data.token);
            localStorage.setItem('agy_user', JSON.stringify(data.user));
            if (withKey !== false) localStorage.setItem('siraugga_access_key', '1');   // lets the app sign in automatically
            sessionStorage.removeItem('agy_manual_logout');
        } catch (_) {}
    }

    // Sign-in for every account: username + password -> email -> one-time emailed link.
    async function loginPassword(username, password) {
        return (await post('/api/login/password', { username: username, password: password })).step_id;
    }
    async function loginEmail(stepId, email) {
        return (await post('/api/login/email', { step_id: stepId, email: email })).message;
    }
    async function loginLink(code) {
        var done = await post('/api/login/link', { code: code });
        saveSession(done, false);
        return done;
    }
    function hasKeyHere() { try { return localStorage.getItem('siraugga_access_key') === '1'; } catch (_) { return false; } }

    // Set up this device. `proof` is { password } (owner), { invite } (one-time link), or {}
    // when already signed in as the owner.
    async function register(proof) {
        if (!window.PublicKeyCredential) throw new Error('This browser cannot create access keys.');
        var start = await post('/api/device-keys/setup/start', proof);
        var o = start.options;
        o.challenge = b64uToBuf(o.challenge);
        o.user.id = b64uToBuf(o.user.id);
        (o.excludeCredentials || []).forEach(function (c) { c.id = b64uToBuf(c.id); });
        var cred;
        try { cred = await navigator.credentials.create({ publicKey: o }); }
        catch (e) { throw new Error(friendly(e)); }
        var resp = cred.response;
        var json = {
            id: cred.id, rawId: bufToB64u(cred.rawId), type: cred.type,
            authenticatorAttachment: cred.authenticatorAttachment || undefined,
            clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
            response: {
                clientDataJSON: bufToB64u(resp.clientDataJSON),
                attestationObject: bufToB64u(resp.attestationObject),
                transports: resp.getTransports ? resp.getTransports() : [],
            },
        };
        var done = await post('/api/device-keys/setup/finish', { setup_id: start.setup_id, credential: json });
        saveSession(done);
        return done;
    }

    // Sign in on a device that already has an access key.
    async function signIn() {
        if (!window.PublicKeyCredential) throw new Error('This browser cannot use access keys.');
        var start = await post('/api/device-keys/login/start', {});
        var o = start.options;
        o.challenge = b64uToBuf(o.challenge);
        (o.allowCredentials || []).forEach(function (c) { c.id = b64uToBuf(c.id); });
        var cred;
        try { cred = await navigator.credentials.get({ publicKey: o }); }
        catch (e) { throw new Error(friendly(e)); }
        var resp = cred.response;
        var json = {
            id: cred.id, rawId: bufToB64u(cred.rawId), type: cred.type,
            authenticatorAttachment: cred.authenticatorAttachment || undefined,
            clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
            response: {
                clientDataJSON: bufToB64u(resp.clientDataJSON),
                authenticatorData: bufToB64u(resp.authenticatorData),
                signature: bufToB64u(resp.signature),
                userHandle: resp.userHandle ? bufToB64u(resp.userHandle) : null,
            },
        };
        var done = await post('/api/device-keys/login/finish', { login_id: start.login_id, credential: json });
        saveSession(done);
        return done;
    }

    window.SirauggaKeys = { register: register, signIn: signIn, loginPassword: loginPassword, loginEmail: loginEmail,
                            loginLink: loginLink, hasKeyHere: hasKeyHere };
})();
