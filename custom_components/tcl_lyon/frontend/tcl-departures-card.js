/*
 * tcl-departures-card \u2014 affichage plein \u00e9cran des prochains d\u00e9parts TCL.
 * Fonctionne avec l'int\u00e9gration "tcl_lyon".
 *
 * \u00c9crit pour du mat\u00e9riel modeste (Echo Show 8 1re g\u00e9n\u00e9ration) :
 * - rendu uniquement si un capteur TCL a chang\u00e9 (pas \u00e0 chaque changement d'\u00e9tat de la maison) ;
 * - DOM mis \u00e0 jour seulement si le contenu affich\u00e9 change ;
 * - aucune animation CSS permanente ;
 * - carte Leaflet (~150 Ko, sans WebGL), charg\u00e9e seulement \u00e0 la premi\u00e8re ouverture,
 *   statique (aucune interaction), orient\u00e9e par une simple rotation CSS.
 */
const LEAFLET_BASE = "/tcl_lyon/leaflet";

let _leafletPromise;
function loadLeaflet() {
  if (window.L && window.L.map) return Promise.resolve(window.L);
  if (!_leafletPromise) {
    _leafletPromise = new Promise((resolve, reject) => {
      const sc = document.createElement("script");
      sc.src = `${LEAFLET_BASE}/leaflet.js`;
      sc.onload = () => resolve(window.L);
      sc.onerror = (e) => { _leafletPromise = null; reject(e); };
      document.head.appendChild(sc);
    });
  }
  return _leafletPromise;
}

// OSM France : sans cl\u00e9 et sans Referer. Home Assistant n'en envoie pas aux autres domaines, et
// CARTO (cl\u00e9 obligatoire), tile.openstreetmap.org et Stadia renvoient alors une image d'erreur.
const OSMFR_TILES = {
  url: "https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png",
  subdomains: "abc",
  attribution: "\u00a9 OpenStreetMap contributors, OSM France",
};

const TILES = {
  // Sombre : un seul filtre CSS sur le calque des tuiles, pas un par tuile
  dark: { ...OSMFR_TILES, filter: "invert(1) hue-rotate(180deg) brightness(.95) contrast(.85)" },
  light: OSMFR_TILES,
};

const TCL_COLORS = {
  A: "#E2001A", B: "#0067B2", C: "#F39200", D: "#009B3A",
  F1: "#8DC63F", F2: "#8DC63F", RX: "#E30613",
};

function displayLine(ligne) {
  return String(ligne || "").toUpperCase().trim();
}

