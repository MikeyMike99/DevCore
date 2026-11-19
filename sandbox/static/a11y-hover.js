(function () {
    'use strict';

    if (window.__sirauggaHoverInit) return;
    window.__sirauggaHoverInit = true;

    var STORAGE_KEY = 'siraugga_hover_read';
    var HOVER_DELAY_MS = 160;
    var DEDUPE_MS = 1500;
    var MAX_TEXT_LEN = 200;

    var INTERACTIVE_SELECTOR = [
        'button', 'a[href]', 'input', 'select', 'textarea', 'summary',
        '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
        '[role="checkbox"]', '[role="radio"]', '[role="switch"]', '[role="option"]',
        '[data-hover-read]'
    ].join(',');

    var SEMANTIC_SELECTOR = 'h1,h2,h3,h4,h5,h6,label,th,td,dt,dd,figcaption,li,p,code,kbd';

    var announcer = null;
    var hoverTimer = null;
    var clearTimer = null;
    var lastEl = null;
    var lastText = '';
    var lastAt = 0;

    function isEnabled() {
        try {
            return localStorage.getItem(STORAGE_KEY) !== 'false';
        } catch (e) {
            return true;
        }
    }

    function setEnabled(val) {
        try {
            localStorage.setItem(STORAGE_KEY, val ? 'true' : 'false');
        } catch (e) {}
    }

    function ensureAnnouncer() {
        if (announcer && document.body && document.body.contains(announcer)) {
            return announcer;
        }
        if (!document.body) return null;
        announcer = document.getElementById('a11y-hover-announcer');
        if (!announcer) {
            announcer = document.createElement('div');
            announcer.id = 'a11y-hover-announcer';
            announcer.setAttribute('role', 'status');
            announcer.setAttribute('aria-live', 'polite');
            announcer.setAttribute('aria-atomic', 'true');
            announcer.style.cssText = [
                'position:absolute', 'width:1px', 'height:1px', 'padding:0',
                'margin:-1px', 'overflow:hidden', 'clip:rect(0,0,0,0)',
                'white-space:nowrap', 'border:0'
            ].join(';');
            document.body.appendChild(announcer);
        }
        return announcer;
    }

    function speakText(text) {
        var el = ensureAnnouncer();
        if (!el || !text) return;
        if (clearTimer) {
            clearTimeout(clearTimer);
            clearTimer = null;
        }
        el.textContent = '';
        setTimeout(function () {
            if (!el) return;
            el.textContent = text;
            clearTimer = setTimeout(function () {
                if (el) el.textContent = '';
            }, 4000);
        }, 20);
    }

    function clean(str) {
        if (!str) return '';
        var s = String(str).replace(/\s+/g, ' ').trim();
        if (s.length > MAX_TEXT_LEN) {
            s = s.slice(0, MAX_TEXT_LEN - 3).trim() + '...';
        }
        return s;
    }

    function isVisible(el) {
        if (!el || el.nodeType !== 1) return false;
        if (el.hidden || el.getAttribute('aria-hidden') === 'true') return false;
        var style = window.getComputedStyle(el);
        if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
        return true;
    }

    function getLabelledByText(el) {
        var ids = el.getAttribute('aria-labelledby');
        if (!ids) return '';
        var parts = [];
        ids.split(/\s+/).forEach(function (id) {
            var ref = document.getElementById(id);
            if (ref) {
                var t = clean(ref.textContent);
                if (t) parts.push(t);
            }
        });
        return parts.join(' ');
    }

    function getFormLabel(el) {
        if (el.labels && el.labels.length > 0) {
            var out = [];
            for (var i = 0; i < el.labels.length; i++) {
                var t = clean(el.labels[i].textContent);
                if (t) out.push(t);
            }
            if (out.length) return out.join(' ');
        }
        if (el.id) {
            var lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
            if (lbl) return clean(lbl.textContent);
        }
        return '';
    }

    function getAccessibleName(el) {
        var name = clean(el.getAttribute('aria-label'));
        if (name) return name;

        name = getLabelledByText(el);
        if (name) return name;

        var tag = el.tagName.toLowerCase();
        if (tag === 'input' || tag === 'select' || tag === 'textarea') {
            name = getFormLabel(el) || clean(el.getAttribute('placeholder')) || clean(el.getAttribute('title'));
            if (!name && tag === 'input' && (el.type === 'submit' || el.type === 'button' || el.type === 'reset')) {
                name = clean(el.value);
            }
            return name;
        }

        if (tag === 'img') {
            return clean(el.getAttribute('alt')) || clean(el.getAttribute('title'));
        }

        var text = clean(el.innerText || el.textContent);
        if (text) return text;

        return clean(el.getAttribute('title'));
    }

    function describeElement(el) {
        var name = getAccessibleName(el);
        if (!name) return '';

        var tag = el.tagName.toLowerCase();
        var role = (el.getAttribute('role') || '').toLowerCase();
        var suffixes = [];

        if (tag === 'button' || role === 'button') {
            if (!/\bbutton\b/i.test(name)) suffixes.push('button');
        } else if (tag === 'a' || role === 'link') {
            if (!/\blink\b/i.test(name)) suffixes.push('link');
        } else if (/^h[1-6]$/.test(tag) || role === 'heading') {
            suffixes.push('heading');
        } else if (tag === 'select') {
            suffixes.push('dropdown');
            if (el.selectedOptions && el.selectedOptions[0]) {
                var opt = clean(el.selectedOptions[0].textContent);
                if (opt && opt !== name) suffixes.push(opt);
            }
        } else if (tag === 'input') {
            var type = (el.type || 'text').toLowerCase();
            if (type === 'checkbox' || type === 'radio') {
                suffixes.push(type);
                suffixes.push(el.checked ? 'checked' : 'not checked');
            } else if (type === 'password') {
                suffixes.push('password field');
            } else if (type !== 'submit' && type !== 'button' && type !== 'reset') {
                suffixes.push(type + ' field');
                var val = clean(el.value);
                if (val && val !== name) suffixes.push('value ' + val);
            }
        } else if (tag === 'textarea') {
            suffixes.push('text area');
        } else if (role === 'tab') {
            suffixes.push('tab');
        } else if (role === 'switch') {
            suffixes.push('switch');
        }

        var expanded = el.getAttribute('aria-expanded');
        if (expanded === 'true') suffixes.push('expanded');
        else if (expanded === 'false') suffixes.push('collapsed');

        if (el.getAttribute('aria-selected') === 'true') suffixes.push('selected');
        if (el.disabled || el.getAttribute('aria-disabled') === 'true') suffixes.push('disabled');

        return suffixes.length ? (name + ', ' + suffixes.join(', ')) : name;
    }

    function hasDirectText(el) {
        for (var i = 0; i < el.childNodes.length; i++) {
            var n = el.childNodes[i];
            if (n.nodeType === 3 && n.nodeValue && n.nodeValue.trim().length > 0) {
                return true;
            }
        }
        return false;
    }

    function resolveHoverTarget(startEl) {
        if (!startEl || startEl.nodeType !== 1) return null;
        if (startEl.closest('#a11y-hover-announcer, #sr-announcer, #sr-alerts')) return null;

        var interactive = startEl.closest(INTERACTIVE_SELECTOR);
        if (interactive && isVisible(interactive)) {
            return interactive;
        }

        if (!isVisible(startEl)) return null;

        var semantic = startEl.closest(SEMANTIC_SELECTOR);
        if (semantic && isVisible(semantic) && semantic.children.length <= 6) {
            return semantic;
        }

        var tag = startEl.tagName.toLowerCase();
        if (tag !== 'html' && tag !== 'body' && tag !== 'main' && tag !== 'section' && tag !== 'div') {
            if (hasDirectText(startEl) || startEl.getAttribute('aria-label') || startEl.getAttribute('title')) {
                return startEl;
            }
        } else if (tag === 'div' && startEl.children.length === 0 && hasDirectText(startEl)) {
            return startEl;
        }

        return null;
    }

    document.addEventListener('pointerover', function (e) {
        if (!isEnabled()) return;
        if (e.pointerType === 'touch') return;

        if (hoverTimer) {
            clearTimeout(hoverTimer);
            hoverTimer = null;
        }

        var target = resolveHoverTarget(e.target);
        if (!target) return;

        hoverTimer = setTimeout(function () {
            hoverTimer = null;
            var text = describeElement(target);
            if (!text) return;

            var now = Date.now();
            if (target === lastEl && (now - lastAt) < DEDUPE_MS) return;
            if (text === lastText && (now - lastAt) < DEDUPE_MS) return;

            lastEl = target;
            lastText = text;
            lastAt = now;
            speakText(text);
        }, HOVER_DELAY_MS);
    }, { passive: true });

    document.addEventListener('pointerleave', function () {
        if (hoverTimer) {
            clearTimeout(hoverTimer);
            hoverTimer = null;
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.altKey && e.shiftKey && (e.key === 'H' || e.key === 'h')) {
            e.preventDefault();
            var next = !isEnabled();
            setEnabled(next);
            speakText(next ? 'Hover reading enabled' : 'Hover reading disabled');
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ensureAnnouncer);
    } else {
        ensureAnnouncer();
    }
})();
