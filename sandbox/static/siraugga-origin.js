(function () {
    'use strict';
    var host = (window.location.hostname || '').toLowerCase();
    var isStatic = (host === 'mikeytech.dev' || host === 'www.mikeytech.dev');
    var apiBase = isStatic ? 'https://siraugga.mikeytech.dev' : (window.location.pathname.indexOf('/ai_agent') === 0 ? '/ai_agent' : '');
    var wsBase = isStatic ? 'wss://siraugga.mikeytech.dev' : ((window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + window.location.host);

    window.IS_STATIC_PAGES = isStatic;
    window.API_BASE = apiBase;
    window.WS_BASE = wsBase;

    if (!window.__sirauggaFetchPatched) {
        window.__sirauggaFetchPatched = true;
        var origFetch = window.fetch.bind(window);
        window.fetch = function (input, init) {
            if (typeof input === 'string' && apiBase && (input.indexOf('/api/') === 0 || input.indexOf('/plugin/') === 0 || input.indexOf('/owner-device/') === 0)) {
                input = apiBase + input;
            }
            if (isStatic && typeof input === 'string' && input.indexOf(apiBase) === 0) {
                init = Object.assign({}, init || {});
                if (!init.credentials || init.credentials === 'same-origin') {
                    init.credentials = 'include';
                }
            }
            return origFetch(input, init);
        };
    }
})();
