/**
 * GAWorld help tooltips — self-contained "?" hover explanations.
 *
 * Drop-in: include this script on any page. Mark up a trigger with
 *   <span class="help-tip" data-help="说明文本"></span>
 * (the "?" glyph is filled in automatically), or add data-help to any
 * existing element to turn it into a trigger. Injects its own styles so
 * no extra stylesheet is required. Reusable across dashboard / studio /
 * simulation pages.
 */
(function () {
  "use strict";
  if (window.__helpTipInit) return;
  window.__helpTipInit = true;

  var CSS = [
    ".help-tip{display:inline-flex;align-items:center;justify-content:center;",
    "width:16px;height:16px;margin-left:5px;border-radius:50%;",
    "border:1px solid #9aa8a0;color:#7c8a82;background:#fff;",
    "font-size:11px;font-weight:800;line-height:1;cursor:help;opacity:.85;",
    "vertical-align:middle;user-select:none;flex:0 0 auto;transition:all .15s ease;}",
    ".help-tip:hover,.help-tip:focus{opacity:1;border-color:#0e7a58;color:#0e7a58;outline:none;}",
    ".help-pop{position:fixed;z-index:2000;max-width:288px;padding:9px 12px;",
    "border-radius:10px;background:#17251f;color:#eaf7f0;font-size:12.5px;",
    "line-height:1.6;font-weight:500;box-shadow:0 12px 34px rgba(10,30,22,.32);",
    "opacity:0;transform:translateY(4px);transition:opacity .14s ease,transform .14s ease;",
    "pointer-events:none;white-space:normal;}",
    ".help-pop.show{opacity:1;transform:translateY(0);}"
  ].join("");

  var style = document.createElement("style");
  style.textContent = CSS;
  (document.head || document.documentElement).appendChild(style);

  var pop = null;
  function ensurePop() {
    if (!pop) {
      pop = document.createElement("div");
      pop.className = "help-pop";
      document.body.appendChild(pop);
    }
    return pop;
  }

  function position(el, p) {
    var r = el.getBoundingClientRect();
    p.style.left = "0px";
    p.style.top = "0px";
    var pr = p.getBoundingClientRect();
    var left = r.left + r.width / 2 - pr.width / 2;
    var top = r.bottom + 8;
    if (top + pr.height > window.innerHeight - 8) top = r.top - pr.height - 8;
    left = Math.max(8, Math.min(left, window.innerWidth - pr.width - 8));
    p.style.left = Math.round(left) + "px";
    p.style.top = Math.round(top) + "px";
  }

  function show(el) {
    var text = el.getAttribute("data-help");
    if (!text) return;
    var p = ensurePop();
    p.textContent = text;
    p.classList.add("show");
    position(el, p);
  }
  function hide() {
    if (pop) pop.classList.remove("show");
  }

  function wire(el) {
    if (el.__helpWired) return;
    el.__helpWired = true;
    if (el.classList.contains("help-tip") && !el.textContent.trim()) el.textContent = "?";
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
    if (!el.hasAttribute("role")) el.setAttribute("role", "button");
    if (!el.hasAttribute("aria-label")) el.setAttribute("aria-label", el.getAttribute("data-help") || "help");
    el.addEventListener("mouseenter", function () { show(el); });
    el.addEventListener("mouseleave", hide);
    el.addEventListener("focus", function () { show(el); });
    el.addEventListener("blur", hide);
  }

  function scan(root) {
    (root || document).querySelectorAll("[data-help]").forEach(wire);
  }

  window.addEventListener("scroll", hide, true);

  window.HelpTips = { scan: scan };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { scan(); });
  } else {
    scan();
  }
})();