function lineColor(ligne, custom) {
  const l = displayLine(ligne);
  if (custom && custom[ligne]) return custom[ligne];
  if (custom && custom[l]) return custom[l];
  if (TCL_COLORS[l]) return TCL_COLORS[l];
  if (/^T\d/.test(l)) return "#7A2A84"; // tram
  if (/^C\d/.test(l)) return "#D5007F"; // Chrono
  return "#E4002B"; // bus
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function rotate(p, deg) {
  const r = (deg * Math.PI) / 180;
  const c = Math.cos(r), s = Math.sin(r);
  return { x: p.x * c - p.y * s, y: p.x * s + p.y * c };
}

const STYLE = `
  :host { display:block; }
  .wrap { box-sizing:border-box; background:#111418; color:#f2f2f2;
    font-family: Roboto, "Helvetica Neue", Arial, sans-serif;
    display:flex; flex-direction:column; padding:2.2vh 2.5vw; gap:1.6vh; }
  .wrap.full { position:fixed; inset:0; z-index:9; width:100vw; height:100vh; }
  .wrap.inline { position:relative; border-radius:12px; min-height:300px; }
  header { display:flex; align-items:baseline; justify-content:space-between; }
  h1 { margin:0; font-size:clamp(20px,4.2vh,44px); font-weight:500; }
  .clock { font-size:clamp(28px,7vh,72px); font-weight:300; }
  .list { flex:1; display:flex; flex-direction:column; gap:1.4vh; overflow:hidden; }
  .row { display:flex; align-items:center; gap:2vw; background:#1d2228; border-radius:14px;
    padding:1.6vh 1.8vw; flex:1 1 0; max-height:20vh; min-height:0; }
  .row[data-map] { cursor:pointer; }
  .row[data-map]:active { background:#262d35; }
  .badge { min-width:clamp(56px,11vh,120px); height:clamp(56px,11vh,120px); border-radius:12px;
    display:flex; align-items:center; justify-content:center; color:#fff;
    font-size:clamp(24px,6vh,64px); font-weight:700; padding:0 .6vw; box-sizing:border-box; }
  .badge.velov { background:#E2001A; font-size:clamp(14px,3vh,32px); }
  .info { flex:1; min-width:0; }
  .dir { font-size:clamp(20px,4.8vh,52px); font-weight:500;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .stop, .alert { font-size:clamp(13px,2.6vh,28px); color:#9aa4ae; margin-top:.4vh;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .alert { color:#ffab40; }
  .warn { color:#ff7043; }
  .times { display:flex; align-items:baseline; gap:2.4vw; }
  .time { position:relative; display:flex; align-items:baseline; gap:.3vw; color:#9aa4ae;
    flex-wrap:wrap; justify-content:flex-end; max-width:22vw; }
  .num { font-size:clamp(22px,5vh,54px); font-weight:500; }
  .unit { font-size:clamp(12px,2.4vh,26px); }
  .time.first { color:#ffd54a; }
  .time.first .num { font-size:clamp(34px,9vh,100px); font-weight:700; }
  .time.first .unit { font-size:clamp(14px,3vh,32px); }
  .subdir { width:100%; text-align:right; font-size:clamp(10px,1.8vh,20px); color:#9aa4ae;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .rt { position:absolute; top:-.4vh; right:-1vw; width:1.2vh; height:1.2vh; border-radius:50%;
    background:#4caf50; }
  .none { color:#9aa4ae; font-size:clamp(16px,3vh,32px); }
  .empty { margin:auto; text-align:center; color:#9aa4ae; font-size:clamp(16px,3.5vh,36px); }
  footer { display:flex; justify-content:space-between; font-size:clamp(11px,2vh,22px); color:#6f7a85; }
  .modal { position:absolute; inset:2.5vh 2.5vw; z-index:5; background:#111418; border-radius:16px;
    display:flex; flex-direction:column; overflow:hidden; border:1px solid #2c333b; }
  .modal[hidden] { display:none; }
  .mhead { display:flex; align-items:center; gap:1.6vw; padding:1.4vh 1.6vw; background:#1d2228; }
  .mhead .badge { min-width:clamp(40px,8vh,90px); height:clamp(40px,8vh,90px);
    font-size:clamp(18px,4.4vh,48px); }
  .mhead .dir { font-size:clamp(18px,4vh,44px); }
  .mtimes { display:flex; gap:1.6vw; color:#ffd54a; font-size:clamp(18px,4.4vh,48px); font-weight:700; }
  .mtimes span + span { color:#9aa4ae; font-weight:500; }
  .close { background:#2c333b; color:#fff; border:0; border-radius:50%; flex:none;
    width:clamp(40px,8vh,80px); height:clamp(40px,8vh,80px); font-size:clamp(20px,4.4vh,44px); }
  .mapbox { position:relative; flex:1; min-height:0; overflow:hidden; background:#1a1f24; }
  .map { position:absolute; background:#1a1f24; }
  .mmsg { position:absolute; left:50%; top:1.5vh; transform:translateX(-50%); z-index:1000;
    background:rgba(17,20,24,.88); padding:.8vh 1.4vw; border-radius:10px;
    font-size:clamp(13px,2.4vh,26px); color:#e0e0e0; white-space:nowrap; }
  .mmsg:empty { display:none; }
  .attrib { position:absolute; right:6px; bottom:4px; z-index:1000; font-size:10px;
    color:#9aa4ae; background:rgba(17,20,24,.7); padding:1px 5px; border-radius:4px; }
  .up { width:100%; height:100%; }
  .veh { position:relative; width:100%; height:100%; }
  .veh .dot { position:absolute; inset:0; border-radius:50%; border:3px solid #fff; box-sizing:border-box;
    display:flex; align-items:center; justify-content:center; color:#fff;
    font:700 15px Roboto, Arial, sans-serif; }
  .veh .arrow { position:absolute; inset:-34%; }
  .veh .arrow::before { content:""; position:absolute; left:50%; top:0; transform:translateX(-50%);
    border-left:9px solid transparent; border-right:9px solid transparent;
    border-bottom:14px solid var(--c); }
  .stopmk { position:relative; width:100%; height:100%; }
  .stopmk .pin { width:100%; height:100%; border-radius:50%; background:#fff;
    border:5px solid #111; box-sizing:border-box; outline:3px solid #ffd54a; }
  .stopmk .lbl { position:absolute; top:100%; left:50%; transform:translateX(-50%); margin-top:6px;
    background:#ffd54a; color:#111; border-radius:6px; padding:1px 6px;
    font:700 15px Roboto, Arial, sans-serif; white-space:nowrap; }
`;

const VEH_SIZE = 42;
const STOP_SIZE = 30;

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
    this._ids = null;
    this._seen = null;
    this._render(true);
  }

  set hass(hass) {
    this._hass = hass;
    // Home Assistant appelle ce setter \u00e0 chaque changement d'\u00e9tat de N'IMPORTE QUELLE entit\u00e9 :
    // on ne redessine que si l'un des capteurs affich\u00e9s a chang\u00e9.
    const ids = this._entityIds();
    const changed =
      !this._seen || ids.length !== this._seen.length ||
      ids.some((id, i) => hass.states[id] !== this._seen[i]);
    if (!changed) return;
    this._seen = ids.map((id) => hass.states[id]);
    this._render(false);
  }

  connectedCallback() {
    // Compte \u00e0 rebours : le DOM n'est touch\u00e9 que si le texte affich\u00e9 change.
    this._timer = setInterval(() => this._render(false), 15000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._closeMap();
  }

  getCardSize() { return 8; }
  static getStubConfig() { return { title: "Prochains d\u00e9parts" }; }

  _entityIds() {
    const hass = this._hass;
    if (!hass) return [];
    const cfgIds = this._config.entities;
    if (cfgIds && cfgIds.length) return cfgIds.map((e) => (typeof e === "string" ? e : e.entity));
    // D\u00e9couverte automatique : parcours complet des \u00e9tats, refait au plus toutes les 60 s.
    const now = Date.now();
    if (!this._ids || now - this._idsAt > 60000) {
      this._ids = Object.keys(hass.states).filter(
        (id) => id.startsWith("sensor.") && hass.states[id].attributes.integration === "tcl_lyon"
      );
      this._idsAt = now;
    }
    return this._ids;
  }

  _minutes(dep, now) {
    const t = Date.parse(dep.heure);
    if (isNaN(t)) return dep.minutes;
    return Math.max(0, Math.floor((t - now) / 60000));
  }

  _fmt(min) {
    if (min <= 0) return { big: "Proche", small: "" };
    if (min >= 60) return { big: `${Math.floor(min / 60)}h${String(min % 60).padStart(2, "0")}`, small: "" };
    return { big: String(min), small: "min" };
  }

  _set(el, key, html) {
    // N'\u00e9crit dans le DOM que si le contenu a chang\u00e9 (\u00e9vite mises en page et repeints).
    if (this._cache[key] === html) return;
    this._cache[key] = html;
    el.innerHTML = html;
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    if (!this._built) this._build();
    const cfg = this._config;
    const hass = this._hass;
    const now = Date.now();
    const states = hass ? this._entityIds().map((id) => hass.states[id]).filter(Boolean) : [];

    const velov = states.filter((s) => s.attributes.type === "velov");
    const rows = states
      .filter((s) => s.attributes.type !== "velov")
      .map((st) => {
        const deps = (st.attributes.departs || [])
          .filter((d) => !(Date.parse(d.heure) < now - 60000))
          .slice(0, cfg.max_departures);
        return { st, a: st.attributes, deps, first: deps.length ? this._minutes(deps[0], now) : Infinity };
      })
      .filter((r) => !(cfg.hide_empty && !r.deps.length));
    if (cfg.sort !== "config") rows.sort((x, y) => x.first - y.first);

    let html = rows.map(({ st, a, deps }) => {
      const alertes = cfg.show_alerts ? (a.alertes || []) : [];
      const times = deps.length
        ? deps.map((d, i) => {
            const f = this._fmt(this._minutes(d, now));
            const sub = !a.direction && d.direction ? `<span class="subdir">${esc(d.direction)}</span>` : "";
            return `<div class="time${i === 0 ? " first" : ""}"><span class="num">${f.big}</span>` +
              `<span class="unit">${f.small}</span>${d.temps_reel ? '<span class="rt"></span>' : ""}${sub}</div>`;
          }).join("")
        : `<div class="none">Aucun d\u00e9part pr\u00e9vu</div>`;
      const sub = alertes.length
        ? `<div class="alert">\u26a0 ${esc(alertes.map((x) => x.titre || x.message).join(" \u00b7 "))}</div>`
        : cfg.show_stop ? `<div class="stop">${esc(a.arret || "")}</div>` : "";
      return `<div class="row" data-map="${esc(st.entity_id)}">` +
        `<div class="badge" style="background:${lineColor(a.ligne, cfg.colors)}">${esc(displayLine(a.ligne))}</div>` +
        `<div class="info"><div class="dir">${esc(a.direction || "Toutes directions")}</div>${sub}</div>` +
        `<div class="times">${times}</div></div>`;
    }).join("");

    html += velov.map((st) => {
      const a = st.attributes;
      const closed = a.statut && !/open|ouvert/i.test(a.statut);
      const bikes = st.state === "unavailable" || st.state === "unknown" ? "\u2013" : st.state;
      const sub = closed ? '<span class="warn">Station ferm\u00e9e</span>'
        : a.places != null ? `${a.places} places libres` : "";
      const elec = a.velos_electriques != null
        ? `<div class="time"><span class="num">${a.velos_electriques}</span><span class="unit">\u26a1</span></div>` : "";
      return `<div class="row"><div class="badge velov">V\u00e9lo'v</div>` +
        `<div class="info"><div class="dir">${esc(a.station || "")}</div><div class="stop">${sub}</div></div>` +
        `<div class="times">${elec}<div class="time first"><span class="num">${bikes}</span>` +
        `<span class="unit">v\u00e9los</span></div></div></div>`;
    }).join("");

    const $ = (q) => this.shadowRoot.querySelector(q);
    this._set($(".list"), "list", html || `<div class="empty">Aucune ligne suivie.<br>Ajoute des lignes dans
      Param\u00e8tres \u2192 Appareils et services \u2192 TCL Lyon \u2192 Configurer.</div>`);

    const hm = (t) => new Date(t).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    if (cfg.show_clock) this._set($(".clock"), "clock", hm(now));
    const last = states.reduce((m, s) => Math.max(m, Date.parse(s.last_updated) || 0), 0);
    const stale = last && now - last > 5 * 60000;
    this._set($("footer"), "footer",
      `<span><span style="color:#4caf50">\u25cf</span> temps r\u00e9el &nbsp; sinon horaire th\u00e9orique</span>` +
      `<span class="${stale ? "warn" : ""}">${last ? (stale ? "Donn\u00e9es anciennes \u2014 " : "") + "MAJ " + hm(last) : ""}</span>`);

    if (this._mapEntity) this._updateModal();
  }

  _build() {
    this._built = true;
    this._cache = {};
    this._closeMap();
    const cfg = this._config;
    this.shadowRoot.innerHTML = `
      <link rel="stylesheet" href="${LEAFLET_BASE}/leaflet.css">
      <style>${STYLE}</style>
      <div class="wrap ${cfg.fullscreen ? "full" : "inline"}">
        <header><h1>${esc(cfg.title || "")}</h1>${cfg.show_clock ? `<div class="clock"></div>` : ""}</header>
        <div class="list"></div>
        <footer></footer>
        <div class="modal" hidden>
          <div class="mhead">
            <div class="badge"></div>
            <div class="info"><div class="dir"></div><div class="stop"></div></div>
            <div class="mtimes"></div>
            <button class="close" aria-label="Fermer">\u2715</button>
          </div>
          <div class="mapbox"><div class="map"></div><div class="mmsg"></div><div class="attrib"></div></div>
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

  _activatePositions() {
    // Les positions (~600 Ko) ne sont t\u00e9l\u00e9charg\u00e9es par Home Assistant que pendant que la carte est ouverte.
    if (this._hass) this._hass.callService("tcl_lyon", "activer_carte", {}).catch(() => {});
  }

  _openMap(entityId) {
    this._mapEntity = entityId;
    this._fitKey = null;
    this.shadowRoot.querySelector(".modal").hidden = false;
    this._activatePositions();
    clearInterval(this._keepAlive);
    this._keepAlive = setInterval(() => this._activatePositions(), 30000);
    this._armTimeout();
    this._updateModal();
  }

  _closeMap() {
    clearTimeout(this._mapTimeout);
    clearInterval(this._keepAlive);
    this._mapEntity = null;
    if (this._map) { this._map.remove(); this._map = null; } // lib\u00e8re tuiles et m\u00e9moire
    this._markers = {};
    const modal = this.shadowRoot && this.shadowRoot.querySelector(".modal");
    if (modal) modal.hidden = true;
  }

  async _updateModal() {
    const st = this._hass && this._hass.states[this._mapEntity];
    if (!st) return this._closeMap();
    const $ = (q) => this.shadowRoot.querySelector(q);
    const a = st.attributes;
    const cfg = this._config;
    const now = Date.now();
    const badge = $(".mhead .badge");
    badge.textContent = displayLine(a.ligne);
    badge.style.background = lineColor(a.ligne, cfg.colors);
    $(".mhead .dir").textContent = a.direction || "Toutes directions";
    $(".mhead .stop").textContent = a.arret || "";
    this._set($(".mtimes"), "mtimes", (a.departs || []).slice(0, 3).map((d) => {
      const f = this._fmt(this._minutes(d, now));
      return `<span>${f.big}${f.small ? " " + f.small : ""}</span>`;
    }).join(""));
    const msg = $(".mmsg");

    if (!a.carte_disponible) {
      msg.textContent = a.arret_position === undefined
        ? "Carte indisponible : renseigne l'URL des positions dans TCL Lyon \u2192 Configurer \u2192 Carte des bus"
        : "Position de l'arr\u00eat inconnue";
      return;
    }
    const vehicles = a.carte_active ? (a.vehicules || []) : [];
    msg.textContent = !a.carte_active ? "Chargement des positions\u2026"
      : vehicles.length ? ""
      : a.positions_ligne === false ? "Pas de position en temps r\u00e9el pour cette ligne (m\u00e9tro, funiculaire\u2026)"
      : "Aucun v\u00e9hicule en approche pour le moment";

    let L;
    try {
      L = await loadLeaflet();
    } catch (e) {
      msg.textContent = "Impossible de charger la carte";
      return;
    }
    if (this._mapEntity !== st.entity_id) return;

    const rawBearing = cfg.map_bearing != null ? cfg.map_bearing : a.carte_orientation;
    const bearing = ((Number(rawBearing) || 0) % 360 + 360) % 360;
    const stop = L.latLng(a.arret_position[0], a.arret_position[1]);
    const color = lineColor(a.ligne, cfg.colors);
    const box = $(".mapbox");
    const W = box.clientWidth, H = box.clientHeight;

    if (!this._map) {
      // Conteneur carr\u00e9 de la taille de la diagonale, tourn\u00e9 en CSS : aucun coin vide quelle que
      // soit l'orientation. Carte statique : pas de glisser, pas de zoom, pas d'animation.
      const D = bearing ? Math.ceil(Math.hypot(W, H)) : 0;
      const el = $(".map");
      Object.assign(el.style, bearing
        ? { width: `${D}px`, height: `${D}px`, left: `${(W - D) / 2}px`, top: `${(H - D) / 2}px`,
            transform: `rotate(${-bearing}deg)` }
        : { width: `${W}px`, height: `${H}px`, left: "0", top: "0", transform: "" });
      this._map = L.map(el, {
        zoomControl: false, attributionControl: false, dragging: false, touchZoom: false,
        doubleClickZoom: false, scrollWheelZoom: false, boxZoom: false, keyboard: false,
        tap: false, zoomAnimation: false, fadeAnimation: false, markerZoomAnimation: false,
        inertia: false, zoomSnap: 0.25,
      }).setView(stop, 16);
      const t = TILES[cfg.map_style] || TILES.dark;
      L.tileLayer(t.url, { subdomains: t.subdomains, maxZoom: 19, keepBuffer: 0, updateWhenIdle: true })
        .addTo(this._map);
      if (t.filter) this._map.getPane("tilePane").style.filter = t.filter;
      $(".attrib").textContent = t.attribution;
      this._markers = {};
      this._bearing = bearing;
      L.marker(stop, {
        interactive: false, keyboard: false,
        icon: L.divIcon({
          className: "", iconSize: [STOP_SIZE, STOP_SIZE], iconAnchor: [STOP_SIZE / 2, STOP_SIZE / 2],
          html: `<div class="up" style="transform:rotate(${bearing}deg)"><div class="stopmk">` +
            `<div class="pin"></div><div class="lbl">${esc(a.arret || "Arr\u00eat")}</div></div></div>`,
        }),
      }).addTo(this._map);
    }

    // Marqueurs des v\u00e9hicules (cr\u00e9\u00e9s une fois, puis seulement d\u00e9plac\u00e9s)
    const seen = new Set();
    for (const v of vehicles) {
      seen.add(v.id);
      let mk = this._markers[v.id];
      if (!mk) {
        mk = L.marker([v.lat, v.lon], {
          interactive: false, keyboard: false,
          icon: L.divIcon({
            className: "", iconSize: [VEH_SIZE, VEH_SIZE], iconAnchor: [VEH_SIZE / 2, VEH_SIZE / 2],
            html: `<div class="up" style="transform:rotate(${bearing}deg)"><div class="veh" style="--c:${color}">` +
              `<div class="arrow"></div><div class="dot" style="background:${color}">` +
              `${esc(displayLine(a.ligne))}</div></div></div>`,
          }),
        }).addTo(this._map);
        this._markers[v.id] = mk;
      } else {
        mk.setLatLng([v.lat, v.lon]);
      }
      const el = mk.getElement();
      if (el) {
        const arrow = el.querySelector(".arrow");
        // L'ic\u00f4ne est redress\u00e9e de +bearing : la fl\u00e8che doit tourner de (cap - orientation)
        arrow.style.display = v.cap == null ? "none" : "";
        arrow.style.transform = `rotate(${(v.cap || 0) - bearing}deg)`;
        el.querySelector(".veh").style.opacity = v.confirme === false ? "0.6" : "1";
      }
    }
    for (const id of Object.keys(this._markers)) {
      if (!seen.has(id)) { this._markers[id].remove(); delete this._markers[id]; }
    }

    // Cadrage : l'arr\u00eat + les v\u00e9hicules en approche, dans le rep\u00e8re tourn\u00e9.
    // L'arr\u00eat se retrouve naturellement dans un coin, \u00e0 l'oppos\u00e9 de la zone d'o\u00f9 arrivent les bus.
    const key = vehicles.map((v) => `${v.id}:${v.lat.toFixed(4)},${v.lon.toFixed(4)}`).join("|");
    if (key === this._fitKey) return;
    this._fitKey = key;
    if (!vehicles.length) {
      this._map.setView(stop, 16, { animate: false });
      return;
    }
    const pts = [stop, ...vehicles.map((v) => L.latLng(v.lat, v.lon))];
    const pad = VEH_SIZE + 24;
    for (let z = 17; z >= 10; z -= 0.25) {
      const r = pts.map((p) => rotate(this._map.project(p, z), -bearing));
      const xs = r.map((p) => p.x), ys = r.map((p) => p.y);
      const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
      if (maxX - minX <= W - 2 * pad && maxY - minY <= H - 2 * pad || z <= 10) {
        const c = rotate({ x: (minX + maxX) / 2, y: (minY + maxY) / 2 }, bearing);
        this._map.setView(this._map.unproject(L.point(c.x, c.y), z), z, { animate: false });
        break;
      }
    }
  }
}

// Home Assistant remplace customElements en démarrant. Une carte enregistrée avant ce
// remplacement reste invisible ("Erreur de configuration") : fréquent sur un appareil lent.
function registerCard() {
  if (!customElements.get("home-assistant")) {
    setTimeout(registerCard, 50);
    return;
  }
  if (!customElements.get("tcl-departures-card")) {
    customElements.define("tcl-departures-card", TclDeparturesCard);
  }
}
registerCard();

window.customCards = window.customCards || [];
window.customCards.push({
  type: "tcl-departures-card",
  name: "TCL \u2013 Prochains d\u00e9parts",
  description: "Affichage plein \u00e9cran des prochains d\u00e9parts TCL (int\u00e9gration tcl_lyon).",
});
