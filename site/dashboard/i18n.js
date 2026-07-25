/**
 * GAWorld i18n — lightweight vanilla-JS internationalization.
 *
 * Supports English (en) and Chinese (zh-CN) via JSON locale files.
 * No dependencies, no build step.
 */
(function () {
  "use strict";

  const STORAGE_KEY = "gaworld-lang";
  const DEFAULT_LOCALE = "zh-CN";
  const LOCALE_MAP = { en: "en", zh: "zh-CN", "zh-CN": "zh-CN" };

  let currentLocale = null;
  let translations = {};

  function normalize(locale) {
    return LOCALE_MAP[locale] || DEFAULT_LOCALE;
  }

  function storageAvailable() {
    try {
      const k = "__test__";
      localStorage.setItem(k, "1");
      localStorage.removeItem(k);
      return true;
    } catch (_) {
      return false;
    }
  }

  async function loadLocale(locale) {
    const url = "/site/dashboard/locales/" + locale + ".json";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("Failed to load locale: " + url);
    return resp.json();
  }

  window.__ = function (key) {
    if (translations[key] !== undefined) return translations[key];
    return key;
  };

  window.__f = function (key, params) {
    var t = window.__(key);
    if (params) {
      for (var k in params) {
        if (params.hasOwnProperty(k)) {
          t = t.split("{" + k + "}").join(String(params[k]));
        }
      }
    }
    return t;
  };

  window.setLocale = async function (locale) {
    var code = normalize(locale);
    if (code === currentLocale) return;
    try {
      var data = await loadLocale(code);
      translations = data;
      currentLocale = code;
      if (storageAvailable()) {
        localStorage.setItem(STORAGE_KEY, code);
      }
      applyTranslations();
      document.dispatchEvent(new CustomEvent("locale-changed", { detail: { locale: code } }));
    } catch (err) {
      console.error("i18n: Failed to set locale", err);
    }
  };

  window.getLocale = function () {
    return currentLocale;
  };

  window.applyTranslations = function () {
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      if (key) {
        var t = window.__(key);
        if (t !== key) el.textContent = t;
      }
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
      var key = el.getAttribute("data-i18n-placeholder");
      if (key) {
        var t = window.__(key);
        if (t !== key) el.placeholder = t;
      }
    });
    document.querySelectorAll("[data-i18n-content]").forEach(function (el) {
      var key = el.getAttribute("data-i18n-content");
      if (key) {
        var t = window.__(key);
        if (t !== key) el.setAttribute("content", t);
      }
    });
    document.querySelectorAll("[data-i18n-title]").forEach(function (el) {
      var key = el.getAttribute("data-i18n-title");
      if (key) {
        var t = window.__(key);
        if (t !== key) el.title = t;
      }
    });
    var enBtn = document.getElementById("lang-en-btn");
    var zhBtn = document.getElementById("lang-zh-btn");
    if (enBtn && zhBtn) {
      enBtn.textContent = window.__("lang.en");
      zhBtn.textContent = window.__("lang.zh");
      enBtn.classList.toggle("active", currentLocale === "en");
      zhBtn.classList.toggle("active", currentLocale === "zh-CN");
    }
  };

  function injectLangSwitcher() {
    var masthead = document.querySelector(".masthead");
    if (!masthead) return;
    var wrap = document.createElement("div");
    wrap.className = "lang-switcher-wrap";
    var enBtn = document.createElement("button");
    enBtn.id = "lang-en-btn";
    enBtn.className = "lang-switcher";
    enBtn.textContent = "EN";
    enBtn.addEventListener("click", function () { window.setLocale("en"); });
    var zhBtn = document.createElement("button");
    zhBtn.id = "lang-zh-btn";
    zhBtn.className = "lang-switcher";
    zhBtn.textContent = "CN";
    zhBtn.addEventListener("click", function () { window.setLocale("zh-CN"); });
    wrap.appendChild(enBtn);
    wrap.appendChild(zhBtn);
    masthead.appendChild(wrap);
  }

  async function init() {
    injectLangSwitcher();
    var saved = storageAvailable() ? localStorage.getItem(STORAGE_KEY) : null;
    var initial = normalize(saved || DEFAULT_LOCALE);
    try {
      var data = await loadLocale(initial);
      translations = data;
      currentLocale = initial;
    } catch (_) {
      currentLocale = DEFAULT_LOCALE;
      translations = {};
    }
    applyTranslations();
    document.dispatchEvent(new CustomEvent("locale-changed", { detail: { locale: currentLocale } }));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
