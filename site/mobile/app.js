/* DOM wiring for the twin mobile client.
 *
 * Deliberately thin: everything worth testing lives in core.js. This file
 * holds only the browser-API glue a headless test cannot meaningfully drive —
 * Geolocation, IndexedDB, fetch, canvas, and event listeners.
 */
(function () {
  "use strict";

  const core = window.GAWorldTwinCore;
  const TOKEN_KEY = "gaworld.twin.token";
  const INTRO_KEY = "gaworld.twin.introSeen";
  const DB_NAME = "gaworld-twin";
  const STORE = "queue";
  const POLL_MS = 30000;

  let token = localStorage.getItem(TOKEN_KEY) || "";
  let selectedTag = "work";
  let trailPoints = [];

  const el = function (id) { return document.getElementById(id); };

  /* -- offline queue (IndexedDB) ------------------------------------- */

  function openDb() {
    return new Promise(function (resolve, reject) {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = function () {
        request.result.createObjectStore(STORE, {keyPath: "report_id"});
      };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }

  function queueTx(mode, fn) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        const tx = db.transaction(STORE, mode);
        const result = fn(tx.objectStore(STORE));
        tx.oncomplete = function () { resolve(result && result.result); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }

  function enqueue(report) {
    return queueTx("readwrite", function (store) { return store.put(report); });
  }

  function readQueue() {
    return queueTx("readonly", function (store) { return store.getAll(); })
      .then(function (rows) { return rows || []; });
  }

  function removeSynced(ids) {
    return queueTx("readwrite", function (store) {
      ids.forEach(function (id) { store.delete(id); });
      return null;
    });
  }

  /* -- API ----------------------------------------------------------- */

  function api(path, options) {
    const opts = options || {};
    const headers = {"Content-Type": "application/json"};
    if (token) { headers.Authorization = "Bearer " + token; }
    return fetch(path, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    }).then(function (response) {
      return response.json().then(function (data) {
        return {status: response.status, data: data};
      });
    });
  }

  /* -- rendering ------------------------------------------------------ */

  function renderTagGrid() {
    const grid = el("tagGrid");
    grid.innerHTML = "";
    core.ACTION_TAGS.forEach(function (tag) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = core.TAG_LABELS[tag] || tag;
      button.setAttribute("aria-pressed", String(tag === selectedTag));
      button.addEventListener("click", function () {
        selectedTag = tag;
        renderTagGrid();
      });
      grid.appendChild(button);
    });
  }

  function renderSnapshot(snapshot) {
    const nowTs = Date.now() / 1000;
    const label = core.syncLabel(snapshot, nowTs);
    const badge = el("syncState");
    badge.textContent = label;
    badge.setAttribute("data-sync", label);

    const report = snapshot.report;
    el("avatar").setAttribute("data-state", report ? report.action_tag : "rest");
    el("currentState").textContent = report
      ? (core.TAG_LABELS[report.action_tag] || report.action_tag)
        + " · " + (report.node_id || "地图之外")
      : "还没有上报过";

    const notice = core.outOfMapNotice(report);
    el("notice").textContent = notice;
    el("notice").hidden = !notice;
  }

  function drawTrail(points) {
    const canvas = el("trail");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    if (!points.length) {
      ctx.fillStyle = "#97a3b4";
      ctx.font = "16px sans-serif";
      ctx.fillText("今日还没有轨迹", 20, 30);
      return;
    }
    const bounds = core.trailBounds(trailPoints.length ? trailPoints : points);
    const projected = points.map(function (p) {
      return core.projectPoint(p, bounds, w, h, 24);
    });

    ctx.strokeStyle = "#6ea8fe";
    ctx.lineWidth = 2;
    ctx.beginPath();
    projected.forEach(function (pt, i) {
      if (i === 0) { ctx.moveTo(pt.x, pt.y); } else { ctx.lineTo(pt.x, pt.y); }
    });
    ctx.stroke();

    projected.forEach(function (pt, i) {
      const last = i === projected.length - 1;
      ctx.beginPath();
      ctx.fillStyle = last ? "#5cc2a8" : "#2c3644";
      ctx.arc(pt.x, pt.y, last ? 7 : 4, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  /* Temporal animation: replay the day's points along their own timeline. */
  function replayTrail() {
    if (trailPoints.length < 2) { drawTrail(trailPoints); return; }
    let index = 1;
    const timer = setInterval(function () {
      drawTrail(trailPoints.slice(0, index));
      index += 1;
      if (index > trailPoints.length) { clearInterval(timer); }
    }, 240);
  }

  /* -- flows ---------------------------------------------------------- */

  function refresh() {
    if (!token) { return Promise.resolve(); }
    return Promise.all([api("/api/twin/snapshot"), api("/api/twin/trail")])
      .then(function (results) {
        const snapshot = results[0];
        const trail = results[1];
        if (snapshot.status === 401 || trail.status === 401) {
          return signOut();
        }
        renderSnapshot(snapshot.data);
        trailPoints = (trail.data.points || []).filter(function (p) {
          return p.grid && !p.out_of_map;
        });
        drawTrail(trailPoints);
      })
      .catch(function () {
        /* Offline: keep the last render rather than blanking the screen. */
        el("syncState").textContent = "离线";
      });
  }

  function flushQueue() {
    return readQueue().then(function (queue) {
      if (!queue.length) {
        el("queueState").textContent = "";
        return null;
      }
      el("queueState").textContent = "待上传 " + queue.length + " 条";
      return api("/api/twin/report", {method: "POST", body: queue})
        .then(function (result) {
          if (result.status !== 200) { return null; }
          /* The server is idempotent on report_id, so everything we just sent
           * is now durable regardless of accepted-vs-duplicate. */
          const ids = queue.map(function (r) { return r.report_id; });
          return removeSynced(ids).then(function () {
            el("queueState").textContent = "";
            return refresh();
          });
        })
        .catch(function () {
          el("queueState").textContent = "待上传 " + queue.length + " 条（离线）";
        });
    });
  }

  function currentPosition() {
    return new Promise(function (resolve) {
      if (!navigator.geolocation) { return resolve(null); }
      navigator.geolocation.getCurrentPosition(
        function (position) { resolve(position.coords); },
        function () { resolve(null); },
        {enableHighAccuracy: true, timeout: 10000, maximumAge: 60000}
      );
    });
  }

  function submitReport() {
    const button = el("reportButton");
    button.disabled = true;
    return currentPosition().then(function (coords) {
      if (!coords) {
        /* Permission denied or unavailable: the spec requires the feature to
         * keep working, so fall back to a manual fix at the last known node
         * rather than dropping the activity report. */
        el("notice").textContent = "无法获取定位，本次仅上报行为";
        el("notice").hidden = false;
        coords = {latitude: 0, longitude: 0, accuracy: 0};
      }
      const report = core.buildReport({
        reportId: (crypto.randomUUID && crypto.randomUUID())
          || String(Date.now()) + Math.random().toString(16).slice(2),
        ts: Math.floor(Date.now() / 1000),
        tzOffset: -new Date().getTimezoneOffset(),
        coords: coords,
        tag: selectedTag,
        note: el("noteInput").value,
        manual: !coords.accuracy,
      });
      return enqueue(report)
        .then(flushQueue)
        .then(function () { el("noteInput").value = ""; });
    }).finally(function () {
      button.disabled = false;
    });
  }

  function showAuthGate() {
    el("intro").hidden = true;
    el("authGate").hidden = false;
  }

  function dismissIntro() {
    localStorage.setItem(INTRO_KEY, "1");
    showAuthGate();
  }

  function signOut() {
    token = "";
    localStorage.removeItem(TOKEN_KEY);
    el("main").hidden = true;
    /* Signing out returns to the gate, not the intro: the user has already
     * seen the explainer and just needs to re-enter a code. */
    showAuthGate();
  }

  function signIn() {
    const code = el("codeInput").value.trim();
    if (!code) { return; }
    el("authError").textContent = "";
    api("/api/twin/auth", {method: "POST", body: {code: code}})
      .then(function (result) {
        if (result.status !== 200 || !result.data.token) {
          el("authError").textContent = "邀请码无效或已撤销";
          return;
        }
        token = result.data.token;
        localStorage.setItem(TOKEN_KEY, token);
        start();
      })
      .catch(function () {
        el("authError").textContent = "无法连接服务器";
      });
  }

  function start() {
    el("intro").hidden = true;
    el("authGate").hidden = true;
    el("main").hidden = false;
    renderTagGrid();
    api("/api/twin/profile").then(function (result) {
      if (result.status === 401) { return signOut(); }
      el("avatar").innerHTML = result.data.avatar_svg || "";
      el("agentLabel").textContent = result.data.label
        || ("Agent " + result.data.agent_id);
    });
    refresh();
    flushQueue();
    setInterval(function () { refresh(); flushQueue(); }, POLL_MS);
  }

  function init() {
    el("codeSubmit").addEventListener("click", signIn);
    el("introStart").addEventListener("click", dismissIntro);
    el("reportButton").addEventListener("click", submitReport);
    el("replayButton").addEventListener("click", replayTrail);
    window.addEventListener("online", flushQueue);

    if (token) {
      start();
    } else if (core.shouldShowIntro(!!token, !!localStorage.getItem(INTRO_KEY))) {
      el("intro").hidden = false;
    } else {
      showAuthGate();
    }

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("sw.js").catch(function () {});
    }
  }

  document.addEventListener("DOMContentLoaded", init);
}());
