/*
 * tcl-departures-card \u2014 affichage plein \u00e9cran des prochains d\u00e9parts TCL.
 * Fonctionne avec l'int\u00e9gration "tcl_lyon".
 */
const MAPLIBRE_BASE = "/tcl_lyon/maplibre";

let _maplibrePromise;
function loadMaplibre() {
  if (window.maplibregl) return Promise.resolve(window.maplibregl);
  if (!_maplibrePromise) {
    _maplibrePromise = new Promise((resolve, reject) => {
      const sc = document.createElement("script");
      sc.src = `${MAPLIBRE_BASE}/maplibre-gl.js`;
      sc.onload = () => resolve(window.maplibregl);
      sc.onerror = (e) => { _maplibrePromise = null; reject(e); };
      document.head.appendChild(sc);
    });
  }
  return _maplibrePromise;
}

function mapStyle(kind) {
  const light = kind === "light";
  const tiles = light
    ? ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"]
    : ["a", "b", "c", "d"].map((s) => `https://${s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png`);
  return {
    version: 8,
    sources: {
      base: {
        type: "raster",
        tiles,
        tileSize: 256,
        maxzoom: 19,
        attribution: light
          ? "\u00a9 OpenStreetMap contributors"
          : "\u00a9 OpenStreetMap contributors \u00a9 CARTO",
      },
    },
    layers: [{ id: "base", type: "raster", source: "base" }],
  };
}

const TCL_COLORS = {
  A: "#E2001A", B: "#0067B2", C: "#F39200", D: "#009B3A",
  F1: "#8DC63F", F2: "#8DC63F", RX: "#E30613",
};
const TCL_DEFAULT = { metroText: "#fff", tram: "#7A2A84", chrono: "#D5007F", bus: "#E4002B" };

function displayLine(ligne) {
  const l = String(ligne || "").toUpperCase().trim();
  const m = l.match(/^(.*\d)[AR]$/);
  return m ? m[1] : l;
}

function lineColor(ligne, custom) {
  if (custom && custom[ligne]) return custom[ligne];
  const l = displayLine(ligne);
  if (custom && custom[ligne]) return custom[ligne];
  if (custom && custom[l]) return custom[l];
  if (TCL_COLORS[l]) return TCL_COLORS[l];
  if (/^T\d/.test(l)) return TCL_DEFAULT.tram;
  if (/^C\d/.test(l)) return TCL_DEFAULT.chrono;
  return TCL_DEFAULT.bus;
}

class TclDeparturesCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      title: "Prochains d\u00e9parts",
      max_departures: 3,
      fullscreen: true,
      show_clock: true,
      show_stop: true,
      hide_empty: false,
      show_alerts: true,
      popup_timeout: 60,
      map_style: "dark",
      colors: {},
      ...config,
    };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._built = false;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    this._timer = setInterval(() => this._render(), 10000);
  }
  disconnectedCallback() {
    clearInterval(this._timer);
    this._closeMap();
  }

  getCardSize() { return 8; }
  static getStubConfig() { return { title: "Prochains d\u00e9parts" }; }

  _entities() {
    const hass = this._hass;
    if (!hass) return [];
    let ids = this._config.entities;
    if (!ids || !ids.length) {
      ids = Object.keys(hass.states).filter(
        (id) => id.startsWith("sensor.") && hass.states[id].attributes.integration === "tcl_lyon"
      );
    }
    return ids
      .map((e) => (typeof e === "string" ? e : e.entity))
      .map((id) => hass.states[id])
      .filter(Boolean);
  }

  _minutes(dep, now) {
    const t = Date.parse(dep.heure);
    if (isNaN(t)) return dep.minutes;
    return Math.max(0, Math.floor((t - now) / 60000));
  }

  _fmt(min) {
    if (min <= 0) return { big: "Proche", small: "" };
    if (min >= 60) {
      return { big: `${Math.floor(min / 60)}h${String(min % 60).padStart(2, "0")}`, small: "" };
    }
    return { big: String(min), small: "min" };
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const cfg = this._config;
    const now = Date.now();
    const states = this._entities();

    const velov = states.filter((s) => s.attributes.type === "velov");
    const rows = states
      .filter((s) => s.attributes.type !== "velov")
      .map((st) => {
        const a = st.attributes;
        const deps = (a.departs || [])
          .filter((d) => Date.parse(d.heure) >= now - 60000 || isNaN(Date.parse(d.heure)))
          .slice(0, cfg.max_departures);
        return { st, a, deps, first: deps.length ? this._minutes(deps[0], now) : Infinity };
      })
      .filter((r) => !(cfg.hide_empty && !r.deps.length));
    if (cfg.sort !== "config") rows.sort((x, y) => x.first - y.first);

    const lastUpdate = states.reduce(
      (m, s) => Math.max(m, Date.parse(s.last_updated) || 0), 0);
    const stale = lastUpdate && now - lastUpdate > 5 * 60000;
    const clock = new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

    const velovHtml = velov.map((st) => {
      const a = st.attributes;
      const closed = a.statut && !/open|ouvert/i.test(a.statut);
      const bikes = st.state === "unavailable" || st.state === "unknown" ? "\u2013" : st.state;
      return `<div class="row">
          <div class="badge velov">V\u00e9lo'v</div>
          <div class="info">
            <div class="dir">${esc(a.station || "")}</div>
            <div class="stop">${closed ? '<span class="warn">Station ferm\u00e9e</span>'
              : a.places != null ? `${a.places} places libres` : ""}</div>
          </div>
          <div class="times">
            ${a.velos_electriques != null
              ? `<div class="time"><span class="num">${a.velos_electriques}</span><span class="unit">\u26a1</span></div>` : ""}
            <div class="time first"><span class="num">${bikes}</span><span class="unit">v\u00e9los</span></div>
          </div>
        </div>`;
    }).join("");

    const rowHtml = rows.map(({ st, a, deps }) => {
      const color = lineColor(a.ligne, cfg.colors);
      const alertes = cfg.show_alerts ? (a.alertes || []) : [];
      const times = deps.length
        ? deps.map((d, i) => {
            const f = this._fmt(this._minutes(d, now));
            const dir = !a.direction && d.direction
              ? `<span class="subdir">${esc(d.direction)}</span>` : "";
            return `<div class="time ${i === 0 ? "first" : ""}">
                <span class="num">${f.big}</span><span class="unit">${f.small}</span>
                ${d.temps_reel ? '<span class="rt" title="Temps r\u00e9el"></span>' : ""}
                ${dir}
              </div>`;
          }).join("")
        : `<div class="none">Aucun d\u00e9part pr\u00e9vu</div>`;
      return `<div class="row" data-map="${esc(st.entity_id)}">
          <div class="badge" style="background:${color}">${esc(displayLine(a.ligne))}</div>
          <div class="info">
            <div class="dir">${esc(a.direction || "Toutes directions")}</div>
            ${alertes.length
              ? `<div class="alert">\u26a0 ${esc(alertes.map((x) => x.titre || x.message).join(" \u00b7 "))}</div>`
              : cfg.show_stop ? `<div class="stop">${esc(a.arret || "")}</div>` : ""}
          </div>
          <div class="times">${times}</div>
        </div>`;
    }).join("") + velovHtml;

    if (!this._built) this._build();
    const $ = (q) => this.shadowRoot.querySelector(q);
    $("h1").textContent = cfg.title || "";
    if (cfg.show_clock) $(".clock").textContent = clock;
    $(".list").innerHTML = rowHtml || `<div class="empty">Aucune ligne suivie.<br>Ajoute des lignes dans
            Param\u00e8tres \u2192 Appareils et services \u2192 TCL Lyon \u2192 Configurer.</div>`;
    $("footer").innerHTML = `
          <span><span style="color:#4caf50">\u25cf</span> temps r\u00e9el &nbsp; sinon horaire th\u00e9orique</span>
          <span class="${stale ? "warn" : ""}">${lastUpdate
            ? (stale ? "Donn\u00e9es anciennes \u2014 " : "") + "MAJ " +
              new Date(lastUpdate).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })
            : ""}</span>`;
    if (this._mapEntity) this._updateModal();
  }

  _build() {
    this._built = true;
    this._closeMap();
    this.shadowRoot.innerHTML = `
      <link rel="stylesheet" href="${MAPLIBRE_BASE}/maplibre-gl.css">
      <style>
        :host { display:block; }
        .wrap {
          box-sizing:border-box; background:#111418; color:#f2f2f2;
          font-family: "Roboto", "Helvetica Neue", Arial, sans-serif;
          display:flex; flex-direction:column; padding:2.2vh 2.5vw; gap:1.6vh;
          ${this._config.fullscreen
            ? "position:fixed; inset:0; z-index:9; width:100vw; height:100vh;"
            : "position:relative; border-radius:12px; min-height:300px;"}
        }
        header { display:flex; align-items:baseline; justify-content:space-between; }
        h1 { margin:0; font-size:clamp(20px,4.2vh,44px); font-weight:500; letter-spacing:.5px; }
        .clock { font-size:clamp(28px,7vh,72px); font-weight:300; font-variant-numeric:tabular-nums; }
        .list { flex:1; display:flex; flex-direction:column; gap:1.4vh; overflow:hidden; }
        .row {
          display:flex; align-items:center; gap:2vw; background:#1d2228;
          border-radius:14px; padding:1.6vh 1.8vw; flex:1 1 0; max-height:20vh; min-height:0;
        }
        .badge {
          min-width:clamp(56px,11vh,120px); height:clamp(56px,11vh,120px); border-radius:12px;
          display:flex; align-items:center; justify-content:center; color:#fff;
          font-size:clamp(24px,6vh,64px); font-weight:700; padding:0 .6vw; box-sizing:border-box;
        }
        .badge.velov { background:#E2001A; font-size:clamp(14px,3vh,32px); }
        .alert { font-size:clamp(13px,2.6vh,28px); color:#ffab40; margin-top:.4vh;
                 white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .warn { color:#ff7043; }
        .info { flex:1; min-width:0; }
        .dir { font-size:clamp(20px,4.8vh,52px); font-weight:500;
               white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .stop { font-size:clamp(13px,2.6vh,28px); color:#9aa4ae; margin-top:.4vh;
                white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .times { display:flex; align-items:baseline; gap:2.4vw; }
        .time { position:relative; display:flex; align-items:baseline; gap:.3vw; color:#9aa4ae;
                flex-wrap:wrap; justify-content:flex-end; max-width:22vw; }
        .time .num { font-size:clamp(22px,5vh,54px); font-weight:500; font-variant-numeric:tabular-nums; }
        .time .unit { font-size:clamp(12px,2.4vh,26px); }
        .time.first { color:#ffd54a; }
        .time.first .num { font-size:clamp(34px,9vh,100px); font-weight:700; }
        .time.first .unit { font-size:clamp(14px,3vh,32px); }
        .subdir { width:100%; text-align:right; font-size:clamp(10px,1.8vh,20px); color:#9aa4ae;
                  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .rt { position:absolute; top:-.4vh; right:-1vw; width:1.2vh; height:1.2vh; border-radius:50%;
              background:#4caf50; animation:pulse 2s infinite; }
        @keyframes pulse { 50% { opacity:.25; } }
        .none { color:#9aa4ae; font-size:clamp(16px,3vh,32px); }
        .empty { margin:auto; text-align:center; color:#9aa4ae; font-size:clamp(16px,3.5vh,36px); }
        footer { display:flex; justify-content:space-between; font-size:clamp(11px,2vh,22px); color:#6f7a85; }
        footer .warn { color:#ff7043; }

        .row[data-map] { cursor:pointer; }
        .row[data-map]:active { background:#262d35; }
        .modal { position:absolute; inset:2.5vh 2.5vw; z-index:5; background:#111418;
                 border-radius:16px; box-shadow:0 10px 40px rgba(0,0,0,.6);
                 display:flex; flex-direction:column; overflow:hidden; }
        .modal[hidden] { display:none; }
        .mhead { display:flex; align-items:center; gap:1.6vw; padding:1.4vh 1.6vw; background:#1d2228; }
        .mhead .badge { min-width:clamp(40px,8vh,90px); height:clamp(40px,8vh,90px);
                        font-size:clamp(18px,4.4vh,48px); }
        .mhead .info .dir { font-size:clamp(18px,4vh,44px); }
        .mhead .mtimes { display:flex; gap:1.6vw; color:#ffd54a; font-size:clamp(18px,4.4vh,48px);
                         font-weight:700; font-variant-numeric:tabular-nums; }
        .mhead .mtimes span + span { color:#9aa4ae; font-weight:500; }
        .close { background:#2c333b; color:#fff; border:0; border-radius:50%;
                 width:clamp(40px,8vh,80px); height:clamp(40px,8vh,80px);
                 font-size:clamp(20px,4.4vh,44px); cursor:pointer; flex:none; }
        .mapbox { position:relative; flex:1; min-height:0; }
        .map { position:absolute; inset:0; background:#1a1f24; }
        .mmsg { position:absolute; left:50%; top:1.5vh; transform:translateX(-50%); z-index:2;
                background:rgba(17,20,24,.88); padding:.8vh 1.4vw; border-radius:10px;
                font-size:clamp(13px,2.4vh,26px); color:#e0e0e0; white-space:nowrap; }
        .mmsg:empty { display:none; }
        .veh { position:relative; width:clamp(30px,5.4vh,56px); height:clamp(30px,5.4vh,56px); }
        .veh .dot { position:absolute; inset:0; border-radius:50%; border:3px solid #fff;
                    display:flex; align-items:center; justify-content:center; color:#fff;
                    font:700 clamp(10px,2vh,20px) Roboto, Arial, sans-serif;
                    box-shadow:0 2px 8px rgba(0,0,0,.5); }
        .veh .arrow { position:absolute; inset:-34%; pointer-events:none; }
        .veh .arrow::before { content:""; position:absolute; left:50%; top:0; transform:translateX(-50%);
                    border-left:9px solid transparent; border-right:9px solid transparent;
                    border-bottom:14px solid var(--c); }
        .stopmk { position:relative; }
        .stopmk .pin { width:clamp(22px,4vh,40px); height:clamp(22px,4vh,40px); border-radius:50%;
                       background:#fff; border:5px solid #111; box-shadow:0 0 0 3px #ffd54a; }
        .stopmk .lbl { position:absolute; top:100%; left:50%; transform:translateX(-50%); margin-top:4px; background:#ffd54a; color:#111; border-radius:6px; padding:1px 6px;
                       font:700 clamp(10px,2vh,20px) Roboto, Arial, sans-serif; white-space:nowrap; }
        .maplibregl-ctrl-attrib { font-size:10px; }
      </style>
      <div class="wrap">
        <header>
          <h1></h1>
          ${this._config.show_clock ? `<div class="clock"></div>` : ""}
        </header>
        <div class="list"></div>
        <footer></footer>
        <div class="modal" hidden>
          <div class="mhead">
            <div class="badge"></div>
            <div class="info"><div class="dir"></div><div class="stop"></div></div>
            <div class="mtimes"></div>
            <button class="close" aria-label="Fermer">\u2715</button>
          </div>
          <div class="mapbox"><div class="map"></div><div class="mmsg"></div></div>
        </div>
      </div>`;
    const root = this.shadowRoot;
    root.querySelector(".list").addEventListener("click", (ev) => {
      const row = ev.target.closest(".row[data-map]");
      if (row) this._openMap(row.dataset.map);
    });
    root.querySelector(".close").addEventListener("click", () => this._closeMap());
    root.querySelector(".modal").addEventListener("pointerdown", () => this._armTimeout());
  }

  /* ---------- Fen\u00eatre carte ---------- */

  _armTimeout() {
    clearTimeout(this._mapTimeout);
    const secs = Number(this._config.popup_timeout);
    if (secs > 0) this._mapTimeout = setTimeout(() => this._closeMap(), secs * 1000);
  }

  _openMap(entityId) {
    this._mapEntity = entityId;
    this._fitKey = null;
    this.shadowRoot.querySelector(".modal").hidden = false;
    this._armTimeout();
    this._updateModal();
  }

  _closeMap() {
    clearTimeout(this._mapTimeout);
    this._mapEntity = null;
    if (this._map) { this._map.remove(); this._map = null; }
    this._markers = {};
    this._stopMarker = null;
    const modal = this.shadowRoot && this.shadowRoot.querySelector(".modal");
    if (modal) modal.hidden = true;
  }

  async _updateModal() {
    const st = this._hass && this._hass.states[this._mapEntity];
    const $ = (q) => this.shadowRoot.querySelector(q);
    if (!st) return this._closeMap();
    const a = st.attributes;
    const cfg = this._config;
    const now = Date.now();
    const badge = $(".mhead .badge");
    badge.textContent = displayLine(a.ligne);
    badge.style.background = lineColor(a.ligne, cfg.colors);
    $(".mhead .dir").textContent = a.direction || "Toutes directions";
    $(".mhead .stop").textContent = a.arret || "";
    $(".mhead .mtimes").innerHTML = (a.departs || []).slice(0, 3)
      .map((d) => { const f = this._fmt(this._minutes(d, now)); return `<span>${f.big}${f.small ? " " + f.small : ""}</span>`; })
      .join("");
    const msg = $(".mmsg");

    if (!a.carte_disponible) {
      msg.textContent = a.carte_disponible === false && a.arret_position === undefined
        ? "Carte indisponible : renseigne l'URL des positions dans TCL Lyon \u2192 Configurer \u2192 Carte des bus"
        : "Position de l'arr\u00eat inconnue";
      return;
    }
    const vehicles = a.vehicules || [];
    msg.textContent = vehicles.length ? "" : "Aucun v\u00e9hicule en approche pour le moment";

    let maplibregl;
    try {
      maplibregl = await loadMaplibre();
    } catch (e) {
      msg.textContent = "Impossible de charger la carte";
      return;
    }
    if (this._mapEntity !== st.entity_id) return;

    const bearing = Number(cfg.map_bearing ?? a.carte_orientation ?? 0) || 0;
    const stop = [a.arret_position[1], a.arret_position[0]]; // [lon, lat]
    const color = lineColor(a.ligne, cfg.colors);

    if (!this._map) {
      this._map = new maplibregl.Map({
        container: $(".map"),
        style: mapStyle(cfg.map_style),
        center: stop,
        zoom: 15,
        bearing,
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        attributionControl: { compact: true },
      });
      this._map.touchZoomRotate.disableRotation();
      this._map.keyboard.disableRotation();
      this._markers = {};
      const el = document.createElement("div");
      el.innerHTML = `<div class="stopmk"><div class="pin"></div><div class="lbl">${esc(a.arret || "Arr\u00eat")}</div></div>`;
      this._stopMarker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat(stop).addTo(this._map);
    }

    // Marqueurs des v\u00e9hicules
    const seen = new Set();
    for (const v of vehicles) {
      seen.add(v.id);
      let mk = this._markers[v.id];
      if (!mk) {
        const el = document.createElement("div");
        el.innerHTML = `<div class="veh"><div class="arrow"></div><div class="dot"></div></div>`;
        mk = new maplibregl.Marker({ element: el }).setLngLat([v.lon, v.lat]).addTo(this._map);
        this._markers[v.id] = mk;
      }
      const el = mk.getElement().querySelector(".veh");
      el.style.setProperty("--c", color);
      el.querySelector(".dot").style.background = color;
      el.querySelector(".dot").textContent = displayLine(a.ligne);
      const arrow = el.querySelector(".arrow");
      arrow.style.display = v.cap == null ? "none" : "";
      arrow.style.transform = `rotate(${(v.cap || 0) - bearing}deg)`;
      mk.setLngLat([v.lon, v.lat]);
    }
    for (const id of Object.keys(this._markers)) {
      if (!seen.has(id)) { this._markers[id].remove(); delete this._markers[id]; }
    }

    // Cadrage : l'arr\u00eat + les v\u00e9hicules en approche. L'arr\u00eat se retrouve ainsi
    // naturellement dans un coin, du c\u00f4t\u00e9 oppos\u00e9 \u00e0 celui d'o\u00f9 arrivent les bus.
    const key = JSON.stringify(vehicles.map((v) => [v.id, v.lat.toFixed(4), v.lon.toFixed(4)]));
    if (key === this._fitKey) return;
    const first = this._fitKey === null;
    this._fitKey = key;
    if (!vehicles.length) {
      this._map.jumpTo({ center: stop, zoom: 15, bearing });
      return;
    }
    const bounds = new maplibregl.LngLatBounds(stop, stop);
    vehicles.forEach((v) => bounds.extend([v.lon, v.lat]));
    const pad = Math.round(Math.min(this._map.getContainer().clientHeight, 600) * 0.12) + 20;
    this._map.fitBounds(bounds, { bearing, padding: pad, maxZoom: 16, duration: first ? 0 : 900 });
  }
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

customElements.define("tcl-departures-card", TclDeparturesCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "tcl-departures-card",
  name: "TCL \u2013 Prochains d\u00e9parts",
  description: "Affichage plein \u00e9cran des prochains d\u00e9parts TCL (int\u00e9gration tcl_lyon).",
});
