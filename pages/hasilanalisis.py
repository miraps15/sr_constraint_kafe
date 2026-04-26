# ============================================================
# HALAMAN HASIL ANALISIS ABSA — hasilanalisis.py
# PERUBAHAN untuk Streamlit Cloud:
#   - df_konversi tidak lagi dari file lokal /content/drive/...
#     melainkan di-load via gsheets_client (Google Sheets API)
#   - Semua path lokal dihilangkan
#   - st.cache_data digunakan dengan ttl agar data fresh
# Fungsionalitas utama (Rumus A: IMDb WR + SAW) tidak diubah.
# ============================================================

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import json
import io
import re

st.set_page_config(
    page_title="Hasil Analisis Review",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ===== BACK NAVIGATION HANDLER =====
if "_go_back" in st.session_state:
    prev_page = st.session_state.pop("_go_back")
    try:
        st.switch_page(prev_page)
    except Exception:
        st.switch_page("app_kafe.py")

if not st.session_state.get("logged_in", False):
    st.switch_page("app_kafe.py")

if "analisis_result" not in st.session_state:
    st.switch_page("pages/app_kafe1.py")

# ════════════════════════════════════════════════════════════════
# CSS
# ════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,700;9..144,900&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
:root {
  --rust: #C8502A; --rust-dk: #A33E20; --rust-lt: #FFF0EB;
  --ink: #1C1917; --muted: #78716C; --border: #E8DDD5;
  --green: #1A7A3C; --green-lt: #EDFAF2;
  --blue: #1A6EB0; --blue-lt: #EBF5FF;
  --bg: #F5F3F0;
  --content-max: 900px;
  --page-px: 40px;
}
html, body, [class*="css"] {
  font-family: 'Plus Jakarta Sans', sans-serif;
  background: var(--bg); color: var(--ink);
}
.stApp { background: var(--bg); }
#MainMenu, footer, header { visibility: hidden; }
.block-container {
  padding-top: 0 !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
  max-width: 100% !important;
}

/* ── Topbar ──────────────────────────────────────────────── */
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 11px 32px; background: #fff;
  border-bottom: 1px solid var(--border);
  box-shadow: 0 1px 12px rgba(28,25,23,.05);
  position: sticky; top: 0; z-index: 999;
}
.topbar-logo {
  font-family: 'Fraunces', serif; font-size: 1.25rem;
  font-weight: 900; color: var(--ink); letter-spacing: -.5px;
}
.topbar-logo span { color: var(--rust); }

/* ── Buttons ─────────────────────────────────────────────── */
div[data-testid="stButton"] button {
  border-radius: 50px !important; background: var(--rust) !important;
  color: white !important; border: none !important;
  font-weight: 700 !important; font-size: .88rem !important;
  padding: 10px 28px !important; min-height: 44px !important;
  transition: background .2s !important;
}
div[data-testid="stButton"] button:hover { background: var(--rust-dk) !important; }
div[data-testid="stDownloadButton"] button {
  border-radius: 10px !important; background: #1A7A3C !important;
  color: white !important; border: none !important;
  font-weight: 700 !important; font-size: .82rem !important;
  padding: 8px 18px !important; min-height: 38px !important;
}
div[data-testid="stDownloadButton"] button:hover { background: #155e2f !important; }
div[data-testid="stExpander"] {
  border: 1.5px solid var(--border) !important;
  border-radius: 14px !important; background: #fff !important;
  box-shadow: 0 2px 8px rgba(28,25,23,.04) !important;
  margin-top: 0 !important;
}
div[data-testid="stExpander"] summary {
  font-size: .86rem !important; font-weight: 700 !important;
  color: var(--rust) !important;
}
div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }

