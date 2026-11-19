"""Shared test setup."""
import pytest


@pytest.fixture(autouse=True)
def _reset_course_box():
    """Forget the cached learner sandbox between tests.

    core.routes.projects keeps the current learner's sandbox folder in a ContextVar. Tests that call its
    helpers outside a request set it in the test thread, and it would otherwise leak into the next test
    (pointing at a temporary folder that no longer exists).
    """
    try:
        from core.routes import projects as proj_mod
    except Exception:
        yield
        return
    proj_mod._COURSE_BOX.set(None)
    yield
    proj_mod._COURSE_BOX.set(None)


@pytest.fixture(scope="session")
def rendering_browser():
    """Skip click-driven browser tests when this Chromium cannot reliably render animation frames.

    Playwright waits for a rendered frame before every click, so a browser that does not render (some
    headless setups under WSL) hangs for 30 seconds on the first click. The probe needs 10 frames in a row.
    """
    from playwright.sync_api import sync_playwright

    probe = (
        "() => new Promise(r => { let n = 0; const t = setTimeout(() => r(false), 3000);"
        " const step = () => { if (++n >= 10) { clearTimeout(t); r(true); } else requestAnimationFrame(step); };"
        " requestAnimationFrame(step); })"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_context().new_page()
            page.goto("about:blank")
            renders = page.evaluate(probe)
        finally:
            browser.close()
    if not renders:
        pytest.skip("This headless Chromium does not reliably render animation frames, so clicks and 1080p recording cannot be driven here.")
