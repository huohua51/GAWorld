from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "site" / "dashboard"
CONSOLE = ROOT / "site" / "console"


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


def test_console_registers_persistent_cooperation_tab():
    html = (CONSOLE / "index.html").read_text(encoding="utf-8")
    source = (CONSOLE / "console.js").read_text(encoding="utf-8")

    assert re.search(
        r'<button[^>]*data-tab="collaboration"[^>]*>'
        r'合作任务<span class="en">Cooperation</span></button>',
        html,
    )
    assert re.search(
        r'\{\s*id:\s*"collaboration",\s*'
        r'src:\s*"/site/dashboard/collaboration\.html"\s*\}',
        source,
    )


def test_cooperation_page_exposes_workspace_controls():
    html = (DASHBOARD / "collaboration.html").read_text(encoding="utf-8")
    required_ids = [
        "taskInput",
        "memberPicker",
        "leaderSelect",
        "roleOverrides",
        "startTaskBtn",
        "sessionList",
        "taskPlan",
        "taskProgress",
        "activityFeed",
        "artifactList",
        "taskStatus",
        "pauseTaskBtn",
        "resumeTaskBtn",
        "cancelTaskBtn",
    ]

    assert all(f'id="{element_id}"' in html for element_id in required_ids)
    assert 'aria-live="polite"' in html
    assert "/site/dashboard/collaboration-core.js" in html
    assert "/site/dashboard/collaboration.js" in html


def test_cooperation_page_uses_safe_nodes_and_core_payload():
    source = (DASHBOARD / "collaboration.js").read_text(encoding="utf-8")

    assert "innerHTML" not in source
    assert "outerHTML" not in source
    assert "insertAdjacentHTML" not in source
    assert "window.GAWorldCollaborationCore" in source
    assert "core.cooperationPayload" in source
    assert 'document.createElement("a")' in source
    assert re.search(r"\.textContent\s*=", source)


def test_cooperation_artifact_urls_are_same_origin_and_session_scoped():
    module_path = DASHBOARD / "collaboration.js"
    script = f"""
      const assert = require("node:assert/strict");
      const page = require({json.dumps(str(module_path))});
      const base = "http://127.0.0.1:8000/site/dashboard/collaboration.html";
      assert.equal(
        page.safeArtifactUrl(
          "/output/collaboration/sessions/cs_1/artifacts/result.md",
          "cs_1",
          base,
        ),
        "/output/collaboration/sessions/cs_1/artifacts/result.md",
      );
      assert.equal(
        page.safeArtifactUrl("https://evil.example/cs_1/artifacts/x", "cs_1", base),
        null,
      );
      assert.equal(
        page.safeArtifactUrl("/runtime/sessions/cs_1/artifacts/x", "cs_1", base),
        null,
      );
      assert.equal(
        page.safeArtifactUrl("/runtime/sessions/cs_1/not-artifacts/x", "cs_1", base),
        null,
      );
      assert.equal(
        page.safeArtifactUrl("/runtime/sessions/cs_1/artifacts/", "cs_1", base),
        null,
      );
      assert.equal(
        page.safeArtifactUrl("/x/cs_1/artifacts/result.md", "cs_1", base),
        null,
      );
      assert.equal(
        page.safeArtifactUrl(
          "/output/collaboration/sessions/cs_10/artifacts/result.md",
          "cs_1",
          base,
        ),
        null,
      );
      assert.equal(
        page.safeArtifactUrl(
          "/output/collaboration/sessions/cs_1/artifacts/nested/result.md",
          "cs_1",
          base,
        ),
        null,
      );
      assert.equal(
        page.safeArtifactUrl(
          "/output/collaboration/sessions/cs_1/artifacts/a%2Fb.md",
          "cs_1",
          base,
        ),
        null,
      );
      assert.equal(
        page.safeArtifactUrl(
          "/output/collaboration/sessions/cs_1/artifacts/%252e%252e",
          "cs_1",
          base,
        ),
        null,
      );
      assert.equal(
        page.safeArtifactUrl(
          "/output/collaboration/sessions/cs_1/artifacts/result.md?download=1",
          "cs_1",
          base,
        ),
        null,
      );
      assert.equal(
        page.safeArtifactUrl(
          "/output/collaboration/sessions/cs_1/artifacts/result.md#preview",
          "cs_1",
          base,
        ),
        null,
      );
      assert.equal(
        page.safeArtifactUrl(
          "/output/collaboration/sessions/not_cs/artifacts/result.md",
          "not_cs",
          base,
        ),
        null,
      );
      assert.equal(page.safeArtifactUrl(
        "/output/collaboration/sessions/cs_1/artifacts/result.md",
        "cs_1/../cs_2",
        base,
      ), null);
    """
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_cooperation_session_list_only_applies_latest_request():
    module_path = DASHBOARD / "collaboration.js"
    source = module_path.read_text(encoding="utf-8")
    load_source = source[
        source.index("async function loadSessions"):
        source.index("function resetActivity")
    ]
    script = f"""
      const assert = require("node:assert/strict");
      const page = require({json.dumps(str(module_path))});
      assert.equal(page.isLatestRequest(4, 4), true);
      assert.equal(page.isLatestRequest(5, 4), false);
    """
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "listGeneration" in source
    assert "requestGeneration" in load_source
    assert load_source.count(
        "isLatestRequest(state.listGeneration, requestGeneration)"
    ) >= 3


def test_cooperation_layout_and_console_tabs_are_responsive():
    page_css = (DASHBOARD / "collaboration.css").read_text(encoding="utf-8")
    console_css = (CONSOLE / "console.css").read_text(encoding="utf-8")

    assert "grid-template-columns:" in page_css
    assert re.search(
        r"@media\s*\(max-width:\s*899px\).*?"
        r"grid-template-columns:\s*1fr",
        page_css,
        re.DOTALL,
    )
    assert re.search(
        r"@media\s*\(max-width:\s*860px\).*?"
        r"overflow-x:\s*auto",
        console_css,
        re.DOTALL,
    )
    assert "flex-shrink: 0" in console_css
    assert ":focus-visible" in page_css


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
