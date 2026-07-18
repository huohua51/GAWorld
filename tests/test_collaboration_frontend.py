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
    expected = [
        "/site/dashboard/i18n.js",
        "/site/dashboard/collaboration-core.js",
        "/site/dashboard/citymap-view.js?v=1",
        "/site/dashboard/app.js?v=4",
        "/site/dashboard/interaction.js",
    ]
    assert [script for script in scripts if script in expected] == expected


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
