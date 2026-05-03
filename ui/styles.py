"""
ApexForge AI — Global Styles & Design Tokens
Government-sovereign look: Deep Navy + Saffron accents + Emerald vitality colors
Injected once at app startup via st.markdown(get_css(), unsafe_allow_html=True)
"""


def get_css() -> str:
    return """
<style>
/* ── Google Fonts ─────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Root tokens ─────────────────────────────────────────────────────────── */
:root {
  --bg-primary:    #0a0f1e;
  --bg-secondary:  #0f1628;
  --bg-card:       #131c35;
  --bg-elevated:   #1a2444;
  --border:        #1e2e52;
  --border-glow:   #2a4080;

  --saffron:       #f59e0b;
  --saffron-light: #fbbf24;
  --saffron-dim:   rgba(245,158,11,0.15);

  --emerald:       #10b981;
  --emerald-dim:   rgba(16,185,129,0.15);
  --amber:         #f59e0b;
  --amber-dim:     rgba(245,158,11,0.12);
  --rose:          #f43f5e;
  --rose-dim:      rgba(244,63,94,0.12);
  --slate:         #94a3b8;
  --white:         #f1f5f9;

  --font-main: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;

  --shadow-md: 0 4px 24px rgba(0,0,0,0.4);
  --shadow-lg: 0 8px 48px rgba(0,0,0,0.6);
  --shadow-glow-saffron: 0 0 20px rgba(245,158,11,0.25);
  --shadow-glow-emerald: 0 0 20px rgba(16,185,129,0.20);
}

/* ── Base ────────────────────────────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"] {
  background: var(--bg-primary) !important;
  font-family: var(--font-main) !important;
  color: var(--white) !important;
}

[data-testid="stSidebar"] {
  background: var(--bg-secondary) !important;
  border-right: 1px solid var(--border) !important;
}

[data-testid="stHeader"] { background: transparent !important; }

/* ── Cards ───────────────────────────────────────────────────────────────── */
.gv-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 1.25rem 1.5rem;
  margin-bottom: 1rem;
  box-shadow: var(--shadow-md);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.gv-card:hover { border-color: var(--border-glow); box-shadow: var(--shadow-lg); }

.gv-card-elevated {
  background: var(--bg-elevated);
  border: 1px solid var(--border-glow);
  border-radius: var(--radius-lg);
  padding: 1.5rem;
  box-shadow: var(--shadow-lg);
}

/* ── Stat tiles ──────────────────────────────────────────────────────────── */
.gv-stat {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 1.2rem 1rem;
  text-align: center;
  transition: all 0.2s;
  position: relative; overflow: hidden;
}
.gv-stat::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, var(--saffron), var(--emerald));
  border-radius: var(--radius-md) var(--radius-md) 0 0;
}
.gv-stat-value {
  font-size: 2rem; font-weight: 800; color: var(--saffron);
  font-variant-numeric: tabular-nums; line-height: 1;
}
.gv-stat-label {
  color: var(--slate); font-size: 0.78rem; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0.4rem;
}

/* ── Vitality badges ─────────────────────────────────────────────────────── */
.badge-active  { background:var(--emerald-dim); color:var(--emerald); border:1px solid var(--emerald); padding:3px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }
.badge-dormant { background:var(--amber-dim);   color:var(--amber);   border:1px solid var(--amber);   padding:3px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }
.badge-closed  { background:var(--rose-dim);    color:var(--rose);    border:1px solid var(--rose);    padding:3px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }
.badge-unknown { background:#1e293b; color:var(--slate); border:1px solid #334155; padding:3px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }

/* ── Confidence bar ──────────────────────────────────────────────────────── */
.conf-bar-outer { background:#1e293b; border-radius:20px; height:8px; overflow:hidden; }
.conf-bar-inner { height:8px; border-radius:20px; transition:width 0.5s ease;
                  background: linear-gradient(90deg, #f59e0b, #10b981); }

/* ── Section headers ─────────────────────────────────────────────────────── */
.gv-section-title {
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.16em;
  text-transform: uppercase; color: var(--saffron); margin-bottom: 0.75rem;
  border-left: 3px solid var(--saffron); padding-left: 0.6rem;
}

/* ── Logo / brand ────────────────────────────────────────────────────────── */
.gv-logo {
  font-size: 1.6rem; font-weight: 800;
  background: linear-gradient(135deg, var(--saffron) 30%, var(--emerald) 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  letter-spacing: -0.02em;
}
.gv-tagline { color: var(--slate); font-size: 0.75rem; letter-spacing: 0.05em; }

/* ── Side-by-side record comparison ─────────────────────────────────────── */
.record-card {
  background: var(--bg-elevated); border: 1px solid var(--border-glow);
  border-radius: var(--radius-md); padding: 1rem;
}
.record-field { margin-bottom: 0.5rem; }
.field-label { color: var(--slate); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
.field-value { color: var(--white); font-size: 0.92rem; font-weight: 500; }
.field-value.highlight { color: var(--saffron); font-weight: 700; }
.field-diff { color: var(--rose); font-weight: 600; }

/* ── AI explanation panel ────────────────────────────────────────────────── */
.explain-panel {
  background: linear-gradient(135deg, rgba(15,22,40,0.95), rgba(26,36,68,0.95));
  border: 1px solid var(--border-glow); border-radius: var(--radius-lg);
  padding: 1.25rem;
}
.reason-item { padding: 0.4rem 0; border-bottom: 1px solid var(--border); font-size: 0.88rem; }
.reason-item:last-child { border-bottom: none; }
.concern-item { color: var(--rose); font-size: 0.88rem; padding: 0.4rem 0; }

/* ── Timeline strip ──────────────────────────────────────────────────────── */
.timeline-event {
  display: flex; align-items: center; gap: 0.75rem;
  padding: 0.5rem 0; border-bottom: 1px solid var(--border);
  font-size: 0.86rem;
}
.timeline-dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.dot-renewal    { background: var(--emerald); box-shadow: var(--shadow-glow-emerald); }
.dot-inspection { background: var(--saffron); box-shadow: var(--shadow-glow-saffron); }
.dot-filing     { background: #60a5fa; }
.dot-utility    { background: #a78bfa; }
.dot-complaint  { background: var(--rose); }
.dot-shutdown   { background: #ef4444; box-shadow: 0 0 12px rgba(239,68,68,0.5); }
.dot-unknown    { background: var(--slate); }

/* ── Query builder ───────────────────────────────────────────────────────── */
.query-chip {
  display: inline-block; background: var(--saffron-dim); color: var(--saffron);
  border: 1px solid rgba(245,158,11,0.4); border-radius: 20px;
  padding: 0.3rem 0.8rem; font-size: 0.8rem; font-weight: 600;
  cursor: pointer; margin: 0.2rem;
}
.query-chip:hover { background: rgba(245,158,11,0.3); }

/* ── UBID display ────────────────────────────────────────────────────────── */
.ubid-badge {
  font-family: var(--font-mono); font-size: 0.72rem;
  color: var(--saffron); background: var(--saffron-dim);
  border: 1px solid rgba(245,158,11,0.3); border-radius: 6px;
  padding: 2px 8px;
}

/* ── Pulse ring ──────────────────────────────────────────────────────────── */
.pulse-ring {
  width: 64px; height: 64px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.2rem; font-weight: 800; position: relative;
}

/* ── Streamlit overrides ─────────────────────────────────────────────────── */
div[data-testid="metric-container"] {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-md); padding: 1rem;
}
.stButton > button {
  background: linear-gradient(135deg, #1e3a8a, #1e40af);
  color: white; border: 1px solid #3b82f6; border-radius: var(--radius-sm);
  font-weight: 600; letter-spacing: 0.02em; transition: all 0.2s;
}
.stButton > button:hover { box-shadow: 0 0 16px rgba(59,130,246,0.4); transform: translateY(-1px); }

button[kind="primary"] {
  background: linear-gradient(135deg, var(--saffron), #d97706) !important;
  color: var(--bg-primary) !important; border: none !important; font-weight: 700 !important;
}
.stTextInput input, .stSelectbox select, .stMultiSelect span {
  background: var(--bg-elevated) !important; color: var(--white) !important;
  border: 1px solid var(--border) !important; border-radius: var(--radius-sm) !important;
}

/* ── Scrollbar ───────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg-secondary); }
::-webkit-scrollbar-thumb { background: var(--border-glow); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--saffron); }

/* ── Misc ────────────────────────────────────────────────────────────────── */
hr { border-color: var(--border) !important; margin: 1rem 0; }
.stAlert { border-radius: var(--radius-md) !important; }
code { font-family: var(--font-mono); background: var(--bg-elevated); padding: 2px 6px; border-radius: 4px; }
</style>
"""