/* ── Page shell: satu wrapper vertikal ────────────────────── */
.page-body {
  max-width: var(--content-max);
  margin: 0 auto;
  padding: 28px var(--page-px) 48px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ── Section ──────────────────────────────────────────────── */
.section {
  background: #fff;
  border: 1.5px solid var(--border);
  border-radius: 18px;
  padding: 22px 24px;
  box-shadow: 0 2px 10px rgba(28,25,23,.045);
  margin-bottom: 14px;
}
.section:last-child { margin-bottom: 0; }

/* ── Section header ──────────────────────────────────────── */
.sec-hdr {
  display: flex; align-items: center; gap: 10px; margin-bottom: 16px;
}
.sec-hdr-accent { width: 4px; height: 30px; border-radius: 2px; flex-shrink: 0; }
.sec-hdr-title {
  font-family: 'Fraunces', serif; font-size: 1rem;
  font-weight: 900; color: var(--ink); margin: 0;
}
.sec-hdr-sub { font-size: .73rem; color: var(--muted); margin: 2px 0 0; }

/* ── Stat boxes in hero ───────────────────────────────────── */
.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.stat-box {
  background: rgba(255,255,255,.09); border: 1px solid rgba(255,255,255,.15);
  border-radius: 14px; padding: 14px 12px; text-align: center;
}
.stat-num {
  font-family: 'Fraunces', serif; font-size: 1.7rem;
  font-weight: 900; line-height: 1; margin-bottom: 4px;
}
.stat-lbl { font-size: .65rem; color: rgba(255,255,255,.45); }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# NAVBAR
# ════════════════════════════════════════════════════════════════
st.markdown("""
<div class="topbar">
  <div class="topbar-logo">Kafe<span>Sby</span></div>
  <nav style="display:flex;gap:2px;align-items:center;">
    <a style="text-decoration:none;color:#78716C;font-size:.78rem;font-weight:600;
       padding:7px 14px;border-radius:8px;transition:background .18s,color .18s;"
       href="?"
       onmouseover="this.style.background='#FFF0EB';this.style.color='#C8502A';"
       onmouseout="this.style.background='';this.style.color='#78716C';">
      &#8592; Kembali ke Beranda
    </a>
  </nav>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# AMBIL DATA DARI SESSION STATE
# ════════════════════════════════════════════════════════════════
result_data      = st.session_state.get("analisis_result", {})
nama_kafe        = result_data.get("nama_kafe", "Kafe Tidak Diketahui")
jumlah_rev       = result_data.get("jumlah_review", 0)
raw_aspects      = result_data.get("raw_aspects", [])
original_reviews = result_data.get("original_reviews", [])
n_analyzed       = result_data.get("n_analyzed", jumlah_rev)
was_truncated    = result_data.get("was_truncated", False)

# ════════════════════════════════════════════════════════════════
# LOAD DF_KONVERSI dari Google Sheets (bukan file lokal)
# ════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False, ttl=600)
def load_konversi() -> pd.DataFrame:
    try:
        from gsheets_client import read_sheet_as_df
        df = read_sheet_as_df("df_konversi")
        if df.empty:
            raise ValueError("Sheet df_konversi kosong")
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        required = ["category", "category_aspect_kafe", "aspect_condition"]
        missing  = [c for c in required if c not in df.columns]
        if missing:
            st.warning(f"⚠️ Kolom df_konversi tidak lengkap: {missing}")
            return pd.DataFrame(columns=required + ["_cat_norm"])
        df["_cat_norm"] = (df["category"].astype(str)
                           .str.lower().str.strip()
                           .str.replace(r"[\s\-_/]+", "_", regex=True))
        return df
    except Exception as e:
        st.warning(f"⚠️ Gagal load df_konversi dari Google Sheets: {e}")
        return pd.DataFrame(
            columns=["category", "category_aspect_kafe", "aspect_condition", "_cat_norm"]
        )


def _normalize_cat(s: str) -> str:
    return re.sub(r"[\s\-_/]+", "_", str(s).lower().strip())


def build_converted_df(raw_aspects_list: list, df_konv: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for asp in raw_aspects_list:
        cat     = str(asp.get("category", "")).strip()
        sent    = str(asp.get("sentiment", "positive")).strip().lower()
        conf    = float(asp.get("confidence", 0))
        src_rev = str(asp.get("_source_review", "")).strip()

        skor     = 1.0 if sent == "positive" else 0.0
        cat_norm = _normalize_cat(cat)

        cat_kafe = cat
        asp_cond = cat

        if not df_konv.empty and "_cat_norm" in df_konv.columns:
            match = df_konv[df_konv["_cat_norm"] == cat_norm]
            if match.empty:
                match = df_konv[
                    df_konv["_cat_norm"].str.contains(cat_norm, na=False, regex=False)
                ]
            if match.empty:
                match = df_konv[
                    df_konv["_cat_norm"].apply(lambda x: bool(x) and x in cat_norm)
                ]
            if not match.empty:
                row_k    = match.iloc[0]
                cat_kafe = str(row_k.get("category_aspect_kafe", cat))
                asp_cond = str(row_k.get("aspect_condition", cat))

        rows.append({
            "review"              : src_rev,
            "category_aspect_kafe": cat_kafe,
            "aspect_condition"    : asp_cond,
            "sentimen"            : sent,
            "skor"                : skor,
            "confidence"          : conf,
            "_aspect"             : str(asp.get("aspect", "")),
            "_category_raw"       : cat,
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["review", "category_aspect_kafe", "aspect_condition",
                 "sentimen", "skor", "confidence", "_aspect", "_category_raw"]
    )


df_konv      = load_konversi()
df_converted = build_converted_df(raw_aspects, df_konv)

# ════════════════════════════════════════════════════════════════
# PERHITUNGAN RUMUS A: IMDb Weighted Rating + SAW
# ════════════════════════════════════════════════════════════════
M_IMDB = 13


def compute_global_C_local(df: pd.DataFrame) -> float:
    if df.empty or "skor" not in df.columns:
        return 0.5
    total_pos = pd.to_numeric(df["skor"], errors="coerce").fillna(0).sum()
    total_v   = len(df)
    return float(total_pos / total_v) if total_v > 0 else 0.5


def compute_imdb_wr_local(v: float, R: float, C: float, m: int = M_IMDB) -> float:
    return (v / (m + v)) * R + (m / (m + v)) * C


def compute_saw_rumus_a(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["category_aspect_kafe", "skor_sentimen", "Vi"])

    need = ["category_aspect_kafe", "aspect_condition", "skor"]
    if not all(c in df.columns for c in need):
        return pd.DataFrame(columns=["category_aspect_kafe", "skor_sentimen", "Vi"])

    df = df.copy()
    df["skor"] = pd.to_numeric(df["skor"], errors="coerce").fillna(0)

    C = compute_global_C_local(df)

    grp  = df.groupby(["category_aspect_kafe", "aspect_condition"])
    r_ij = grp["skor"].mean().rename("R")
    v_ij = grp["skor"].count().rename("v")
    base = pd.concat([r_ij, v_ij], axis=1).reset_index()

    base["WR"] = base.apply(
        lambda row: compute_imdb_wr_local(float(row["v"]), float(row["R"]), C, M_IMDB),
        axis=1
    )

    max_wr_per_cat = (
        base.groupby("category_aspect_kafe")["WR"].max().rename("max_WR")
    )
    base = base.merge(max_wr_per_cat.reset_index(), on="category_aspect_kafe", how="left")

    base["Rij"] = base["WR"] / base["max_WR"].replace(0, 1e-9)

    n_conds_per_cat = (
        base.groupby("category_aspect_kafe")["aspect_condition"]
        .count().rename("n_conds")
    )
    base = base.merge(n_conds_per_cat.reset_index(), on="category_aspect_kafe", how="left")
    base["Wj"] = 1.0 / base["n_conds"].replace(0, 1.0)

    base["weighted"] = base["Wj"] * base["Rij"]
    vi_df = (
        base.groupby("category_aspect_kafe")["weighted"]
        .sum().rename("Vi").reset_index()
    )
    vi_df["skor_sentimen"] = (vi_df["Vi"] * 100).round(1)

    return vi_df.sort_values("skor_sentimen", ascending=False).reset_index(drop=True)


def compute_condition_rumus_a(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "aspect_condition" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["skor"] = pd.to_numeric(df["skor"], errors="coerce").fillna(0)

    C = compute_global_C_local(df)

    grp  = df.groupby(["category_aspect_kafe", "aspect_condition"])
    r    = grp["skor"].mean().rename("R").reset_index()
    n    = grp["skor"].count().rename("n_ij").reset_index()
    base = r.merge(n, on=["category_aspect_kafe", "aspect_condition"])

    base["WR"] = base.apply(
        lambda row: compute_imdb_wr_local(float(row["n_ij"]), float(row["R"]), C, M_IMDB),
        axis=1
    )
    base["skor_sentimen"] = (base["WR"] * 100).round(1)

    return base.sort_values(
        ["category_aspect_kafe", "skor_sentimen"], ascending=[True, False]
    ).reset_index(drop=True)


df_saw      = compute_saw_rumus_a(df_converted)
df_cond_saw = compute_condition_rumus_a(df_converted)

# ════════════════════════════════════════════════════════════════
# DATA UNTUK CHART
# ════════════════════════════════════════════════════════════════
_cond_data_json = df_cond_saw.to_dict("records") if not df_cond_saw.empty else []
_cond_data_str  = json.dumps(_cond_data_json)

if not df_saw.empty:
    _chart_data = df_saw[["category_aspect_kafe", "skor_sentimen"]].to_dict("records")
else:
    _chart_data = []
_chart_data_str = json.dumps(_chart_data)

# ════════════════════════════════════════════════════════════════
# PALET WARNA
# ════════════════════════════════════════════════════════════════
CAT_PALETTES = {
    0: {"bg": "#FFF0EB", "fg": "#C8502A", "bar": "#C8502A", "icon": "🍽️", "border": "#FDDDD5"},
    1: {"bg": "#FFF7E6", "fg": "#B8730A", "bar": "#F59E0B", "icon": "⭐", "border": "#FDECC8"},
    2: {"bg": "#EBF5FF", "fg": "#1A6EB0", "bar": "#3B82F6", "icon": "✨", "border": "#C3DEFF"},
    3: {"bg": "#F0FBF0", "fg": "#1A7A3C", "bar": "#22C55E", "icon": "💚", "border": "#BBF0CC"},
    4: {"bg": "#F5F0FF", "fg": "#7C3AED", "bar": "#8B5CF6", "icon": "💜", "border": "#D9C9FF"},
    5: {"bg": "#FFF0F5", "fg": "#BE185D", "bar": "#EC4899", "icon": "💗", "border": "#FFC9DE"},
}

def _pal(idx: int) -> dict:
    return CAT_PALETTES[idx % len(CAT_PALETTES)]

# ════════════════════════════════════════════════════════════════
# STATISTIK RINGKAS
# ════════════════════════════════════════════════════════════════
n_kafe_cat   = len(df_saw)
n_cond_total = (
    df_converted["aspect_condition"].nunique() if not df_converted.empty else 0
)
n_aspects = len(raw_aspects)

if not df_saw.empty and "Vi" in df_saw.columns:
    overall_vi = round(float(df_saw["Vi"].mean() * 100), 1)
elif not df_saw.empty and "skor_sentimen" in df_saw.columns:
    overall_vi = round(float(df_saw["skor_sentimen"].mean()), 1)
else:
    overall_vi = 0.0

truncated_note = ""
if was_truncated:
    truncated_note = (
        f"⚡ {n_analyzed} dari {jumlah_rev} review dianalisis (deduplikasi & batching)"
    )

_nama_kafe_safe = (
    str(nama_kafe)
    .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
)

_truncated_html = (
    f'<p style="font-size:.75rem;color:#F59E0B;margin:6px 0 0;">{truncated_note}</p>'
    if truncated_note else ""
)

# ════════════════════════════════════════════════════════════════
# HERO SECTION — satu components.html agar background gelap konsisten
# (st.markdown & st.columns tidak bisa dijadikan background gelap penuh
#  karena Streamlit selalu inject wrapper terang di antara elemen)
# ════════════════════════════════════════════════════════════════

_hero_truncated = (
    f'<p style="font-size:.72rem;color:#F59E0B;margin:5px 0 0 0;">{truncated_note}</p>'
    if truncated_note else ""
)

_hero_html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,900&family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
html, body {{ background:transparent; font-family:'Plus Jakarta Sans',sans-serif; }}
.hero {{
  background: linear-gradient(135deg,#1C1917 0%,#2d1a0e 60%,#3d2210 100%);
  padding: 26px 32px 26px;
  position: relative;
  overflow: hidden;
}}
.hero-coffee {{
  position:absolute; font-size:200px; opacity:.04;
  right:-10px; top:-40px; transform:rotate(15deg);
  pointer-events:none; line-height:1;
}}
.hero-inner {{
  position:relative; z-index:1;
  max-width:900px; margin:0 auto;
  display:flex; align-items:center;
  justify-content:space-between; gap:24px; flex-wrap:wrap;
}}
.hero-left {{ flex:1; min-width:220px; }}
.badge {{
  display:inline-flex; align-items:center; gap:5px;
  background:rgba(200,80,42,.35); color:#F9A07A;
  font-size:.6rem; font-weight:700; letter-spacing:1.4px;
  text-transform:uppercase; padding:4px 12px;
  border-radius:50px; margin-bottom:12px;
}}
.hero-title {{
  font-family:'Fraunces',serif;
  font-size:clamp(1.2rem,2vw,1.8rem);
  font-weight:900; color:#fff; margin:0 0 5px; line-height:1.2;
}}
.hero-sub {{
  font-size:.78rem; color:rgba(255,255,255,.4); margin:0; line-height:1.5;
}}
.hero-sub b {{ color:rgba(255,255,255,.7); }}
.stat-grid {{
  display:grid; grid-template-columns:repeat(4,1fr);
  gap:10px; flex-shrink:0; min-width:280px;
}}
.stat-box {{
  background:rgba(255,255,255,.08);
  border:1px solid rgba(255,255,255,.14);
  border-radius:13px; padding:13px 10px; text-align:center;
}}
.stat-box.accent {{
  background:rgba(200,80,42,.22);
  border-color:rgba(200,80,42,.4);
}}
.stat-num {{
  font-family:'Fraunces',serif;
  font-size:1.65rem; font-weight:900;
  line-height:1; margin-bottom:5px;
}}
.stat-lbl {{
  font-size:.6rem; color:rgba(255,255,255,.4);
  text-transform:uppercase; letter-spacing:.5px;
}}
</style>
</head><body>
<div class="hero">
  <div class="hero-coffee">☕</div>
  <div class="hero-inner">
    <div class="hero-left">
      <div class="badge">📊 Hasil Analisis ABSA</div>
      <h1 class="hero-title">{_nama_kafe_safe}</h1>
      <p class="hero-sub">Berbasis <b>{jumlah_rev} review</b> pelanggan</p>
      {_hero_truncated}
    </div>
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-num" style="color:#F9A07A;">{jumlah_rev}</div>
        <div class="stat-lbl">Review</div>
      </div>
      <div class="stat-box">
        <div class="stat-num" style="color:#6EE7B7;">{n_kafe_cat}</div>
        <div class="stat-lbl">Kategori</div>
      </div>
      <div class="stat-box">
        <div class="stat-num" style="color:#93C5FD;">{n_aspects}</div>
        <div class="stat-lbl">Aspek</div>
      </div>
      <div class="stat-box accent">
        <div class="stat-num" style="color:#FDA07A;">{overall_vi:.1f}%</div>
        <div class="stat-lbl">Skor Sentimen</div>
      </div>
    </div>
  </div>
</div>
</body></html>"""

components.html(_hero_html, height=140, scrolling=False)

# ════════════════════════════════════════════════════════════════
# MAIN CONTENT — satu kolom, terpusat, card-per-section
# ════════════════════════════════════════════════════════════════
st.markdown('<div class="page-body">', unsafe_allow_html=True)

if df_saw.empty:
    st.markdown("""
    <div class="section" style="text-align:center;padding:56px 24px;">
      <div style="font-size:3rem;margin-bottom:12px;">🔍</div>
      <div style="font-family:'Fraunces',serif;font-size:1.1rem;font-weight:800;
        color:#C8502A;margin-bottom:8px;">Tidak ada aspek terdeteksi</div>
      <div style="font-size:.84rem;color:#78716C;max-width:380px;margin:0 auto;line-height:1.6;">
        Coba masukkan review yang lebih deskriptif tentang makanan,
        pelayanan, atau suasana kafe.
      </div>
    </div>
    """, unsafe_allow_html=True)

else:
    # ── SECTION 1: Skor Sentimen per Kategori ─────────────────
    cat_cards_html = ""
    for i_cat, row in df_saw.reset_index(drop=True).iterrows():
        p           = _pal(i_cat)
        cat_kafe    = str(row["category_aspect_kafe"])
        cat_display = cat_kafe.replace("_", " ").title()
        pct         = float(row.get("skor_sentimen", 0))
        bar_w       = min(int(pct), 100)
        sent_label  = "Positif" if pct >= 50 else "Negatif"
        sent_color  = "#1A7A3C" if pct >= 50 else "#C8502A"
        sent_bg     = "#EDFAF2" if pct >= 50 else "#FFF0EB"

        cat_cards_html += f"""
<div onclick="showDetail('{cat_kafe}')"
  style="background:#FAFAF9;border:1.5px solid {p['border']};border-radius:12px;
  padding:13px 16px;cursor:pointer;transition:all .2s;margin-bottom:8px;"
  onmouseover="this.style.transform='translateX(3px)';this.style.boxShadow='0 4px 16px rgba(0,0,0,.08)';this.style.background='#fff';"
  onmouseout="this.style.transform='';this.style.boxShadow='';this.style.background='#FAFAF9';">
  <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:34px;height:34px;border-radius:9px;background:{p['bg']};
      display:flex;align-items:center;justify-content:center;font-size:.9rem;flex-shrink:0;">{p['icon']}</div>
    <div style="flex:1;min-width:0;">
      <div style="font-family:'Fraunces',serif;font-size:.88rem;font-weight:800;
        color:#1C1917;margin-bottom:5px;">{cat_display}</div>
      <div style="display:flex;align-items:center;gap:8px;">
        <div style="flex:1;height:6px;background:{p['bg']};border-radius:50px;overflow:hidden;">
          <div style="height:6px;width:{bar_w}%;background:{p['bar']};border-radius:50px;"></div>
        </div>
        <div style="font-size:.88rem;font-weight:800;color:{p['fg']};min-width:40px;text-align:right;">{pct:.1f}%</div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;align-items:flex-end;gap:3px;flex-shrink:0;margin-left:2px;">
      <div style="background:{sent_bg};color:{sent_color};font-size:.6rem;
        font-weight:700;padding:2px 8px;border-radius:50px;">{sent_label}</div>
      <div style="font-size:.58rem;color:#ccc;">detail ▸</div>
    </div>
  </div>
</div>"""

    cond_panel_html = """
<div class="detail-panel" id="detail-panel">
  <div id="detail-content"></div>
</div>"""

    combined_html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,900&family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:'Plus Jakarta Sans',sans-serif; background:transparent; padding:2px 0 4px; }}
