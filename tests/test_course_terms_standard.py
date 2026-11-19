"""Standard: every course has the Terms & Privacy agreement, with no exceptions and nothing to remember when adding a course.

The gate lives in the shared course page and the server enforces it for every course id, so a new course gets it by itself.
These tests prove it for every course that exists on disk."""
import asyncio

import pytest

from core import response_cards
from core.routes import projects as proj


def _ids():
    return [c["id"] for c in response_cards.list_courses()]


def test_there_are_courses_to_check():
    assert len(_ids()) >= 10


@pytest.mark.parametrize("course_id", _ids())
def test_every_course_page_has_the_terms_gate(course_id):
    from core.server import app

    async def _run():
        r = await app.test_client().get(f"/plugin/course?course={course_id}")
        assert r.status_code == 200
        html = (await r.get_data()).decode("utf-8")
        assert 'id="course-terms-gate"' in html, course_id
        assert "Your data and privacy" in html, course_id
        assert 'id="accept-terms-btn"' in html, course_id
    asyncio.run(_run())


def test_the_server_refuses_work_until_the_terms_are_accepted_for_any_course():
    """The check is on the progress record, not on a course name, so it holds for every course id."""
    assert proj._is_terms_accepted({}) is False
    assert proj._is_terms_accepted({"terms_accepted": {"accepted": False}}) is False
    assert proj._is_terms_accepted({"terms_accepted": {"accepted": True, "version": proj.COURSE_TERMS_VERSION}}) is True
    # Everybody, always: an old version of the terms, or none recorded, means "ask again".
    assert proj._is_terms_accepted({"terms_accepted": {"accepted": True, "version": "an-old-version"}}) is False
    assert proj._is_terms_accepted({"terms_accepted": {"accepted": True}}) is False


def test_the_owner_is_not_exempt(monkeypatch):
    """The owner's own course box used to skip the terms; now it does not."""
    monkeypatch.setattr(proj, "_is_course_admin_box", lambda: True)
    assert proj._is_terms_accepted({}) is False
