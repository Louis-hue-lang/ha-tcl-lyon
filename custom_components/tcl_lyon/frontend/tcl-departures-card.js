/*
 * tcl-departures-card — affichage plein écran des prochains départs TCL.
 * Fonctionne avec l'intégration "tcl_lyon".
 */
const TCL_COLORS = {
  A: "#E2001A", B: "#0067B2", C: "#F39200", D: "#009B3A",
  F1: "#8DC63F", F2: "#8DC63F", RX: "#E30613",
};
const TCL_DEFAULT = { metroText: "#fff", tram: "#7A2A84", chrono: "#D5007F", bus: "#E4002B" };

function lineColor(ligne, custom) {
  const l = String(ligne || "").toUpperCase();
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
      title: "Prochains départs",
      max_departures: 3,
      fullscreen: true,
      show_clock: true,
      show_stop: true,
      hide_empty: false,
      colors: {},
      ...config,
    };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
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
  }

  getCardSize() { return 8; }
  static getStubConfig() { return { title: "Prochains départs" }; }

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

    const rows = states
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

    const rowHtml = rows.map(({ a, deps }) => {
      const color = lineColor(a.ligne, cfg.colors);
      const times = deps.length
        ? deps.map((d, i) => {
            const f = this._fmt(this._minutes(d, now));
            const dir = !a.direction && d.direction
              ? `<span class="subdir">${esc(d.direction)}</span>` : "";
            return `<div class="time ${i === 0 ? "first" : ""}">
                <span class="num">${f.big}</span><span class="unit">${f.small}</span>
                ${d.temps_reel ? '<span class="rt" title="Temps réel"></span>' : ""}
                ${dir}
              </div>`;
          }).join("")
        : `<div class="none">Aucun départ prévu</div>`;
      return `<div class="row">
          <div class="badge" style="background:${color}">${esc(a.ligne)}</div>
          <div class="info">
            <div class="dir">${esc(a.direction || "Toutes directions")}</div>
            ${cfg.show_stop ? `<div class="stop">${esc(a.arret || "")}</div>` : ""}
          </div>
          <div class="times">${times}</div>
        </div>`;
    }).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        .wrap {
          box-sizing:border-box; background:#111418; color:#f2f2f2;
          font-family: "Roboto", "Helvetica Neue", Arial, sans-serif;
          display:flex; flex-direction:column; padding:2.2vh 2.5vw; gap:1.6vh;
          ${cfg.fullscreen
            ? "position:fixed; inset:0; z-index:9; width:100vw; height:100vh;"
            : "border-radius:12px; min-height:300px;"}
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
      </style>
      <div class="wrap">
        <header>
          <h1>${esc(cfg.title || "")}</h1>
          ${cfg.show_clock ? `<div class="clock">${clock}</div>` : ""}
        </header>
        <div class="list">
          ${rowHtml || `<div class="empty">Aucune ligne suivie.<br>Ajoute des lignes dans
            Paramètres → Appareils et services → TCL Lyon → Configurer.</div>`}
        </div>
        <footer>
          <span>● temps réel &nbsp; sinon horaire théorique</span>
          <span class="${stale ? "warn" : ""}">${lastUpdate
            ? (stale ? "Données anciennes — " : "") + "MAJ " +
              new Date(lastUpdate).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })
            : ""}</span>
        </footer>
      </div>`;
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
  name: "TCL – Prochains départs",
  description: "Affichage plein écran des prochains départs TCL (intégration tcl_lyon).",
});