.detail-panel {{
  display:none; background:#fff; border-radius:12px; border:1.5px solid #E8DDD5;
  padding:16px 18px; margin-top:2px; margin-bottom:4px;
  box-shadow:0 4px 14px rgba(0,0,0,.07);
}}
.detail-panel.visible {{ display:block; animation:fadeIn .18s ease; }}
@keyframes fadeIn {{ from {{ opacity:0;transform:translateY(-5px); }} to {{ opacity:1;transform:none; }} }}
.cond-row {{
  display:flex; align-items:center; gap:7px; margin-bottom:6px;
  padding:7px 9px; background:#F9F7F5; border-radius:8px;
  transition:background .15s;
}}
.cond-row:hover {{ background:#FFF0EB; }}
</style>
</head><body>
{cat_cards_html}
{cond_panel_html}
<script>
var condData = {_cond_data_str};
function _norm(s) {{ return String(s||'').toLowerCase().trim().replace(/[\\s\\-_\\/]+/g,'_'); }}
function showDetail(catKafe) {{
  var panel   = document.getElementById('detail-panel');
  var content = document.getElementById('detail-content');
  var catNorm = _norm(catKafe);
  var rows = condData.filter(function(r) {{ return _norm(r.category_aspect_kafe||'') === catNorm; }});
  if (!rows.length) {{ panel.className='detail-panel'; return; }}
  var maxPct   = Math.max.apply(null, rows.map(function(r){{return r.skor_sentimen||0;}}));
  var catTitle = catKafe.replace(/_/g,' ').replace(/\\b\\w/g,function(c){{return c.toUpperCase();}});
  var html = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">'
    + '<div>'
    + '<div style="font-size:.6rem;color:#aaa;font-weight:600;text-transform:uppercase;letter-spacing:.7px;margin-bottom:2px;">Detail Aspek</div>'
    + '<span style="font-family:serif;font-size:.92rem;font-weight:800;color:#1C1917;">'+catTitle+'</span>'
    + '</div>'
    + '<button onclick="hideDetail()" style="background:#F9F7F5;border:1.5px solid #E8DDD5;'
    + 'border-radius:50px;padding:3px 11px;cursor:pointer;font-size:.7rem;color:#78716C;font-weight:700;">&#10005; Tutup</button>'
    + '</div>';
  rows.forEach(function(r) {{
    var pct  = r.skor_sentimen || 0;
    var barW = maxPct > 0 ? Math.round((pct / maxPct) * 100) : 0;
    var sc   = pct >= 50 ? '#1A7A3C' : '#C8502A';
    var bar  = pct >= 50 ? '#22C55E' : '#EF4444';
    var bg   = pct >= 50 ? '#EDFAF2' : '#FFF0EB';
    var nij  = r.n_ij || 0;
    var cond = r.aspect_condition || '-';
    html += '<div class="cond-row">'
      + '<div style="width:6px;height:6px;border-radius:50%;background:'+bar+';flex-shrink:0;"></div>'
      + '<div style="flex:1;min-width:0;">'
      + '<div style="font-size:.76rem;font-weight:600;color:#1C1917;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+cond+'</div>'
      + '<div style="font-size:.59rem;color:#aaa;">'+nij+' data</div>'
      + '</div>'
      + '<div style="flex:1;height:5px;background:#EDE8E4;border-radius:50px;overflow:hidden;margin:0 8px;">'
      + '<div style="height:5px;background:'+bar+';border-radius:50px;width:'+barW+'%;"></div></div>'
      + '<div style="font-size:.78rem;font-weight:800;color:'+sc+';min-width:38px;text-align:right;">'+pct.toFixed(1)+'%</div>'
      + '<div style="background:'+bg+';color:'+sc+';font-size:.57rem;font-weight:700;padding:2px 6px;border-radius:50px;white-space:nowrap;margin-left:3px;">'+(pct>=50?'Positif':'Negatif')+'</div>'
      + '</div>';
  }});
  content.innerHTML = html;
  panel.className   = 'detail-panel visible';
  panel.scrollIntoView({{behavior:'smooth',block:'nearest'}});
}}
function hideDetail() {{ document.getElementById('detail-panel').className = 'detail-panel'; }}
</script>
</body></html>"""

    n_cards  = max(len(df_saw), 1)
    iframe_h = n_cards * 74 + 280

    st.markdown("""
    <div class="section">
      <div class="sec-hdr">
        <div class="sec-hdr-accent" style="background:#C8502A;"></div>
        <div>
          <p class="sec-hdr-title">Skor Sentimen per Kategori</p>
          <p class="sec-hdr-sub">Klik kartu untuk melihat detail aspek di dalamnya</p>
        </div>
      </div>
    """, unsafe_allow_html=True)

    components.html(combined_html, height=iframe_h, scrolling=False)

    st.markdown('</div>', unsafe_allow_html=True)

    # ── SECTION 2: Grafik Batang ──────────────────────────────
    if _chart_data:
        chart_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:'Plus Jakarta Sans',sans-serif; background:transparent; padding:2px 0 8px; }}
.bar-row {{ display:flex; align-items:center; gap:10px; margin-bottom:9px; }}
.bar-label {{ font-size:.8rem; font-weight:700; color:#1C1917; width:120px; flex-shrink:0; text-align:right; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.bar-track {{ flex:1; height:24px; background:#EDE8E4; border-radius:50px; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:50px; display:flex; align-items:center; padding:0 8px; font-size:.68rem; font-weight:800; color:#fff; white-space:nowrap; min-width:44px; }}
.bar-pct {{ font-size:.8rem; font-weight:800; min-width:44px; text-align:left; }}
.badge-sent {{ font-size:.58rem; font-weight:700; padding:2px 8px; border-radius:50px; white-space:nowrap; }}
</style>
</head><body>
<div id="chart-root"></div>
<script>
var data = {_chart_data_str};
var colors = ['#C8502A','#F59E0B','#3B82F6','#22C55E','#8B5CF6','#EC4899'];
data.sort(function(a,b){{ return b.skor_sentimen - a.skor_sentimen; }});
var html = '';
data.forEach(function(item, idx) {{
  var pct   = item.skor_sentimen || 0;
  var label = String(item.category_aspect_kafe || '').replace(/_/g,' ').replace(/\\b\\w/g, function(c){{ return c.toUpperCase(); }});
  var color   = colors[idx % colors.length];
  var sc      = pct >= 50 ? '#1A7A3C' : '#C8502A';
  var bgBadge = pct >= 50 ? '#EDFAF2' : '#FFF0EB';
  var sentTxt = pct >= 50 ? 'Positif' : 'Negatif';
  html += '<div class="bar-row">'
    + '<div class="bar-label" title="'+label+'">'+label+'</div>'
    + '<div class="bar-track"><div class="bar-fill" style="width:'+pct+'%;background:'+color+';">'+pct.toFixed(1)+'%</div></div>'
    + '<div class="bar-pct" style="color:'+sc+';">'+pct.toFixed(1)+'%</div>'
    + '<div class="badge-sent" style="background:'+bgBadge+';color:'+sc+';">'+sentTxt+'</div>'
    + '</div>';
}});
document.getElementById('chart-root').innerHTML = html || '<div style="color:#bbb;font-size:.84rem;padding:12px 0;">Tidak ada data</div>';
</script>
</body></html>"""

        chart_h = max(120, len(_chart_data) * 38 + 20)

        st.markdown("""
        <div class="section">
          <div class="sec-hdr">
            <div class="sec-hdr-accent" style="background:#3B82F6;"></div>
            <div>
              <p class="sec-hdr-title">Grafik Skor Sentimen per Kategori</p>
              <p class="sec-hdr-sub">Perbandingan skor antar kategori aspek kafe</p>
            </div>
          </div>
        """, unsafe_allow_html=True)

        components.html(chart_html, height=chart_h, scrolling=False)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── SECTION 3: Performa Tiap Aspek ───────────────────────
    if not df_cond_saw.empty:
        df_bar = df_cond_saw[["aspect_condition", "skor_sentimen", "n_ij"]].copy()
        df_bar = df_bar.sort_values("skor_sentimen", ascending=False).reset_index(drop=True)

        top5 = df_bar.head(5)
        bot5 = df_bar.tail(min(5, len(df_bar))).iloc[::-1].reset_index(drop=True)

        bar_items = []
        for _, r in bot5.iterrows():
            bar_items.append({"cond": str(r["aspect_condition"]), "pct": float(r["skor_sentimen"]), "n": int(r["n_ij"]), "type": "low"})
        for _, r in top5.iterrows():
            bar_items.append({"cond": str(r["aspect_condition"]), "pct": float(r["skor_sentimen"]), "n": int(r["n_ij"]), "type": "high"})

        bar_json = json.dumps(bar_items)

        bar_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:'Plus Jakarta Sans',sans-serif; background:transparent; padding:2px 0 8px; }}
