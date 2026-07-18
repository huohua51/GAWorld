from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "site" / "dashboard"


def test_collaboration_core_node_suite():
    result = subprocess.run(
        [
            "node",
            "--test",
            str(DASHBOARD / "collaboration-core.test.js"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_external_transcript_content_uses_text_content_only():
    source = (DASHBOARD / "interaction.js").read_text(encoding="utf-8")

    assert "innerHTML" not in source
    assert re.search(r"speaker\.textContent\s*=", source)
    assert re.search(r"content\.textContent\s*=\s*String\(event\.content", source)
    assert 'document.createElement("article")' in source


def test_panel_and_assets_are_mounted_in_safe_order():
    html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    css = (DASHBOARD / "interaction.css").read_text(encoding="utf-8")
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)

    assert 'id="collaborationPanel"' in html
    assert 'id="collaborationMembers"' in html
    assert 'id="collaborationTranscript"' in html
    assert 'id="collaborationStatus"' in html
    assert 'aria-live="polite"' in html
    assert 'aria-labelledby="collaborationMembersLabel"' in html
    assert 'aria-labelledby="collaborationTranscriptLabel"' in html
    assert ".collaboration-panel [hidden]" in css
    assert html.index("/site/dashboard/styles.css") < html.index(
        "/site/dashboard/interaction.css"
    )
    i18n_index = scripts.index("/site/dashboard/i18n.js")
    core_index = scripts.index("/site/dashboard/collaboration-core.js")
    app_index = next(
        index
        for index, script in enumerate(scripts)
        if re.fullmatch(r"/site/dashboard/app\.js(?:\?[^/]*)?", script)
    )
    interaction_index = scripts.index("/site/dashboard/interaction.js")

    assert i18n_index < core_index < app_index < interaction_index


def test_polling_controller_queues_history_and_rejects_stale_responses():
    source = (DASHBOARD / "interaction.js").read_text(encoding="utf-8")
    refresh_source = source[
        source.index("async function refreshSession"):
        source.index("async function startDiscussion")
    ]

    assert "pendingFullHistoryGeneration" in source
    assert "pollingGeneration" in source
    assert "core.queueFullHistoryRequest" in source
    assert "core.consumeFullHistoryRequest" in source
    assert "core.isCurrentPoll" in source
    assert "core.releaseCurrentPoll" in source
    assert not re.search(r"\bpolling:\s*(?:true|false)", source)
    assert source.count("empty.remove();") <= 1
    assert refresh_source.index(
        "core.queueFullHistoryRequest"
    ) < refresh_source.index(
        "document.hidden"
    ) < refresh_source.index(
        "core.consumeFullHistoryRequest"
    )


def test_session_create_hides_old_actions_and_restores_on_failure():
    source = (DASHBOARD / "interaction.js").read_text(encoding="utf-8")
    start_source = source[
        source.index("async function startDiscussion"):
        source.index("async function changeSession")
    ]

    assert "const previousSession = state.session;" in start_source
    assert start_source.index(
        "state.session = null;"
    ) < start_source.index(
        'request(\n        "/api/collaboration/sessions"'
    )
    assert re.search(
        r"catch \(error\).*?"
        r"state\.session = previousSession;.*?"
        r"renderSession\(\);.*?"
        r"schedulePoll\(\);",
        start_source,
        re.DOTALL,
    )


def test_session_actions_exclude_polling_history_and_other_controls():
    source = (DASHBOARD / "interaction.js").read_text(encoding="utf-8")
    refresh_source = source[
        source.index("async function refreshSession"):
        source.index("async function startDiscussion")
    ]
    start_source = source[
        source.index("async function startDiscussion"):
        source.index("async function changeSession")
    ]
    action_source = source[
        source.index("async function changeSession"):
        source.index("function refreshLocale")
    ]

    assert "actionPending: null" in source
    assert "actionGeneration" in source
    assert refresh_source.index(
        "state.actionPending"
    ) < refresh_source.index(
        "core.queueFullHistoryRequest"
    )
    assert "state.actionPending" in start_source
    assert "state.actionPending" in action_source
    assert "els.pauseBtn.disabled = controlsDisabled;" in source
    assert "els.resumeBtn.disabled = controlsDisabled;" in source
    assert "els.cancelBtn.disabled = controlsDisabled;" in source
    assert "els.historyBtn.disabled = controlsDisabled;" in source
    assert "|| Boolean(state.actionPending)" in source
    assert re.search(
        r"visibilitychange.*?!state\.actionPending.*?"
        r"refreshSession\(false\);",
        source,
        re.DOTALL,
    )


def test_current_action_failure_releases_controls_and_reschedules_poll():
    source = (DASHBOARD / "interaction.js").read_text(encoding="utf-8")
    action_source = source[
        source.index("async function changeSession"):
        source.index("function refreshLocale")
    ]

    assert "core.isCurrentAction" in source
    assert "core.releaseCurrentAction" in source
    assert re.search(
        r"catch \(error\).*?"
        r"releaseAction\(identity\);.*?"
        r"renderSession\(\);.*?"
        r"reportError\(error\);.*?"
        r"schedulePoll\(\);",
        action_source,
        re.DOTALL,
    )
    assert "finally" not in action_source


def test_collaboration_locale_keys_match_in_order():
    zh = json.loads(
        (DASHBOARD / "locales" / "zh-CN.json").read_text(encoding="utf-8")
    )
    en = json.loads(
        (DASHBOARD / "locales" / "en.json").read_text(encoding="utf-8")
    )
    zh_keys = list(zh)
    en_keys = list(en)
    required = [
        "collaboration.title",
        "collaboration.members",
        "collaboration.make_friends",
        "collaboration.topic",
        "collaboration.rounds",
        "collaboration.start",
        "collaboration.pause",
        "collaboration.resume",
        "collaboration.cancel",
        "collaboration.status",
        "collaboration.empty_transcript",
    ]

    assert zh_keys == en_keys
    assert all(key in en for key in required)
    indexes = [en_keys.index(key) for key in required]
    assert indexes == sorted(indexes)
