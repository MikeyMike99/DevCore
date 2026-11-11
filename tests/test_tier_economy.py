"""Tier economy: under high usage, Tier 1 is moved to the economy model (core/model_routing.json
"tier_economy"). Run (WSL): cd core && ~/.venvs/devcore/bin/python -m pytest -q ../tests/test_tier_economy.py
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents import model_router as mr  # noqa: E402

MODELS = {
    "Claude Sonnet 5.5 (Medium) · via Google": {"backend": "antigravity", "cli_model": "Claude Sonnet 5.5 (Medium)", "quota_group": "google:claude_gpt"},
    "Claude Sonnet 5.5": {"backend": "claude_cli", "cli_model": "claude-sonnet-5-5", "quota_group": "claude_sub"},
    "Gemini 3.8 Flash (High)": {"backend": "antigravity", "cli_model": "Gemini 3.8 Flash (High)", "quota_group": "google:gemini"},
    "Gemini 4 Argon (Medium)": {"backend": "antigravity", "cli_model": "Gemini 4 Argon (Medium)", "quota_group": "google:argon"},
}


def usage(argon=80, claude_gpt=80, gemini=80, claude_week=10, claude_session=10):
    row = lambda g, p: {"group": g, "period": "Weekly", "remaining_pct": p, "reset_ts": 2e9}
    return {"at": 9e18, "google": [row("Gemini 4 Argon", argon), row("Claude and GPT models", claude_gpt),
                                   row("Gemini Models", gemini)],
            "claude": {"week_pct": claude_week, "session_pct": claude_session}}


@pytest.fixture
def setup(monkeypatch):
    state = {"usage": usage()}
    monkeypatch.setattr(mr, "discovered_models", lambda: MODELS)
    monkeypatch.setattr(mr, "usage_snapshot", lambda wait=False: state["usage"])
    monkeypatch.setattr(mr, "_load_quota", lambda: {})
    return state


def test_no_change_when_usage_is_fine(setup):
    assert mr.economy_model(1) == (None, [])


def test_tier1_moved_when_any_premium_pool_is_low(setup):
    setup["usage"] = usage(claude_week=81)          # Claude subscription: 19% left
    eco, busy = mr.economy_model(1)
    assert eco == "Gemini 3.8 Flash (High)" and busy == ["claude_sub"]
    setup["usage"] = usage(argon=0)                  # Argon used up
    assert mr.economy_model(1)[0] == "Gemini 3.8 Flash (High)"


def test_other_tiers_never_moved(setup):
    setup["usage"] = usage(argon=0, claude_gpt=5, claude_week=99)
    for tier in (2, 3, 4, 5):
        assert mr.economy_model(tier) == (None, [])


def test_gemini_pool_low_alone_does_not_trigger(setup):
    setup["usage"] = usage(gemini=10)                # Flash's own pool is not a premium pool
    assert mr.economy_model(1) == (None, [])


def test_falls_back_to_normal_chain_when_flash_is_out(setup):
    setup["usage"] = usage(argon=0, gemini=0)
    assert mr.economy_model(1)[0] is None
    setup["usage"] = usage(argon=0)
    assert mr.economy_model(1, tried=("Gemini 3.8 Flash (High)",))[0] is None


def test_pool_left_pct_uses_lowest_window(setup):
    setup["usage"] = usage(claude_week=40, claude_session=75)
    assert mr.pool_left_pct()["claude_sub"] == 25
