"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const core = require("./collaboration-core.js");


test("agent ids normalize to unique positive integers", () => {
  assert.deepEqual(
    core.normalizeAgentIds(["2", 1, "2", 0, -3, "not-an-id", 4.5]),
    [2, 1],
  );
});


test("discussion payload normalizes members and trims topic", () => {
  assert.deepEqual(
    core.discussionPayload(["2", 1, "2"], "  公共空间  ", "6"),
    {
      kind: "discussion",
      agent_ids: [2, 1],
      topic: "公共空间",
      max_rounds: 6,
    },
  );
});


test("cooperation payload includes only a valid leader", () => {
  assert.deepEqual(
    core.cooperationPayload(
      [3, "1", 3],
      "  联合报告 ",
      "3",
      {"1": "研究", "3": "编辑"},
    ),
    {
      kind: "cooperation",
      agent_ids: [3, 1],
      task: "联合报告",
      leader_id: 3,
      role_overrides: {"1": "研究", "3": "编辑"},
    },
  );
  assert.equal(
    Object.hasOwn(
      core.cooperationPayload([1, 2], "报告", "none", {}),
      "leader_id",
    ),
    false,
  );
});


test("only active sessions continue polling", () => {
  ["queued", "running", "paused", "failed", "interrupted"].forEach((status) => {
    assert.equal(core.shouldPoll({status}), true);
  });
  ["completed", "cancelled", "unknown"].forEach((status) => {
    assert.equal(core.shouldPoll({status}), false);
  });
  assert.equal(core.shouldPoll(null), false);
});