.group-wrap {{ background:#FAFAF9; border-radius:11px; border:1.5px solid #EDE8E4; padding:14px 16px; margin-bottom:10px; }}
.group-wrap:last-child {{ margin-bottom:0; }}
.group-label {{ font-size:.64rem; font-weight:800; letter-spacing:.8px; text-transform:uppercase; padding:3px 9px; border-radius:6px; margin-bottom:10px; display:inline-block; }}
.bar-row {{ display:flex; align-items:center; gap:8px; margin-bottom:7px; }}
.bar-row:last-child {{ margin-bottom:0; }}
.bar-label {{ font-size:.76rem; font-weight:600; color:#1C1917; width:150px; flex-shrink:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-align:right; }}
.bar-wrap {{ flex:1; height:18px; background:#EDE8E4; border-radius:50px; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:50px; display:flex; align-items:center; padding-left:7px; font-size:.6rem; font-weight:700; color:#fff; white-space:nowrap; }}
.bar-n {{ font-size:.59rem; color:#bbb; min-width:40px; text-align:left; }}
</style>
</head><body>
<div id="chart-root"></div>
<script>
var items    = {bar_json};
var lowItems  = items.filter(function(x){{ return x.type === 'low'; }});
var highItems = items.filter(function(x){{ return x.type === 'high'; }});
function makeRow(item) {{
  var isHigh = item.type === 'high';
  var color  = isHigh ? '#22C55E' : '#EF4444';
  var pct    = item.pct.toFixed(1);
  return '<div class="bar-row">'
    + '<div class="bar-label" title="'+item.cond+'">'+item.cond+'</div>'
    + '<div class="bar-wrap"><div class="bar-fill" style="width:'+item.pct+'%;background:'+color+';">'+pct+'%</div></div>'
    + '<div class="bar-n">'+item.n+' data</div>'
    + '</div>';
}}
var html = '';
if (highItems.length) {{
  html += '<div class="group-wrap">';
  html += '<div class="group-label" style="background:#EDFAF2;color:#1A7A3C;">&#10003; Aspek Terkuat</div>';
  highItems.forEach(function(it){{ html += makeRow(it); }});
  html += '</div>';
}}
if (lowItems.length) {{
  html += '<div class="group-wrap">';
  html += '<div class="group-label" style="background:#FFF0EB;color:#C8502A;">&#9888; Perlu Perhatian</div>';
  lowItems.forEach(function(it){{ html += makeRow(it); }});
  html += '</div>';
}}
document.getElementById('chart-root').innerHTML = html;
</script>
</body></html>"""

        n_items = len(bar_items)
        bar_h   = max(200, n_items * 30 + 110)

        st.markdown("""
        <div class="section">
          <div class="sec-hdr">
            <div class="sec-hdr-accent" style="background:#22C55E;"></div>
            <div>
              <p class="sec-hdr-title">Performa Tiap Aspek</p>
              <p class="sec-hdr-sub">Aspek terkuat &amp; yang perlu perhatian berdasarkan skor sentimen</p>
            </div>
          </div>
        """, unsafe_allow_html=True)

        components.html(bar_html, height=bar_h, scrolling=False)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── SECTION 4: Ringkasan Analisis ────────────────────────
    if not df_cond_saw.empty:
        best_cond  = df_cond_saw.sort_values("skor_sentimen", ascending=False).iloc[0]
        worst_cond = df_cond_saw.sort_values("skor_sentimen", ascending=True).iloc[0]
        best_name  = str(best_cond["aspect_condition"])
        worst_name = str(worst_cond["aspect_condition"])
        best_pct   = float(best_cond["skor_sentimen"])
        worst_pct  = float(worst_cond["skor_sentimen"])

        perlu_naik = df_cond_saw[df_cond_saw["skor_sentimen"] < 50].sort_values("skor_sentimen")
        perlu_jaga = df_cond_saw[df_cond_saw["skor_sentimen"] >= 70].sort_values("skor_sentimen", ascending=False)

        naik_list = ", ".join(
            f"<b>{r['aspect_condition']}</b> ({r['skor_sentimen']:.0f}%)"
            for _, r in perlu_naik.head(3).iterrows()
        )
        jaga_list = ", ".join(
            f"<b>{r['aspect_condition']}</b> ({r['skor_sentimen']:.0f}%)"
            for _, r in perlu_jaga.head(3).iterrows()
        )

        deskripsi_naik = (
            f"Aspek yang perlu perhatian: {naik_list}."
            if naik_list
            else "Semua aspek mendapat respons positif dari pelanggan."
        )
        deskripsi_jaga = (
            f"Aspek unggulan yang sudah berjalan baik: {jaga_list}. Pertahankan kualitas aspek-aspek ini."
            if jaga_list
            else "Tingkatkan konsistensi layanan agar pelanggan semakin puas."
        )

        st.markdown(f"""
<div class="section" style="background:linear-gradient(135deg,#FFFBF8 0%,#FFF7F3 100%);">
  <div class="sec-hdr">
    <div class="sec-hdr-accent" style="background:#F59E0B;"></div>
    <div><p class="sec-hdr-title">Ringkasan Analisis</p></div>
  </div>
  <p style="font-size:.84rem;color:#44352C;line-height:1.75;margin:0 0 8px;">{deskripsi_naik}</p>
  <p style="font-size:.84rem;color:#44352C;line-height:1.75;margin:0 0 14px;">{deskripsi_jaga}</p>
  <div style="display:flex;gap:8px;flex-wrap:wrap;">
    <span style="background:#EDFAF2;color:#1A7A3C;font-size:.72rem;font-weight:700;padding:5px 13px;border-radius:50px;">✓ Terbaik: {best_name} ({best_pct:.0f}%)</span>
    <span style="background:#FFF0EB;color:#C8502A;font-size:.72rem;font-weight:700;padding:5px 13px;border-radius:50px;">⚠ Terendah: {worst_name} ({worst_pct:.0f}%)</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── SECTION 5: Data Lengkap + Download ───────────────────────
if not df_converted.empty:
    df_valid_conv = df_converted[
        df_converted["aspect_condition"].notna()
        & (df_converted["aspect_condition"].astype(str).str.strip() != "")
        & df_converted["sentimen"].notna()
        & (df_converted["sentimen"].astype(str).str.strip() != "")
    ].copy()

    n_rows_conv = len(df_valid_conv)

    tampil_cols = [
        "review", "category_aspect_kafe", "aspect_condition",
        "sentimen", "skor", "confidence"
    ]
    tampil_cols_exist = [c for c in tampil_cols if c in df_valid_conv.columns]

    rename_map = {
        "review"              : "Review",
        "category_aspect_kafe": "Kategori Kafe",
        "aspect_condition"    : "Aspek Kondisi",
        "sentimen"            : "Sentimen",
        "skor"                : "Skor Sentimen",
        "confidence"          : "Confidence (%)",
    }

    df_download = df_valid_conv[tampil_cols_exist].copy()
    df_download = df_download.rename(columns=rename_map)

    def to_excel_bytes(df: pd.DataFrame) -> bytes:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Hasil Analisis")
        return buf.getvalue()

    excel_bytes = to_excel_bytes(df_download)

    st.markdown('<div class="section" style="padding:0;">', unsafe_allow_html=True)
    with st.expander(
        f"📋 Lihat Data Lengkap — {n_rows_conv} aspek terdeteksi", expanded=False
    ):
        col_dl, col_info_dl = st.columns([2, 5])
        with col_dl:
            st.download_button(
                label="⬇️ Download Excel",
                data=excel_bytes,
                file_name=f"hasil_analisis_{str(nama_kafe).replace(' ','_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_download_excel",
                use_container_width=True,
            )
        with col_info_dl:
            st.markdown(
                f'<div style="font-size:.74rem;color:#78716C;padding-top:8px;">'
                f'📊 {n_rows_conv} baris · kolom: Review, Kategori, Aspek, Skor Sentimen, Confidence</div>',
                unsafe_allow_html=True
            )

        st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)

        df_show = df_valid_conv[tampil_cols_exist].copy()

        if "sentimen" in df_show.columns:
            df_show["sentimen"] = df_show["sentimen"].apply(
                lambda x: f"✅ {x}" if str(x).lower() == "positive" else f"❌ {x}"
            )
        if "skor" in df_show.columns:
            df_show["skor"] = df_show["skor"].apply(
                lambda x: int(float(x)) if pd.notna(x) else 0
            )
        if "confidence" in df_show.columns:
            df_show["confidence"] = df_show["confidence"].apply(
                lambda x: f"{float(x):.1f}%" if pd.notna(x) else "—"
            )
        if "review" in df_show.columns:
            df_show["review"] = df_show["review"].apply(
                lambda x: str(x)[:90] + "…" if len(str(x)) > 90 else str(x)
            )

        df_show = df_show.rename(columns=rename_map).reset_index(drop=True)
        df_show.index = df_show.index + 1

        st.dataframe(
            df_show,
            use_container_width=True,
            height=min(440, n_rows_conv * 38 + 60),
        )
        st.markdown(
            f'<div style="font-size:.72rem;color:#bbb;margin-top:4px;">'
            f'Total: {n_rows_conv} baris — 1 baris = 1 aspek terdeteksi dari review</div>',
            unsafe_allow_html=True
        )
    st.markdown('</div>', unsafe_allow_html=True)

else:
    st.markdown("""
    <div class="section" style="background:#FFFBEB;border-color:#F59E0B;">
      <b style="color:#B8730A;">⚠️ Data konversi kosong.</b><br>
      <span style="font-size:.82rem;color:#78716C;">
        Model tidak menemukan aspek dari review yang diinput, atau df_konversi tidak dapat dibaca dari Google Sheets.
      </span>
    </div>
    """, unsafe_allow_html=True)

# ── Tombol Kembali ────────────────────────────────────────────
st.markdown('<div style="margin-top:4px;">', unsafe_allow_html=True)
_, col_back_btn, _ = st.columns([1, 10, 1])
with col_back_btn:
    col_b, _ = st.columns([3, 9])
    with col_b:
        if st.button("← Analisis Review Baru", key="btn_back_main"):
            if "analisis_result" in st.session_state:
                del st.session_state["analisis_result"]
            st.switch_page("pages/app_kafe1.py")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)  # close .page-body

# ════════════════════════════════════════════════════════════════
# FOOTER
# ════════════════════════════════════════════════════════════════
st.markdown("""
<div style="background:#111;padding:18px 40px;text-align:center;
  color:rgba(255,255,255,.22);font-size:.72rem;">
  &copy; 2025 &nbsp;<b style="color:#C8502A;">KafeSby</b>
  &nbsp;&middot; Rekomendasi Kafe Surabaya Berbasis Review Pengunjung
</div>
""", unsafe_allow_html=True)
