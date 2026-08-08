"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const core = require("./core.js");


test("buildReport assembles the server's expected shape", () => {
  const report = core.buildReport({
    reportId: "abc",
    ts: 1000,
    tzOffset: 480,
    coords: {latitude: 30.27, longitude: 120.15, accuracy: 12},
    tag: "work",
    note: "  加班  ",
  });
  assert.equal(report.report_id, "abc");
  assert.equal(report.ts, 1000);
  assert.equal(report.tz_offset, 480);
  assert.equal(report.loc.lat, 30.27);
  assert.equal(report.loc.lng, 120.15);
  assert.equal(report.loc.acc_m, 12);
  assert.equal(report.loc.source, "gps");
  assert.equal(report.action_tag, "work");
  assert.equal(report.note, "加班");
});


test("buildReport marks manual fixes so the server can tell them apart", () => {
  const report = core.buildReport({
    reportId: "abc", ts: 1000, tzOffset: 0,
    coords: {latitude: 1, longitude: 2, accuracy: null},
    tag: "rest", note: "", manual: true,
  });
  assert.equal(report.loc.source, "manual");
  assert.equal(report.loc.acc_m, 0);
});


test("buildReport falls back to the other tag for an unknown one", () => {
  const report = core.buildReport({
    reportId: "a", ts: 1, tzOffset: 0,
    coords: {latitude: 1, longitude: 2, accuracy: 1},
    tag: "nonsense", note: "",
  });
  assert.equal(report.action_tag, "other");
});


test("queue drops reports the server has accepted, keeping the rest", () => {
  const queue = [{report_id: "a"}, {report_id: "b"}, {report_id: "c"}];
  assert.deepEqual(core.dropSynced(queue, ["a", "c"]), [{report_id: "b"}]);
});


test("queue is unchanged when nothing synced", () => {
  const queue = [{report_id: "a"}];
  assert.deepEqual(core.dropSynced(queue, []), [{report_id: "a"}]);
});


test("trailBounds covers every point with a non-zero span", () => {
  const bounds = core.trailBounds([
    {grid: {x: 0, y: 0}},
    {grid: {x: 4, y: 2}},
  ]);
  assert.equal(bounds.minX, 0);
  assert.equal(bounds.maxX, 4);
  assert.equal(bounds.minY, 0);
  assert.equal(bounds.maxY, 2);
});


test("trailBounds pads a single point so projection cannot divide by zero", () => {
  const bounds = core.trailBounds([{grid: {x: 3, y: 3}}]);
  assert.ok(bounds.maxX > bounds.minX);
  assert.ok(bounds.maxY > bounds.minY);
});


test("trailBounds on no points returns a usable unit box", () => {
  const bounds = core.trailBounds([]);
  assert.ok(bounds.maxX > bounds.minX);
  assert.ok(bounds.maxY > bounds.minY);
});


test("projectPoint maps grid coordinates into canvas pixels", () => {
  const bounds = {minX: 0, maxX: 10, minY: 0, maxY: 10};
  const mid = core.projectPoint({grid: {x: 5, y: 5}}, bounds, 100, 100, 0);
  assert.equal(mid.x, 50);
  assert.equal(mid.y, 50);
});


test("projectPoint flips the y axis so north is up", () => {
  const bounds = {minX: 0, maxX: 10, minY: 0, maxY: 10};
  const low = core.projectPoint({grid: {x: 0, y: 0}}, bounds, 100, 100, 0);
  const high = core.projectPoint({grid: {x: 0, y: 10}}, bounds, 100, 100, 0);
  assert.ok(high.y < low.y);
});


test("projectPoint honours padding", () => {
  const bounds = {minX: 0, maxX: 10, minY: 0, maxY: 10};
  const corner = core.projectPoint({grid: {x: 0, y: 0}}, bounds, 100, 100, 10);
  assert.equal(corner.x, 10);
});


test("visiblePoints returns the prefix up to a timestamp", () => {
  const points = [{ts: 1}, {ts: 2}, {ts: 3}];
  assert.deepEqual(core.visiblePoints(points, 2), [{ts: 1}, {ts: 2}]);
});


test("visiblePoints on an empty trail is empty", () => {
  assert.deepEqual(core.visiblePoints([], 5), []);
});


test("syncLabel reports synced state when the server says fresh", () => {
  assert.equal(core.syncLabel({fresh: true, report: {ts: 100}}, 160), "已同步");
});


test("syncLabel reports not-synced rather than showing a stale position", () => {
  assert.equal(core.syncLabel({fresh: false, report: {ts: 100}}, 99999), "未同步");
});


test("syncLabel handles an agent that has never reported", () => {
  assert.equal(core.syncLabel({fresh: false, report: null}, 100), "尚无上报");
});


test("outOfMapNotice appears only for an out-of-map report", () => {
  assert.ok(core.outOfMapNotice({out_of_map: true}));
  assert.equal(core.outOfMapNotice({out_of_map: false}), "");
  assert.equal(core.outOfMapNotice(null), "");
});
