/* Headless render + round-trip check for the Studio 家庭 editor.
 *
 *   node --test site/dashboard/studio-family.test.js
 *
 * Same slicing technique as family-card.test.js: studio.js touches too much
 * DOM at load to boot headlessly, so the editor's own block is evaluated
 * against stubs. Two things are worth this test:
 *
 * 1. **The tri-state.** `children: null` means "sample it", `children: []`
 *    means "pinned to none". Collapsing those two in the draft→wire
 *    conversion would silently turn "this couple has no children" into
 *    "generate some", and the operator would only find out a run later.
 * 2. **Escaping.** Names here are operator input on their way to innerHTML.
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const STUDIO = fs.readFileSync(path.join(__dirname, "studio.js"), "utf8");

const START = "const MARITAL_LABELS = {";
const END = "async function saveFamilyOverride";

function familyBlock() {
  const start = STUDIO.indexOf(START);
  assert.notEqual(start, -1, "family editor block not found in studio.js");
  const end = STUDIO.indexOf(END);
  assert.notEqual(end, -1, "saveFamilyOverride not found in studio.js");
  assert.ok(end > start, "unexpected ordering in studio.js");
  return STUDIO.slice(start, end);
}

function boot(overrides, preview) {
  const store = {
    creating: false,
    currentId: 13,
    familyPreview: preview,
    familyDraft: null,
  };
  const esc = (text) =>
    String(text == null ? "" : text).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );
  const api = async () => ({});
  const $ = () => null;
  const factory = new Function(
    "store",
    "esc",
    "api",
    "$",
    `${familyBlock()}\n return { blankFamilyDraft, familyDraftToOverride, familyCard };`
  );
  const mod = factory(store, esc, api, $);
  store.familyDraft = mod.blankFamilyDraft(overrides);
  return { store, mod };
}

const PREVIEW = {
  selected: {
    agent_id: 13,
    name: "蒋昊",
    household_id: "hh_001",
    household_type: "nuclear",
    marital_status: "married",
    brief: "已婚；核心家庭。配偶叶嘉宁（34岁，同住）",
    pinned: true,
  },
  candidates: [{ agent_id: 16, name: "叶嘉宁", age: 34, gender: "女", residence: "西湖·文新" }],
  duties: { weekday: ["晚上尽量回家和伴侣一起吃晚饭"], weekend: [] },
  warnings: [],
  override: {},
};

test("an unpinned agent starts in fully-automatic mode", () => {
  const { store } = boot(null, PREVIEW);
  assert.equal(store.familyDraft.marital_status, "");
  assert.equal(store.familyDraft.partnerMode, "auto");
  assert.equal(store.familyDraft.children, null);
  assert.equal(store.familyDraft.elders, null);
});

test("an existing override round-trips through the draft unchanged", () => {
  const override = {
    marital_status: "married",
    partner: { kind: "agent", agent_id: 16, role: "spouse" },
    children: [{ name: "蒋荷", gender: "女", age: 2, coresident: true, role: "child" }],
  };
  const { store, mod } = boot(override, PREVIEW);
  const wire = mod.familyDraftToOverride(store.familyDraft);
  assert.equal(wire.marital_status, "married");
  assert.deepEqual(wire.partner, { kind: "agent", agent_id: 16, role: "spouse" });
  assert.equal(wire.children.length, 1);
  assert.equal(wire.children[0].name, "蒋荷");
});

test("pinned-to-none survives the round trip as an empty list, not as null", () => {
  const { store, mod } = boot({ children: [] }, PREVIEW);
  assert.deepEqual(store.familyDraft.children, []);
  const wire = mod.familyDraftToOverride(store.familyDraft);
  assert.ok("children" in wire, "an empty pin must still be sent");
  assert.deepEqual(wire.children, []);
});

test("automatic children are omitted from the wire payload entirely", () => {
  const { store, mod } = boot(null, PREVIEW);
  const wire = mod.familyDraftToOverride(store.familyDraft);
  assert.ok(!("children" in wire), "an unpinned list must not be sent as []");
});

test("pinning no partner sends an explicit null", () => {
  const { store, mod } = boot({ partner: null }, PREVIEW);
  assert.equal(store.familyDraft.partnerMode, "none");
  const wire = mod.familyDraftToOverride(store.familyDraft);
  assert.ok("partner" in wire);
  assert.equal(wire.partner, null);
});

test("an off-screen partner keeps its name, age and gender", () => {
  const override = {
    partner: { kind: "ghost", name: "周敏", gender: "女", age: 41, role: "spouse" },
  };
  const { store, mod } = boot(override, PREVIEW);
  assert.equal(store.familyDraft.partnerMode, "ghost");
  const wire = mod.familyDraftToOverride(store.familyDraft);
  assert.equal(wire.partner.kind, "ghost");
  assert.equal(wire.partner.name, "周敏");
  assert.equal(wire.partner.age, 41);
});

test("the card renders the current family, the tags and the duties", () => {
  const { mod } = boot(null, PREVIEW);
  const html = mod.familyCard();
  assert.match(html, /已婚/);
  assert.match(html, /核心家庭/);
  assert.match(html, /已固定/);
  assert.match(html, /叶嘉宁/);
  assert.match(html, /工作日/);
  assert.match(html, /family_overrides\.json/);
  assert.match(html, /saveFamilyBtn/);
  assert.match(html, /resetFamilyBtn/);
});

test("the card degrades instead of throwing", () => {
  const { mod } = boot(null, null);
  assert.match(mod.familyCard(), /加载中/);
  const failed = boot(null, { error: "boom" });
  assert.match(failed.mod.familyCard(), /boom/);
});

test("a conflicting pin is surfaced, not swallowed", () => {
  const preview = Object.assign({}, PREVIEW, {
    warnings: ["居民 1 指定配偶为 2，但 2 指定的是 3；按 id 从小到大解析，后来的那条会被忽略。"],
  });
  const { mod } = boot(null, preview);
  assert.match(mod.familyCard(), /后来的那条会被忽略/);
});

test("operator-typed names are escaped", () => {
  const hostile = {
    children: [
      { name: '<img src=x onerror="alert(1)">', gender: "女", age: 3, coresident: true },
    ],
  };
  const preview = JSON.parse(JSON.stringify(PREVIEW));
  preview.selected.brief = "<b>不该加粗</b>";
  preview.candidates[0].name = "<script>bad()</script>";
  const { mod } = boot(hostile, preview);
  const html = mod.familyCard();
  assert.ok(!html.includes("<img src=x"), "child name was not escaped");
  assert.ok(!html.includes("<b>不该加粗"), "brief was not escaped");
  assert.match(html, /&lt;img src=x/);
});