# ─── Reusable HTML snippet builders ──────────────────────────────────────────

def stat_card(value: str | int | float, label: str) -> str:
    return f"""
    <div class="gv-stat">
      <div class="gv-stat-value">{value}</div>
      <div class="gv-stat-label">{label}</div>
    </div>
    """


def vitality_badge(status: str) -> str:
    cls = f"badge-{status.lower()}"
    icons = {"ACTIVE": "●", "DORMANT": "◐", "CLOSED": "○", "UNKNOWN": "?"}
    icon = icons.get(status, "?")
    return f'<span class="{cls}">{icon} {status}</span>'


def confidence_bar(score: float) -> str:
    pct = round(score * 100)
    color = "#10b981" if score >= 0.92 else "#f59e0b" if score >= 0.65 else "#f43f5e"
    return f"""
    <div style="margin:4px 0">
      <div class="conf-bar-outer">
        <div class="conf-bar-inner" style="width:{pct}%; background:{color};"></div>
      </div>
      <small style="color:#94a3b8">{pct}% confidence</small>
    </div>
    """


def ubid_badge(ubid: str) -> str:
    short = str(ubid)[:8] + "…"
    return f'<span class="ubid-badge" title="{ubid}">UBID:{short}</span>'


def section_title(text: str) -> str:
    return f'<div class="gv-section-title">{text}</div>'


def timeline_dot_class(event_type: str) -> str:
    return {
        "RENEWAL":    "dot-renewal",
        "INSPECTION": "dot-inspection",
        "FILING":     "dot-filing",
        "UTILITY":    "dot-utility",
        "COMPLAINT":  "dot-complaint",
        "SHUTDOWN":   "dot-shutdown",
    }.get(event_type, "dot-unknown")
