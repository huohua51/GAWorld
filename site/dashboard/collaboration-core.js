(function (root, factory) {
  "use strict";

  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.GAWorldCollaborationCore = api;
  }
}(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  function normalizeAgentIds(values) {
    const result = [];
    (values || []).forEach(function (raw) {
      const value = Number(raw);
      if (
        Number.isInteger(value)
        && value > 0
        && !result.includes(value)
      ) {
        result.push(value);
      }
    });
    return result;
  }

  function discussionPayload(values, topic, maxRounds) {
    return {
      kind: "discussion",
      agent_ids: normalizeAgentIds(values),
      topic: String(topic || "").trim(),
      max_rounds: Number(maxRounds),
    };
  }

  function cooperationPayload(values, task, leaderId, roles) {
    const payload = {
      kind: "cooperation",
      agent_ids: normalizeAgentIds(values),
      task: String(task || "").trim(),
      role_overrides: Object.assign({}, roles || {}),
    };
    const leader = Number(leaderId);
    if (Number.isInteger(leader) && leader > 0) {
      payload.leader_id = leader;
    }
    return payload;
  }

  function shouldPoll(session) {
    return Boolean(
      session
      && [
        "queued",
        "running",
        "paused",
        "failed",
        "interrupted",
      ].includes(session.status)
    );
  }

  return {
    normalizeAgentIds,
    discussionPayload,
    cooperationPayload,
    shouldPoll,
  };
}));
