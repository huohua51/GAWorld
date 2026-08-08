/* Pure logic for the twin mobile client.
 *
 * No DOM, no fetch, no browser APIs — everything here is testable under
 * `node site/mobile/core.test.js`. Browser-only concerns (Geolocation,
 * IndexedDB, rendering) live in app.js, which is deliberately thin.
 *
 * Mirrors the collaboration-core.js convention: UMD wrapper exporting to both
 * CommonJS and the window global.
 */
(function (root, factory) {
  "use strict";

  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.GAWorldTwinCore = api;
  }
}(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  /* Must stay in step with ACTION_TAGS in gaworld/twin/backend.py. The server
   * re-validates, so a drift here degrades to "other" rather than corrupting
   * data. */
  const ACTION_TAGS = [
    "commute", "work", "study", "meal", "shopping",
    "rest", "social", "exercise", "errand", "other",
  ];

  const TAG_LABELS = {
    commute: "通勤",
    work: "工作",
    study: "学习",
    meal: "吃饭",
    shopping: "购物",
    rest: "休息",
    social: "社交",
    exercise: "运动",
    errand: "办事",
    other: "其他",
  };

  function buildReport(options) {
    const opts = options || {};
    const coords = opts.coords || {};
    const tag = ACTION_TAGS.includes(opts.tag) ? opts.tag : "other";
    return {
      report_id: String(opts.reportId || ""),
      ts: Number(opts.ts || 0),
      tz_offset: Number(opts.tzOffset || 0),
      loc: {
        lat: Number(coords.latitude || 0),
        lng: Number(coords.longitude || 0),
        acc_m: Number(coords.accuracy || 0),
        source: opts.manual ? "manual" : "gps",
      },
      action_tag: tag,
      note: String(opts.note || "").trim(),
    };
  }

  /* Remove reports the server confirmed, keeping anything still unsent.
   * Called after a queue flush; the server is idempotent on report_id, so a
   * report that syncs twice is harmless — one that is dropped early is not. */
  function dropSynced(queue, syncedIds) {
    const synced = new Set(syncedIds || []);
    return (queue || []).filter(function (item) {
      return !synced.has(item.report_id);
    });
  }

  function trailBounds(points) {
    const list = (points || []).filter(function (p) {
      return p && p.grid && typeof p.grid.x === "number";
    });
    if (!list.length) {
      return {minX: 0, maxX: 1, minY: 0, maxY: 1};
    }
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    list.forEach(function (p) {
      minX = Math.min(minX, p.grid.x);
      maxX = Math.max(maxX, p.grid.x);
      minY = Math.min(minY, p.grid.y);
      maxY = Math.max(maxY, p.grid.y);
    });
    /* A single point (or a perfectly straight line) would give a zero span and
     * make projectPoint divide by zero. Pad it into a real box. */
    if (maxX - minX < 1e-6) { minX -= 0.5; maxX += 0.5; }
    if (maxY - minY < 1e-6) { minY -= 0.5; maxY += 0.5; }
    return {minX: minX, maxX: maxX, minY: minY, maxY: maxY};
  }

  function projectPoint(point, bounds, width, height, padding) {
    const pad = Number(padding || 0);
    const innerW = Math.max(1, width - pad * 2);
    const innerH = Math.max(1, height - pad * 2);
    const spanX = bounds.maxX - bounds.minX;
    const spanY = bounds.maxY - bounds.minY;
    const fx = (point.grid.x - bounds.minX) / spanX;
    const fy = (point.grid.y - bounds.minY) / spanY;
    return {
      x: pad + fx * innerW,
      /* Canvas y grows downward; map grid y grows north. Flip so the drawing
       * matches the world. */
      y: pad + (1 - fy) * innerH,
    };
  }

  function visiblePoints(points, uptoTs) {
    return (points || []).filter(function (p) {
      return Number(p.ts) <= Number(uptoTs);
    });
  }

  function syncLabel(snapshot, nowTs) {
    const snap = snapshot || {};
    if (!snap.report) {
      return "尚无上报";
    }
    return snap.fresh ? "已同步" : "未同步";
  }

  function outOfMapNotice(report) {
    if (report && report.out_of_map) {
      return "当前位置在地图覆盖范围之外，位置不会同步到智能体";
    }
    return "";
  }

  return {
    ACTION_TAGS: ACTION_TAGS,
    TAG_LABELS: TAG_LABELS,
    buildReport: buildReport,
    dropSynced: dropSynced,
    trailBounds: trailBounds,
    projectPoint: projectPoint,
    visiblePoints: visiblePoints,
    syncLabel: syncLabel,
    outOfMapNotice: outOfMapNotice,
  };
}));
