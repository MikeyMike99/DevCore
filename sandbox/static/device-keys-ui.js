// Access keys in the main app:
//  * automatic sign-in on a device that has a Siraugga access key (once per tab, not after a
//    manual logout), plus a "Sign in with access key" button as a fallback;
//  * the Super Admin's Settings section: owner password, one-time invite links with a role,
//    and the list of devices/people with Remove.
(function () {
    'use strict';
    var $ = function (id) { return document.getElementById(id); };
    var ss = {
        get: function (k) { try { return sessionStorage.getItem(k); } catch (_) { return null; } },
        set: function (k, v) { try { sessionStorage.setItem(k, v); } catch (_) {} },
    };
    function token() { try { return localStorage.getItem('agy_auth_token') || ''; } catch (_) { return ''; } }
    function hasKeyHere() { try { return localStorage.getItem('siraugga_access_key') === '1'; } catch (_) { return false; } }
    function onLocalhost() { return /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname); }

    async function api(method, url, body) {
        var r = await fetch(url, {
            method: method, cache: 'no-store', credentials: 'same-origin',
            headers: Object.assign({ 'Authorization': 'Bearer ' + token() }, body ? { 'Content-Type': 'application/json' } : {}),
            body: body ? JSON.stringify(body) : undefined,
        });
        var d = {};
        try { d = await r.json(); } catch (_) {}
        return { ok: r.ok && d.success !== false, status: r.status, data: d };
    }

    // ---- who am I? ----------------------------------------------------------------------------
    async function signedIn() {
        if (token()) {
            var me = await api('GET', '/api/auth/me');
            if (me.ok && me.data.user) return true;
        }
        try {
            var s = await (await fetch('/api/owner-device/status', { cache: 'no-store' })).json();
            if (s.this_browser_trusted || s.is_host) return true;
        } catch (_) {}
        return false;
    }

    // ---- sign in -------------------------------------------------------------------------------
    var fb = $('access-key-feedback');
    function say(t) { if (fb) fb.textContent = t || ''; }

    async function doSignIn(auto) {
        if (!window.SirauggaKeys) return;
        say(auto ? 'Signing you in with this device\'s access key…' : 'Confirm on your device…');
        try {
            await window.SirauggaKeys.signIn();
            say('Signed in. Reloading…');
            location.reload();
        } catch (e) {
            say(auto ? '' : e.message);
            showSignInButton(true);
        }
    }

    function showSignInButton(on) {
        var b = $('access-key-signin-btn'), l = $('access-key-setup-link');
        if (b) b.classList.toggle('hidden', !on);
        if (l) l.classList.toggle('hidden', !on || hasKeyHere());
    }

    var signinBtn = $('access-key-signin-btn');
    if (signinBtn) signinBtn.addEventListener('click', function () { doSignIn(false); });

    async function initSignIn() {
        if (onLocalhost() || !window.PublicKeyCredential) return;     // localhost is the owner already
        if (await signedIn()) return;
        showSignInButton(true);
        // Automatic: only where a key was set up, once per tab, and never right after "Logout".
        if (hasKeyHere() && !ss.get('agy_manual_logout') && ss.get('ak_auto_tried') !== '1') {
            ss.set('ak_auto_tried', '1');
            doSignIn(true);
        }
    }

    // ---- owner panel ---------------------------------------------------------------------------
    var card = $('access-keys-card');
    var afb = $('ak-feedback');
    function asay(t) { if (afb) afb.textContent = t || ''; }

    function fmtDate(ts) {
        if (!ts) return '';
        try { return new Date(ts * 1000).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' }); } catch (_) { return ''; }
    }
    function device(label) {
        label = label || '';
        var os = /Windows/.test(label) ? 'Windows' : /Android/.test(label) ? 'Android' : /iPhone|iPad/.test(label) ? 'iPhone/iPad' : /Mac OS/.test(label) ? 'Mac' : /Linux/.test(label) ? 'Linux' : 'Device';
        var br = /Edg\//.test(label) ? 'Edge' : /Chrome\//.test(label) ? 'Chrome' : /Firefox\//.test(label) ? 'Firefox' : /Safari\//.test(label) ? 'Safari' : '';
        return br ? br + ' on ' + os : os;
    }

    function render(d) {
        $('ak-password-state').textContent = d.has_password ? '(set; type a new one to change it)' : '(not set yet)';
        $('ak-setup-url').textContent = d.setup_url || (location.origin + '/setup');
        var sel = $('ak-invite-role');
        if (!sel.options.length) {
            // Least access first, so the default choice is the safe one.
            var order = ['guest', 'modder', 'gamedev', 'admin'];
            Object.keys(d.roles || {}).sort(function (a, b) {
                return (order.indexOf(a) + 99) % 99 - (order.indexOf(b) + 99) % 99;
            }).forEach(function (k) {
                var o = document.createElement('option'); o.value = k; o.textContent = d.roles[k]; sel.appendChild(o);
            });
        }
        var list = $('ak-list');
        list.innerHTML = '';
        function row(text, btnText, onClick) {
            var li = document.createElement('li');
            li.className = 'flex items-center justify-between gap-2 bg-slate-950/60 border border-slate-800 rounded px-2 py-1';
            var span = document.createElement('span'); span.textContent = text; li.appendChild(span);
            var b = document.createElement('button');
            b.type = 'button'; b.textContent = btnText;
            b.className = 'shrink-0 min-h-[32px] text-[11px] text-rose-300 hover:text-rose-100 bg-slate-800 rounded px-2 focus:ring-2 focus:ring-rose-400 focus:outline-none';
            b.setAttribute('aria-label', btnText + ': ' + text);
            b.addEventListener('click', onClick);
            li.appendChild(b); list.appendChild(li);
        }
        (d.keys || []).forEach(function (k) {
            var who = k.role === 'owner' ? 'You (Super Admin)'
                : k.name + (k.email ? ' (' + k.email + ')' : '') + ' · ' + ((d.roles || {})[k.role] || k.role)
                  + (k.project ? ' on ' + k.project + (k.parts && k.parts.length ? ' [' + k.parts.join(', ') + ']' : ' [whole project]') : '');
            row(who + ' · ' + device(k.label) + ' · last used ' + fmtDate(k.last_used), 'Remove', async function () {
                if (!window.confirm('Remove this access key? That device will no longer be able to sign in with it.')) return;
                var r = await api('DELETE', '/api/device-keys/keys/' + encodeURIComponent(k.id));
                asay(r.ok ? 'Access key removed.' : (r.data.error || 'Could not remove it.'));
                refresh();
            });
        });
        (d.invites || []).forEach(function (v) {
            row(v.name + (v.email ? ' (' + v.email + ')' : '') + ' · ' + ((d.role_labels || d.roles || {})[v.role] || v.role) + ' · link not used yet (until ' + fmtDate(v.expires_at) + ')', 'Cancel link', async function () {
                var r = await api('DELETE', '/api/device-keys/invites/' + encodeURIComponent(v.id));
                asay(r.ok ? 'Link cancelled.' : (r.data.error || 'Could not cancel it.'));
                refresh();
            });
        });
        if (!list.children.length) {
            var li = document.createElement('li'); li.className = 'text-slate-500';
            li.textContent = 'No access keys yet.'; list.appendChild(li);
        }
    }

    async function refresh() {
        if (!card) return;
        var r = await api('GET', '/api/device-keys');
        card.classList.toggle('hidden', !r.ok);
        if (r.ok) render(r.data);
    }

    // Game developer invites: pick the project (and parts) they are handed.
    async function fillProjects() {
        var sel = $('ak-invite-project');
        if (!sel || sel.options.length) return;
        var r = await api('GET', '/api/projects');
        (r.data.projects || []).forEach(function (p) {
            var o = document.createElement('option'); o.value = p; o.textContent = p; sel.appendChild(o);
        });
    }
    function syncDevFields() {
        var on = $('ak-invite-role') && $('ak-invite-role').value === 'gamedev';
        $('ak-dev-fields').classList.toggle('hidden', !on);
        if (on) fillProjects();
    }

    if (card) {
        $('ak-invite-role').addEventListener('change', syncDevFields);
        $('ak-password-form').addEventListener('submit', async function (e) {
            e.preventDefault();
            var pw = $('ak-password');
            var r = await api('POST', '/api/device-keys/password', { password: pw.value });
            asay(r.ok ? 'Owner password saved.' : (r.data.error || 'Could not save it.'));
            if (r.ok) { pw.value = ''; refresh(); } else pw.focus();
        });
        $('ak-invite-form').addEventListener('submit', async function (e) {
            e.preventDefault();
            var name = $('ak-invite-name'), email = $('ak-invite-email');
            var isDev = $('ak-invite-role').value === 'gamedev';
            var r = await api('POST', '/api/device-keys/invites', {
                name: name.value, email: email.value, role: $('ak-invite-role').value,
                project: isDev ? $('ak-invite-project').value : '',
                parts: isDev ? $('ak-invite-parts').value : '',
            });
            if (!r.ok) { asay(r.data.error || 'Could not create the link.'); (/email/i.test(r.data.error || '') ? email : name).focus(); return; }
            $('ak-invite-url').value = r.data.url;
            $('ak-invite-result').classList.remove('hidden');
            $('ak-invite-url').focus(); $('ak-invite-url').select();
            asay(r.data.emailed_to
                ? 'Link created for ' + name.value + ' and emailed to ' + r.data.emailed_to + '.'
                : r.data.email_error
                    ? 'Link created for ' + name.value + ', but ' + r.data.email_error.charAt(0).toLowerCase() + r.data.email_error.slice(1)
                    : 'Link created for ' + name.value + '. Copy it and send it to them.');
            name.value = ''; email.value = ''; $('ak-invite-parts').value = '';
            refresh();
        });
        $('ak-invite-copy').addEventListener('click', async function () {
            var v = $('ak-invite-url').value;
            try { await navigator.clipboard.writeText(v); asay('Link copied.'); }
            catch (_) { $('ak-invite-url').select(); asay('Press Ctrl+C to copy the selected link.'); }
        });
    }

    refresh();
    initSignIn();
})();
