# ============================================================
# SISTEM REKOMENDASI KAFE SURABAYA — app_kafe1.py (Logged-in)
# Versi Streamlit Cloud
#
# PERBAIKAN PERFORMA [PATCH-FLICKER]:
#   [F1] Semua slideshow per-kategori digabung jadi SATU
#        components.html → eliminasi kelap-kelip saat scroll
#        dan saat switch tab/aspek.
#   [F2] HTML slideshow di-cache via @st.cache_data sehingga
#        tidak di-rebuild setiap Streamlit re-run.
#   [F4] Guard _best_rendered_1 di session_state: slideshow
#        hanya di-inject ulang jika data benar-benar berubah.
#   Perbaikan lain tidak diubah dari PATCH-LOADING sebelumnya.
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import urllib.parse
import json, io, os, sys, hashlib, tempfile, requests

from utils_kafe import (
    load_data,
    compute_best_per_category_imdb,
    precompute_top5_conditions_imdb,
    compute_overall_score,
    gdrive_direct_url, build_slideshow_html, COMMON_CSS
)
from users_manager import (
    load_users,
    get_user_favorites,
)

st.set_page_config(
    page_title="Rekomendasi Kafe Surabaya",
    page_icon="☕", layout="wide",
    initial_sidebar_state="collapsed",
)
import os
_IS_HEALTH_CHECK = os.environ.get("STREAMLIT_HEALTH_CHECK", "") == "true"

# ════════════════════════════════════════════════════════════════
# QUERY PARAMS
# ════════════════════════════════════════════════════════════════
_qp = st.query_params

# ════════════════════════════════════════════════════════════════
# RESTORE LOGIN DARI URL (TAB BARU)
# ════════════════════════════════════════════════════════════════
if _qp.get("user"):
    st.session_state["logged_in"] = True
    if _qp.get("is_google") == "True":
        st.session_state["login_google"] = _qp.get("user")
    else:
        st.session_state["login_username"] = _qp.get("user")

# ════════════════════════════════════════════════════════════════
# NAVIGASI KE DETAIL (HARUS DI ATAS GUARD!)
# ════════════════════════════════════════════════════════════════
if _qp.get("nav_kid") and _qp.get("nav_nama"):
    _kid  = _qp.get("nav_kid")
    _nama = _qp.get("nav_nama")
    _cat  = _qp.get("nav_cat", "")
    st.session_state["detail_kid"]        = _kid
    st.session_state["detail_nama"]       = _nama
    st.session_state["detail_source"]     = "kasus_e"
    st.session_state["detail_cat_chosen"] = _cat
    st.query_params.clear()
    st.session_state["_prev_page"] = "pages/app_kafe1.py"
    st.switch_page("pages/skemacari1.py")

# ════════════════════════════════════════════════════════════════
# GUARD LOGIN
# ════════════════════════════════════════════════════════════════
if not st.session_state.get("logged_in", False):
    st.switch_page("app_kafe.py")

# ════════════════════════════════════════════════════════════════
# IMPORT absa_engine
# ════════════════════════════════════════════════════════════════
_engine_available    = False
_engine_import_error = ""

for _search_path in ["/app", "/app/pages", os.getcwd(),
                     os.path.join(os.getcwd(), "pages")]:
    if _search_path not in sys.path:
        sys.path.insert(0, _search_path)

try:
    import absa_engine as _absa_engine
    _engine_available    = True
    _engine_import_error = ""
except Exception as _e:
    _engine_available    = False
    _engine_import_error = str(_e)

# ════════════════════════════════════════════════════════════════
# PRE-WARM ABSA MODELS
# ════════════════════════════════════════════════════════════════
def _prewarm_absa_models():
    if st.session_state.get("_absa_warmed", False):
        return True
    if not _engine_available:
        return False
    try:
        _absa_engine.load_glove()
        _absa_engine._get_nlp()
        asp_model, asp_cfg = _absa_engine.load_aspect_model_engine()
        sent_model, sent_cfg = _absa_engine.load_sent_model_engine()
        if asp_model is None or sent_model is None:
            st.session_state["_absa_warmed"]     = False
            st.session_state["_absa_warm_error"] = "Model gagal di-load (None)"
            return False
        _absa_engine.load_konversi_df()
        st.session_state["_absa_warmed"]     = True
        st.session_state["_absa_warm_error"] = ""
        return True
    except Exception as e:
        st.session_state["_absa_warmed"]     = False
        st.session_state["_absa_warm_error"] = str(e)
        return False

# ════════════════════════════════════════════════════════════════
# INFO USER
# ════════════════════════════════════════════════════════════════
_login_username = st.session_state.get("login_username", "")
_login_google   = st.session_state.get("login_google", "")
_is_google      = bool(_login_google)
_display_name   = _login_username if not _is_google else _login_google.replace("@gmail.com", "")
_identifier     = _login_google if _is_google else _login_username

# ════════════════════════════════════════════════════════════════
# LOAD DATA — via Google Sheets
# ════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def get_df():
    df = load_data()
    df["skor_sentimen"] = pd.to_numeric(df["skor_sentimen"], errors="coerce").fillna(0)
    df["kafe_id"]       = df["kafe_id"].astype(str)
    return df

df = get_df()

@st.cache_data(show_spinner=False)
def get_best_per_category(_dataframe: pd.DataFrame) -> pd.DataFrame:
    return compute_best_per_category_imdb(_dataframe)

@st.cache_data(show_spinner=False)
def precompute_all_top5(_dataframe: pd.DataFrame) -> dict:
    return precompute_top5_conditions_imdb(_dataframe)

@st.cache_data(show_spinner=False)
def get_kafe_per_condition(cond: str) -> set:
    sub = df[df["aspect_condition"] == cond]
    return set(sub["kafe_id"].unique().tolist())

@st.cache_data(show_spinner=False)
def get_jumlah_review_per_kafe(_dataframe: pd.DataFrame) -> dict:
    if "review_id" in _dataframe.columns:
        return _dataframe.groupby("kafe_id")["review_id"].nunique().to_dict()
    elif "review" in _dataframe.columns:
        return _dataframe.groupby("kafe_id")["review"].nunique().to_dict()
    return {}

@st.cache_data(show_spinner=False)
def get_reviewer_aktif_per_kafe(_dataframe: pd.DataFrame) -> dict:
    if "status_reviewer" not in _dataframe.columns or "review_id" not in _dataframe.columns:
        return {}
    result = {}
    for kid, grp in _dataframe.groupby("kafe_id"):
        dedup = grp.drop_duplicates(subset=["review_id"])
        total = len(dedup)
        if total == 0:
            result[kid] = 0.0
            continue
        aktif = dedup["status_reviewer"].astype(str).str.lower().str.strip().eq("aktif").sum()
        result[kid] = round((aktif / total) * 100, 1)
    return result

# [P1] Guard precompute
if "precompute_done_1" not in st.session_state:
    with st.spinner("☕ Memuat data kafe..."):
        best_df      = get_best_per_category(df)
        _top5_lookup = precompute_all_top5(df)
    st.session_state["precompute_done_1"]  = True
    st.session_state["_cached_best_df_1"]  = best_df
    st.session_state["_cached_top5_1"]     = _top5_lookup
else:
    best_df      = st.session_state["_cached_best_df_1"]
    _top5_lookup = st.session_state["_cached_top5_1"]

_jml_review_map     = get_jumlah_review_per_kafe(df)
_reviewer_aktif_map = get_reviewer_aktif_per_kafe(df)

def find_kafe_for_prefs(pref_items: list, lokasi: str) -> tuple:
    if not pref_items:
        if lokasi and "kecamatan_kafe" in df.columns:
            kids = set(df[df["kecamatan_kafe"].str.lower() == lokasi.lower()]["kafe_id"].unique())
        else:
            kids = set(df["kafe_id"].unique())
        return kids, {}
    per_cond = {c: get_kafe_per_condition(c) for c in pref_items}
    valid = None
    for kids in per_cond.values():
        valid = set(kids) if valid is None else valid & kids
    if valid is None:
        valid = set()
    if lokasi and "kecamatan_kafe" in df.columns:
        lok_kids = set(df[df["kecamatan_kafe"].str.lower() == lokasi.lower()]["kafe_id"].unique())
        valid = valid & lok_kids
    return valid, per_cond

def suggest_remove_aspect(pref_items: list, lokasi: str) -> list:
    suggestions = []
    for cond in pref_items:
        remaining  = [c for c in pref_items if c != cond]
        valid_kids, _ = find_kafe_for_prefs(remaining, lokasi)
        if valid_kids:
            suggestions.append((cond, len(valid_kids)))
    suggestions.sort(key=lambda x: x[1], reverse=True)
    return suggestions

# ════════════════════════════════════════════════════════════════
# LOOKUP TABLES
# ════════════════════════════════════════════════════════════════
all_nama      = sorted(df["nama_kafe"].dropna().unique().tolist())
all_condition = sorted(df["aspect_condition"].dropna().unique().tolist())
unique_cats   = sorted(df["category_aspect_kafe"].dropna().unique().tolist())

all_kecamatan_search = sorted(df["kecamatan_kafe"].dropna().unique().tolist()) if "kecamatan_kafe" in df.columns else []

if "kecamatan_kafe" in df.columns:
    all_kecamatan = sorted(df["kecamatan_kafe"].dropna().unique().tolist())
else:
    all_kecamatan = []

cat_cond_map = {
    cat: sorted(df[df["category_aspect_kafe"]==cat]["aspect_condition"].dropna().unique().tolist())
    for cat in unique_cats
}
nama_to_kafeid      = df.drop_duplicates("nama_kafe").set_index("nama_kafe")["kafe_id"].to_dict()
kecamatan_to_kafeid = {}
if "kecamatan_kafe" in df.columns:
    for kec in all_kecamatan_search:
        sub_kec = df[df["kecamatan_kafe"] == kec]["kafe_id"].unique().tolist()
        kecamatan_to_kafeid[kec] = sub_kec

nama_set      = set(all_nama)
kecamatan_set = set(all_kecamatan_search)
cond_set      = set(all_condition)

# ════════════════════════════════════════════════════════════════
# ICONS / BADGE
# ════════════════════════════════════════════════════════════════
_pal = [
    ("&#129369;","badge-c0","icon-c0","#FAFAF8"),
    ("&#127869;","badge-c1","icon-c1","#FAFAF8"),
    ("&#10024;", "badge-c2","icon-c2","#ffffff"),
    ("&#128176;","badge-c3","icon-c3","#FAFAF8"),
    ("&#9749;",  "badge-c4","icon-c4","#ffffff"),
    ("&#127968;","badge-c5","icon-c5","#FAFAF8"),
]
CAT_ICONS={}; CAT_BADGE={}; CAT_ICON_CLS={}; CAT_BG={}
for idx, cat in enumerate(unique_cats):
    ico, badge, icls, bg = _pal[idx % len(_pal)]
    CAT_ICONS[cat]=ico; CAT_BADGE[cat]=badge; CAT_ICON_CLS[cat]=icls; CAT_BG[cat]=bg

_clrs = [("#FFF0EB","#C8502A"),("#FFF7E6","#B8730A"),("#EBF5FF","#1A6EB0"),
         ("#F0FBF0","#1A7A3C"),("#F5F0FF","#7C3AED"),("#FFF0F5","#BE185D")]
badge_css = ""
for idx, cat in enumerate(unique_cats):
    bg_c, fg_c = _clrs[idx % len(_clrs)]
    badge_css += f".{CAT_BADGE[cat]}{{background:{bg_c};color:{fg_c};}}.{CAT_ICON_CLS[cat]}{{background:{bg_c};}}\n"

# ════════════════════════════════════════════════════════════════
# CSS
# ════════════════════════════════════════════════════════════════
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,700;9..144,900&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
:root{{--rust:#C8502A;--rust-dk:#A33E20;--rust-lt:#FFF0EB;--ink:#1C1917;--muted:#78716C;--border:#E8DDD5;}}
html,body,[class*="css"]{{font-family:'Plus Jakarta Sans',sans-serif;background:#fff;color:var(--ink);}}
.stApp{{background:#fff;}}
#MainMenu,footer,header{{visibility:hidden;}}
.block-container{{padding-top:0!important;padding-left:0!important;padding-right:0!important;max-width:100%!important;}}
.topbar{{display:flex;align-items:center;justify-content:space-between;padding:13px 40px;background:#fff;border-bottom:1px solid var(--border);box-shadow:0 2px 16px rgba(28,25,23,.05);position:sticky;top:0;z-index:999;}}
.topbar-logo{{font-family:'Fraunces',serif;font-size:1.4rem;font-weight:900;color:var(--ink);letter-spacing:-.5px;}}
.topbar-logo span{{color:var(--rust);}}
.topbar-nav{{display:flex;gap:2px;align-items:center;}}
.nav-link{{text-decoration:none;color:var(--muted);font-size:.78rem;font-weight:600;padding:7px 11px;border-radius:8px;transition:background .18s,color .18s;white-space:nowrap;}}
.nav-link:hover{{background:var(--rust-lt);color:var(--rust);}}
.section-divider{{border:none;border-top:1px solid var(--border);margin:0;}}
.section-header-hl{{display:flex;align-items:center;gap:16px;padding:18px 28px;border-radius:14px;margin-bottom:28px;}}
.section-header-hl.blue{{background:linear-gradient(90deg,#EFF6FF,#F5F9FF);border-left:4px solid #3B82F6;}}
.hl-icon{{font-size:1.8rem;flex-shrink:0;}}
.hl-title{{font-family:'Fraunces',serif;font-size:1.45rem;font-weight:900;color:var(--ink);margin:0;}}
.hl-sub{{font-size:.84rem;color:var(--muted);margin:0;line-height:1.5;}}
{badge_css}
.footer{{background:#111;padding:22px 48px;text-align:center;color:rgba(255,255,255,.22);font-size:.74rem;}}
.footer b{{color:var(--rust);}}
div[data-testid="stSelectbox"] > div > div {{
    border-radius: 60px !important; border: 2px solid #E8DDD5 !important;
    box-shadow: 0 6px 28px rgba(200,80,42,.11) !important; font-size: .95rem !important; background: #fff !important;
}}
div[data-testid="stSelectbox"] label {{ display: none !important; }}
div[data-testid="stButton"] button {{
    border-radius: 50px !important; background: #C8502A !important; color: white !important;
    border: none !important; font-weight: 700 !important; font-size: .9rem !important;
    padding: 10px 28px !important; min-height: 46px !important;
}}
div[data-testid="stButton"] button:hover {{ background: #A33E20 !important; }}
div[data-testid="stButton"] button:disabled {{ background: #E8DDD5 !important; color: #aaa !important; }}
div[data-testid="stMultiSelect"] > label {{ display: none !important; }}
div[data-testid="stMultiSelect"] > div {{
    border-radius: 12px !important; border: 1.5px solid #E8DDD5 !important; background: #fff !important;
}}
div[data-testid="stNumberInput"] > div > input {{
    border-radius: 8px !important; border: 1.5px solid #E8DDD5 !important;
}}
div[data-testid="stExpander"] {{
    border: 1.5px solid #E8DDD5 !important; border-radius: 12px !important; background: #fff !important;
}}
div[data-testid="stExpander"] summary {{ font-size: .84rem !important; font-weight: 600 !important; color: #C8502A !important; }}
.pref-native-wrap {{ background: #fff; padding: 32px 48px 40px; }}
.pref-section-hdr {{
    display: flex; align-items: center; gap: 16px; padding: 18px 28px; border-radius: 14px; margin-bottom: 28px;
    background: linear-gradient(90deg, #EDFAF2, #F4FDF7); border-left: 4px solid #22C55E;
}}
.pref-hdr-icon {{ font-size: 1.8rem; flex-shrink: 0; }}
.pref-hdr-title {{ font-family: 'Fraunces', serif; font-size: 1.45rem; font-weight: 900; color: #1C1917; margin: 0; }}
.pref-hdr-sub {{ font-size: .84rem; color: #78716C; margin: 0; line-height: 1.5; }}
.cat-block-native {{ background: #FAFAF8; border: 1.5px solid #E8DDD5; border-radius: 14px; padding: 16px 20px 14px; margin-bottom: 12px; }}
.cat-block-ico {{ width: 30px; height: 30px; border-radius: 8px; background: #FFF0EB; display: flex; align-items: center; justify-content: center; font-size: .9rem; flex-shrink: 0; }}
.cat-block-nm {{ font-family: 'Fraunces', serif; font-size: .92rem; font-weight: 700; color: #1C1917; text-transform: capitalize; }}
.cmp-native-wrap {{ background: #FAFAF8; padding: 32px 48px 40px; }}
.cmp-section-hdr {{ display: flex; align-items: center; gap: 16px; padding: 18px 28px; border-radius: 14px; margin-bottom: 28px; background: linear-gradient(90deg, #FFFBEB, #FFFDF5); border-left: 4px solid #F59E0B; }}
div[data-testid="stTextInput"] input {{
    border-radius: 10px !important; border: 1.5px solid #E8DDD5 !important; font-size: .9rem !important; color: #1C1917 !important;
}}
div[data-testid="stTextArea"] textarea {{
    border-radius: 10px !important; border: 1.5px solid #E8DDD5 !important; font-size: .88rem !important; color: #1C1917 !important;
}}
div[data-testid="stRadio"] > label {{ display: none !important; }}
div[data-testid="stRadio"] > div > label {{
    background: #F9F7F5 !important; border: 1.5px solid #E8DDD5 !important;
    border-radius: 50px !important; padding: 6px 16px !important; font-size: .84rem !important; font-weight: 600 !important; color: #78716C !important; cursor: pointer !important;
}}
div[data-testid="stRadio"] > div > label:has(input:checked) {{
    background: #FFF0EB !important; border-color: #C8502A !important; color: #C8502A !important;
}}
.lokasi-label {{
    font-size: .84rem !important; font-weight: 600 !important;
    color: #78716C !important; margin-bottom: 4px !important;
}}
.fav-btn-wrap div[data-testid="stButton"] button {{
    min-height: 34px !important; height: 34px !important; padding: 4px 14px !important;
    font-size: .76rem !important; font-weight: 700 !important; background: #FFF0EB !important;
    color: #C8502A !important; border: 1.5px solid rgba(200,80,42,.3) !important;
    border-radius: 8px !important; line-height: 1 !important; white-space: nowrap !important;
    position: fixed !important; top: 12px !important; right: 40px !important;
    z-index: 1000 !important; width: auto !important;
}}
.fav-btn-wrap div[data-testid="stButton"] button:hover {{ background: #FFE0D4 !important; }}
/* CSS slideshow inline */
.slide-section-wrap {{overflow:hidden;}}
.slide-track-outer {{position:relative;padding:0 0 4px;}}
.slide-track {{display:flex;gap:16px;overflow-x:auto;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;padding:4px 44px 12px;scrollbar-width:thin;scrollbar-color:rgba(200,80,42,.3) transparent;}}
.slide-track::-webkit-scrollbar {{height:5px;}}
.slide-track::-webkit-scrollbar-track {{background:transparent;}}
.slide-track::-webkit-scrollbar-thumb {{background:rgba(200,80,42,.3);border-radius:10px;}}
.slide-btn {{position:absolute;top:50%;transform:translateY(-60%);width:36px;height:36px;border-radius:50%;background:#fff;border:1.5px solid #E8DDD5;box-shadow:0 2px 8px rgba(0,0,0,.12);cursor:pointer;font-size:1rem;font-weight:700;color:#C8502A;display:flex;align-items:center;justify-content:center;z-index:10;line-height:1;}}
.slide-btn-left {{left:4px;}}
.slide-btn-right {{right:4px;}}
.slide-card {{flex-shrink:0;scroll-snap-align:start;}}
.slide-card-inner {{background:#fff;border-radius:14px;border:1.5px solid #E8DDD5;overflow:hidden;box-shadow:0 2px 10px rgba(28,25,23,.07);transition:transform .2s,box-shadow .2s;}}
.slide-card-inner:hover {{transform:translateY(-4px);box-shadow:0 8px 24px rgba(28,25,23,.13);}}
.slide-counter {{text-align:center;font-size:.72rem;color:#aaa;font-weight:500;margin-top:2px;}}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# SESSION STATE INIT
# ════════════════════════════════════════════════════════════════
for _k, _v in [
    ("show_no_kafe_popup", False), ("no_kafe_suggestions", []),
    ("show_lokasi_only_popup", False), ("pending_lokasi", ""),
    ("analisis_processing", False), ("analisis_error", ""),
    ("go_to_favorit", False),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

if st.session_state.get("_nav_to_detail"):
    _kid  = st.session_state.pop("_nav_to_detail")
    _nama = st.session_state.pop("_nav_to_detail_nama", "")
    st.session_state["detail_kid"]  = _kid
    st.session_state["detail_nama"] = _nama
    st.session_state["_prev_page"] = "pages/app_kafe1.py"
    st.switch_page("pages/skemacari1.py")

if st.session_state.get("go_to_favorit", False):
    st.session_state["go_to_favorit"] = False
    st.switch_page("pages/favoritekafe.py")

# ════════════════════════════════════════════════════════════════
# NAVBAR
# ════════════════════════════════════════════════════════════════
st.markdown("""
<div class="topbar">
  <div class="topbar-logo">Kafe<span>Sby</span></div>
  <nav class="topbar-nav">
    <a class="nav-link" href="?">&#128269; Cari Kafe</a>
    <a class="nav-link" href="#best-section">&#11088; Best Kafe</a>
    <a class="nav-link" href="#compare-section">&#9878; Bandingkan</a>
    <a class="nav-link" href="#analisis-section">&#128200; Analisis</a>
  </nav>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="fav-btn-wrap">', unsafe_allow_html=True)
if st.button("❤️ My Favorite", key="btn_my_fav_nav"):
    st.session_state["go_to_favorit"] = True
    st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# SALAM USER
# ════════════════════════════════════════════════════════════════
st.markdown(f"""
<div style="background:linear-gradient(90deg,#FFF8F3,#FFF1E8);padding:18px 48px 14px;border-bottom:1px solid #E8DDD5;">
  <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
    <span style="font-size:1.5rem;">👋</span>
    <span style="font-family:'Fraunces',serif;font-size:1.3rem;font-weight:900;color:#1C1917;">
      Halo, <span style="color:#C8502A;">{_display_name}</span>!
    </span>
    <span style="font-size:.78rem;color:#78716C;">Selamat datang kembali di KafeSby ☕</span>
  </div>
</div>
""", unsafe_allow_html=True)
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# HERO
# ════════════════════════════════════════════════════════════════
st.markdown("""
<div style="text-align:center;background:linear-gradient(135deg,#FFF8F3,#FFF1E8 55%,#FFE8D6);
  padding:56px 48px 28px;position:relative;overflow:hidden;">
  <div style="position:absolute;font-size:260px;opacity:.03;top:-40px;right:-10px;transform:rotate(12deg);pointer-events:none;">☕</div>
  <div style="display:inline-flex;align-items:center;gap:6px;background:#C8502A;color:#fff;
    font-size:.7rem;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;
    padding:5px 14px;border-radius:50px;margin-bottom:18px;">☕ Rekomendasi Berbasis Review Pengguna</div>
  <h1 style="font-family:'Fraunces',serif;font-size:clamp(2rem,4vw,3.2rem);font-weight:900;
    color:#1C1917;line-height:1.12;margin:0 0 14px;letter-spacing:-.8px;">
    Sistem Rekomendasi<br>Kafe di <span style="color:#C8502A;">Surabaya</span>
  </h1>
  <p style="color:#78716C;font-size:1rem;margin:0 auto 22px;max-width:540px;line-height:1.65;">
    Temukan kafe terbaik berdasarkan preferensimu.
  </p>
  <div style="display:inline-flex;align-items:flex-start;gap:10px;background:rgba(200,80,42,.07);
    border:1px solid rgba(200,80,42,.18);border-radius:12px;padding:12px 18px;max-width:620px;
    margin:0 auto 28px;text-align:left;">
    <span style="font-size:1.1rem;flex-shrink:0;margin-top:1px;">💡</span>
    <span style="font-size:.84rem;color:#1C1917;line-height:1.6;">
      Rekomendasi ini didasarkan pada <b style="color:#C8502A;">ulasan google dari pengunjung kafe di Surabaya tahun 2025</b>.
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# SEARCH BOX
# ════════════════════════════════════════════════════════════════
with st.container():
    st.markdown('<div style="background:linear-gradient(135deg,#FFF8F3,#FFF1E8 55%,#FFE8D6);padding:0 48px 12px;text-align:center;"><p style="font-size:.84rem;color:#78716C;margin-bottom:4px;font-weight:500;">Ketik nama kafe, kecamatan, atau kondisi yang kamu cari:</p></div>', unsafe_allow_html=True)
    col_search, col_btn = st.columns([5, 1])
    with col_search:
        search_input = st.selectbox(
            "Cari kafe",
            options=[""] + all_nama + all_kecamatan_search + all_condition,
            index=0, placeholder="Cari nama kafe, kecamatan, atau kondisi…",
            key="main_search_select", label_visibility="collapsed"
        )
    with col_btn:
        search_btn = st.button("🔍 Cari", key="main_search_btn", use_container_width=True)
    st.markdown('<div style="background:linear-gradient(135deg,#FFF8F3,#FFF1E8 55%,#FFE8D6);padding:4px 48px 52px;text-align:center;"><p style="font-size:.74rem;color:#bbb;">Contoh: &ldquo;Arung Senja&rdquo; &middot; &ldquo;Wonokromo&rdquo; &middot; &ldquo;makanan enak&rdquo;</p></div>', unsafe_allow_html=True)

def navigate_from_query(q: str):
    if not q or q.strip() == "": return
    q = q.strip()
    if q in nama_set:
        st.session_state["detail_kid"]  = nama_to_kafeid.get(q, "")
        st.session_state["detail_nama"] = q
        st.switch_page("pages/skemacari1.py"); return
    if q in kecamatan_set:
        st.session_state["pref_items"]  = []
        st.session_state["pref_bobot"]  = {}
        st.session_state["pref_lokasi"] = q
        st.switch_page("pages/skemacari4.py"); return
    if q in cond_set:
        st.session_state["detail_cond"] = q
        st.switch_page("pages/skemacari3.py"); return
    q_lower = q.lower()
    nm = next((n for n in all_nama if q_lower in n.lower()), None)
    if nm:
        st.session_state["detail_kid"]  = nama_to_kafeid.get(nm, "")
        st.session_state["detail_nama"] = nm
        st.switch_page("pages/skemacari1.py"); return
    kec = next((k for k in all_kecamatan_search if q_lower in k.lower()), None)
    if kec:
        st.session_state["pref_items"]  = []
        st.session_state["pref_bobot"]  = {}
        st.session_state["pref_lokasi"] = kec
        st.switch_page("pages/skemacari4.py"); return
    co = next((c for c in all_condition if q_lower in c.lower()), None)
    if co:
        st.session_state["detail_cond"] = co
        st.switch_page("pages/skemacari3.py"); return
    st.warning(f'❌ Tidak ditemukan: "{q}". Coba kata kunci lain.', icon="🔍")

if search_btn and search_input:
    navigate_from_query(search_input)
elif search_input and search_input != "":
    navigate_from_query(search_input)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# PREFERENSI
# ════════════════════════════════════════════════════════════════
st.markdown("""
<div class="pref-native-wrap">
  <div class="pref-section-hdr">
    <div class="pref-hdr-icon">✅</div>
    <div>
      <p class="pref-hdr-title">Mau cari kafe seperti apa?</p>
      <p class="pref-hdr-sub">Pilih sebanyak apapun aspek — bobot rata otomatis, bisa diubah manual.</p>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

with st.container():
    _, col_pref, _ = st.columns([1, 10, 1])
    with col_pref:
        st.markdown('<p class="lokasi-label">📍 Lokasi kamu saat ini (opsional)</p>', unsafe_allow_html=True)
        pref_lokasi_input = st.selectbox(
            "Lokasi", options=[""] + all_kecamatan, index=0,
            placeholder="Ketik nama kecamatan…",
            key="pref_lokasi_select", label_visibility="collapsed"
        )
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        selected_per_cat = {}
        for cat in unique_cats:
            icon_html = CAT_ICONS.get(cat, "&#9749;")
            conds     = cat_cond_map.get(cat, [])
            if not conds: continue
            st.markdown(f'<div class="cat-block-native"><div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;"><div class="cat-block-ico">{icon_html}</div><div class="cat-block-nm">{cat}</div></div></div>', unsafe_allow_html=True)
            chosen = st.multiselect(f"Aspek {cat}", options=conds, default=[],
                                    key=f"pref_cat_{cat}", label_visibility="collapsed",
                                    placeholder=f"Pilih aspek {cat}…")
            selected_per_cat[cat] = chosen

        all_selected = []
        for v in selected_per_cat.values():
            all_selected.extend(v)

        if all_selected:
            n_sel     = len(all_selected)
            default_w = round(1.0 / n_sel, 4)
            chips_preview = " ".join(
                f'<span style="display:inline-flex;align-items:center;gap:5px;background:#FFF0EB;color:#C8502A;border:1px solid rgba(200,80,42,.25);border-radius:50px;padding:4px 12px;font-size:.76rem;font-weight:600;margin:3px 2px;">{c}<span style="background:#C8502A;color:#fff;border-radius:50px;padding:1px 7px;font-size:.66rem;">{round(default_w*100)}%</span></span>'
                for c in all_selected
            )
            st.markdown(f'<div style="padding:12px 0 8px;line-height:2;"><span style="font-size:.84rem;font-weight:600;color:#78716C;">✏️ Kriteria:</span><br>{chips_preview}</div>', unsafe_allow_html=True)
            manual_bobots = {}
            bobot_ok      = True
            with st.expander("⚙️ Ubah bobot secara manual? (opsional)", expanded=False):
                for cond in all_selected:
                    manual_bobots[cond] = st.number_input(
                        cond, min_value=0.0, max_value=1.0,
                        value=default_w, step=0.01, format="%.2f",
                        key=f"bobot_{cond}_{n_sel}"
                    )
                total_bobot = sum(manual_bobots.values())
                bobot_ok    = abs(total_bobot - 1.0) < 0.005
                sc = "#1A7A3C" if bobot_ok else "#C8502A"
                sb = "#EDFAF2" if bobot_ok else "#FFF0EB"
                st.markdown(f'<div style="padding:8px 14px;border-radius:8px;background:{sb};color:{sc};font-size:.84rem;font-weight:700;">Total: {total_bobot:.2f} {"✓" if bobot_ok else "← harus = 1.00"}</div>', unsafe_allow_html=True)
        else:
            manual_bobots = {}
            bobot_ok      = True

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        col_btn_pref, _ = st.columns([2, 5])
        with col_btn_pref:
            btn_pref_disabled = (len(all_selected) == 0 and not pref_lokasi_input) or \
                                (len(all_selected) > 0 and bool(manual_bobots) and not bobot_ok)
            btn_pref = st.button("💾 Simpan Preferensi", key="btn_simpan_pref",
                                 disabled=btn_pref_disabled, use_container_width=True)

        if btn_pref:
            if not all_selected:
                st.session_state["show_lokasi_only_popup"] = True
                st.session_state["pending_lokasi"]         = pref_lokasi_input or ""
                st.rerun()
            else:
                if manual_bobots and bobot_ok:
                    bobot_final = {k: v for k, v in manual_bobots.items() if k in all_selected}
                else:
                    bobot_final = {c: round(1.0 / len(all_selected), 4) for c in all_selected}
                s = sum(bobot_final.values())
                if s > 0:
                    bobot_final = {k: v / s for k, v in bobot_final.items()}
                valid_kids, _ = find_kafe_for_prefs(all_selected, pref_lokasi_input)
                if len(valid_kids) == 0:
                    st.session_state["show_no_kafe_popup"]  = True
                    st.session_state["no_kafe_suggestions"] = suggest_remove_aspect(all_selected, pref_lokasi_input)
                    st.session_state["pending_lokasi"]      = pref_lokasi_input
                    st.rerun()
                else:
                    st.session_state.update({
                        "show_no_kafe_popup": False,
                        "show_lokasi_only_popup": False,
                        "pref_items": all_selected,
                        "pref_bobot": bobot_final,
                        "pref_lokasi": pref_lokasi_input or ""
                    })
                    st.switch_page("pages/skemacari4.py")

        if st.session_state.get("show_no_kafe_popup", False):
            suggestions = st.session_state.get("no_kafe_suggestions", [])
            lok_txt = f" di <b>{st.session_state.get('pending_lokasi','')}</b>" if st.session_state.get("pending_lokasi") else ""
            st.markdown(f'<div style="background:#FFF0EB;border:2px solid #C8502A;border-radius:16px;padding:20px 24px;margin-top:14px;"><div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;"><span style="font-size:1.3rem;">😕</span><span style="font-family:Fraunces,serif;font-size:1rem;font-weight:800;color:#C8502A;">Tidak ada kafe yang sesuai</span></div><p style="font-size:.84rem;color:#1C1917;margin:0 0 10px;">Tidak ditemukan kafe dengan semua aspek yang kamu pilih{lok_txt}.</p>', unsafe_allow_html=True)
            for cond, n_k in suggestions[:4]:
                st.markdown(f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;background:#fff;border:1px solid #E8DDD5;border-radius:8px;padding:7px 12px;"><span style="font-size:.79rem;flex:1;">Hapus <b>"{cond}"</b></span><span style="font-size:.74rem;color:#1A7A3C;font-weight:700;background:#EDFAF2;padding:2px 8px;border-radius:50px;">→ {n_k} kafe</span></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            _, col_tutup = st.columns([7, 2])
            with col_tutup:
                if st.button("✕ Tutup", key="btn_close_no_kafe"):
                    st.session_state["show_no_kafe_popup"] = False; st.rerun()

        if st.session_state.get("show_lokasi_only_popup", False):
            pending = st.session_state.get("pending_lokasi", "")
            lok_l   = f"lokasi <b>{pending}</b>" if pending else "tanpa aspek"
            st.markdown(f'<div style="background:#FFFBEB;border:2px solid #F59E0B;border-radius:16px;padding:20px 24px;margin-top:14px;"><p style="font-size:.84rem;color:#1C1917;margin:0 0 14px;">Lanjutkan hanya berdasarkan {lok_l}?</p></div>', unsafe_allow_html=True)
            col_lanjut, col_batal, _ = st.columns([2, 2, 3])
            with col_lanjut:
                if st.button("✅ Lanjutkan", key="btn_confirm_lokasi_only"):
                    st.session_state.update({"show_lokasi_only_popup": False,
                        "pref_items": [], "pref_bobot": {}, "pref_lokasi": pending})
                    st.switch_page("pages/skemacari4.py")
            with col_batal:
                if st.button("← Pilih Aspek Dulu", key="btn_cancel_lokasi_only"):
                    st.session_state["show_lokasi_only_popup"] = False; st.rerun()

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# BANDINGKAN KAFE
# ════════════════════════════════════════════════════════════════
st.markdown('<div id="compare-section"></div>', unsafe_allow_html=True)
st.markdown("""
<div class="cmp-native-wrap">
  <div class="cmp-section-hdr">
    <div style="font-size:1.8rem;flex-shrink:0;">⚖️</div>
    <div>
      <p style="font-family:'Fraunces',serif;font-size:1.45rem;font-weight:900;color:#1C1917;margin:0;">Bandingkan Beberapa Kafe</p>
      <p style="font-size:.84rem;color:#78716C;margin:0;">Pilih 2–5 kafe dari dropdown.</p>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)
with st.container():
    _, col_cmp, _ = st.columns([1, 10, 1])
    with col_cmp:
        compare_selected = st.multiselect("Pilih kafe", options=all_nama, default=[],
                                          key="compare_multiselect", label_visibility="collapsed",
                                          placeholder="Ketik nama kafe…", max_selections=5)
        col_cmp_btn, col_cmp_rst, _ = st.columns([2, 1, 4])
        with col_cmp_btn:
            btn_compare = st.button("⚖️ Bandingkan", key="btn_compare",
                                    disabled=len(compare_selected) < 1, use_container_width=True)
        with col_cmp_rst:
            if st.button("✕ Reset", key="btn_cmp_reset", use_container_width=True):
                st.session_state["compare_multiselect"] = []; st.rerun()
        if btn_compare and compare_selected:
            st.session_state["compare_names"] = list(compare_selected)
            st.switch_page("pages/skemabandingkan.py")

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# BEST KAFE — SLIDESHOW
# [F1] Semua kategori digabung dalam SATU components.html
# [F2] HTML di-cache via @st.cache_data
# ════════════════════════════════════════════════════════════════

CARD_W = 220
IMG_H  = 128
TOP5_H = 108
BODY_H = 118


def _build_one_card_html_1(row: pd.Series, rank: int, cat: str,
                             bg_sec: str, top5_lookup: dict,
                             jml_review_map: dict, reviewer_aktif_map: dict,
                             identifier: str, is_google: bool) -> str:
    rank_bg_map  = {1: "#D4A017", 2: "#8C8C8C", 3: "#A0522D"}
    rank_bg      = rank_bg_map.get(rank, "rgba(28,25,23,.65)")
    nama_display = str(row.get("nama_kafe", "—"))
    alamat       = str(row.get("alamat_kafe", "—"))
    jam          = str(row.get("jam_buka", "—"))
    kid          = str(row.get("kafe_id", ""))
    saw_score    = float(row.get("saw_score", 0))
    saw_pct      = f"{saw_score * 100:.1f}%"
    jml_rev      = jml_review_map.get(kid, 0)
    try:
        jml_r = f"{int(jml_rev):,}".replace(",", ".")
    except Exception:
        jml_r = str(jml_rev)
    rev_aktif_pct = reviewer_aktif_map.get(kid, 0.0)
    rev_aktif_str = f"{rev_aktif_pct:.1f}%"
    cover  = str(row.get("cover", ""))
    direct = gdrive_direct_url(cover)
    if direct:
        img_html = (
            f'<img src="{direct}" alt="{nama_display}" '
            f'style="width:100%;height:{IMG_H}px;object-fit:cover;display:block;" loading="lazy" '
            f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">'
            f'<div style="display:none;width:100%;height:{IMG_H}px;background:#f5ede5;'
            f'align-items:center;justify-content:center;font-size:2rem;color:#c8a898;'
            f'flex-direction:column;">&#9749;<small style="font-size:.55rem;text-transform:uppercase;">No Photo</small></div>'
        )
    else:
        img_html = (
            f'<div style="width:100%;height:{IMG_H}px;background:#f5ede5;display:flex;'
            f'align-items:center;justify-content:center;font-size:2rem;color:#c8a898;'
            f'flex-direction:column;">&#9749;<small style="font-size:.55rem;text-transform:uppercase;">No Photo</small></div>'
        )
    top5_list = top5_lookup.get(f"{kid}|{cat}", [])
    top5_html = ""
    if top5_list:
        _dot_colors = ["#C8502A","#B8730A","#1A6EB0","#1A7A3C","#7C3AED"]
        top5_html   = (f'<div style="border-top:1px solid #E8DDD5;padding:7px 11px 9px;background:#FAFAF8;'
                       f'height:{TOP5_H}px;box-sizing:border-box;overflow:hidden;">'
                       f'<div style="font-size:.58rem;color:#78716C;font-weight:600;text-transform:uppercase;letter-spacing:.7px;margin-bottom:5px;">&#128269; Top 5 Aspek Kafe Ini</div>')
        for ti, (cond_label, pct_val) in enumerate(top5_list):
            bar_w      = min(int(float(pct_val)), 100)
            dot_clr    = _dot_colors[ti % len(_dot_colors)]
            cond_short = str(cond_label)[:18] + ("…" if len(str(cond_label)) > 18 else "")
            top5_html += (f'<div style="display:flex;align-items:center;gap:5px;margin-bottom:3px;">'
                          f'<div style="width:13px;height:13px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.50rem;font-weight:800;color:#fff;flex-shrink:0;background:{dot_clr};">{ti+1}</div>'
                          f'<div style="font-size:.61rem;color:#1C1917;font-weight:500;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{cond_label}">{cond_short}</div>'
                          f'<div style="flex:1;height:3px;background:#f0e8e3;border-radius:2px;overflow:hidden;"><div style="height:3px;border-radius:2px;background:{dot_clr};width:{bar_w}%;"></div></div>'
                          f'<div style="font-size:.58rem;font-weight:700;min-width:26px;text-align:right;color:{dot_clr};">{float(pct_val):.0f}%</div></div>')
        top5_html += '</div>'

    cat_encoded = urllib.parse.quote(cat)
    nav_url = f"?nav_kid={kid}&nav_nama={urllib.parse.quote(nama_display)}&nav_cat={cat_encoded}&user={identifier}&is_google={is_google}"

    return f"""
<div style="width:{CARD_W}px;flex-shrink:0;scroll-snap-align:start;">
  <div style="background:#fff;border-radius:14px;border:1.5px solid #E8DDD5;
    overflow:hidden;box-shadow:0 2px 10px rgba(28,25,23,.07);
    transition:transform .2s,box-shadow .2s;"
    onmouseover="this.style.transform='translateY(-4px)';this.style.boxShadow='0 8px 24px rgba(28,25,23,.13)';"
    onmouseout="this.style.transform='';this.style.boxShadow='0 2px 10px rgba(28,25,23,.07)';">
    <div style="position:relative;">
      <div style="position:absolute;top:8px;left:8px;background:{rank_bg};color:#fff;
        font-size:.66rem;font-weight:700;width:26px;height:26px;border-radius:50%;
        display:flex;align-items:center;justify-content:center;z-index:2;
        box-shadow:0 2px 6px rgba(0,0,0,.25);">{rank}</div>
      <div style="width:100%;height:{IMG_H}px;overflow:hidden;background:#f5ede5;">{img_html}</div>
    </div>
    <div style="padding:9px 11px 10px;height:{BODY_H}px;box-sizing:border-box;overflow:hidden;">
      <div style="font-family:'Fraunces',serif;font-size:.80rem;font-weight:700;
        color:#1C1917;margin-bottom:2px;white-space:nowrap;overflow:hidden;
        text-overflow:ellipsis;" title="{nama_display}">{nama_display}</div>
      <div style="font-size:.62rem;color:#999;margin-bottom:3px;white-space:nowrap;
        overflow:hidden;text-overflow:ellipsis;" title="{alamat}">&#128205; {alamat}</div>
      <div style="font-size:.62rem;color:#C8502A;font-weight:600;margin-bottom:6px;">&#128336; {jam}</div>
      <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;">
        <span style="font-size:.62rem;color:#fff;background:#C8502A;padding:2px 8px;
          border-radius:50px;font-weight:700;">&#11088; {saw_pct}</span>
        <span style="font-size:.60rem;color:#555;background:#F7F3F0;padding:2px 6px;
          border-radius:50px;font-weight:500;">&#128101; {jml_r} review</span>
        <span style="font-size:.60rem;color:#1A7A3C;background:#EDFAF2;padding:2px 6px;
          border-radius:50px;font-weight:500;">&#9989; {rev_aktif_str} aktif</span>
      </div>
    </div>
    {top5_html}
    <a href="{nav_url}" target="_blank"
       style="display:block;text-align:center;padding:10px 8px;
       background:#C8502A;color:#fff;font-size:.73rem;font-weight:700;
       text-decoration:none;border-radius:0 0 12px 12px;">
       Lihat Detail →
    </a>
  </div>
</div>"""


# [F2] Cache HTML per kategori
@st.cache_data(show_spinner=False)
def _build_category_html_1(
    cat: str,
    ranked_json: str,
    top5_json: str,
    jml_review_json: str,
    reviewer_aktif_json: str,
    bg_sec: str,
    accentbg: str,
    accentfg: str,
    icon: str,
    identifier: str,
    is_google: bool,
    card_w: int, img_h: int, top5_h: int, body_h: int,
) -> str:
    import io
    ranked_df       = pd.read_json(io.StringIO(ranked_json), orient="records")
    top5_lookup     = json.loads(top5_json)
    jml_review_map  = json.loads(jml_review_json)
    reviewer_aktif  = json.loads(reviewer_aktif_json)

    if ranked_df.empty:
        return ""

    n_total      = len(ranked_df)
    uid          = cat.replace(" ", "_").replace("/", "_").lower()
    card_total_w = card_w + 16

    all_cards_html = "".join(
        _build_one_card_html_1(row, i + 1, cat, bg_sec, top5_lookup,
                               jml_review_map, reviewer_aktif, identifier, is_google)
        for i, (_, row) in enumerate(ranked_df.iterrows())
    )

    return f"""
<div class="slide-section-wrap" style="background:{bg_sec};padding:36px 48px 14px;" id="section-{uid}">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
    <div style="font-family:'Fraunces',serif;font-size:1.25rem;font-weight:700;color:#1C1917;display:flex;align-items:center;gap:10px;">
      {icon}&nbsp;Best&nbsp;<span style="padding:3px 12px;border-radius:50px;font-size:.66rem;font-weight:700;letter-spacing:.8px;text-transform:uppercase;background:{accentbg};color:{accentfg};">{cat.upper()}</span>
    </div>
    <div style="font-size:.75rem;color:#bbb;">{n_total} kafe &middot; geser untuk lihat semua</div>
  </div>
  <div style="font-size:.84rem;color:#78716C;margin-bottom:14px;">Diurutkan berdasarkan skor sentimen tertinggi ke terendah kategori aspek <b>{cat.lower()}</b></div>
  <div class="slide-track-outer">
    <button class="slide-btn slide-btn-left" onclick="slideTrack('{uid}',-1)">&#8249;</button>
    <div id="track_{uid}" class="slide-track">
      {all_cards_html}
    </div>
    <button class="slide-btn slide-btn-right" onclick="slideTrack('{uid}',1)">&#8250;</button>
  </div>
  <div id="counter_{uid}" class="slide-counter">1 / {n_total}</div>
</div>"""

# [F1][F2] Build satu HTML besar berisi SEMUA kategori, di-cache
@st.cache_data(show_spinner=False)
def build_all_slides_html_1(
    best_df_json: str,
    top5_json: str,
    jml_review_json: str,
    reviewer_aktif_json: str,
    cats_json: str,
    clrs_json: str,
    cat_icons_json: str,
    cat_bg_json: str,
    identifier: str,
    is_google: bool,
    card_w: int, img_h: int, top5_h: int, body_h: int,
) -> str:
    best_df        = pd.read_json(io.StringIO(best_df_json), orient="records")
    top5_lookup    = json.loads(top5_json)
    unique_cats    = json.loads(cats_json)
    clrs           = json.loads(clrs_json)
    cat_icons      = json.loads(cat_icons_json)
    cat_bg         = json.loads(cat_bg_json)

    if best_df.empty:
        return "", 0

    body_parts = []
    for idx_cat, cat in enumerate(unique_cats):
        cat_ranked = best_df[best_df["category_aspect_kafe"] == cat].reset_index(drop=True)
        if cat_ranked.empty:
            continue

        bg_sec    = cat_bg.get(cat, "#fff")
        icon      = cat_icons.get(cat, "&#9749;")
        accentbg, accentfg = clrs[idx_cat % len(clrs)]

        kids_in_cat = set(cat_ranked["kafe_id"].astype(str).tolist())
        top5_subset = {
            key: v
            for key, v in top5_lookup.items()
            if isinstance(key, str) and "|" in key
            and key.split("|", 1)[0] in kids_in_cat
            and key.split("|", 1)[1] == cat
        }

        section_html = _build_category_html_1(
            cat                 = cat,
            ranked_json         = cat_ranked.to_json(orient="records"),
            top5_json           = json.dumps(top5_subset),
            jml_review_json     = jml_review_json,
            reviewer_aktif_json = reviewer_aktif_json,
            bg_sec              = bg_sec,
            accentbg            = accentbg,
            accentfg            = accentfg,
            icon                = icon,
            identifier          = identifier,
            is_google           = is_google,
            card_w              = card_w,
            img_h               = img_h,
            top5_h              = top5_h,
            body_h              = body_h,
        )
        body_parts.append(section_html)

    all_body = '<hr style="border:none;border-top:1px solid #E8DDD5;margin:0;">'.join(body_parts)

    card_total_w = card_w + 16
    script = f"""
<script>
(function(){{
  var cardW = {card_total_w};
  var cursors = {{}};
  window.slideTrack = function(uid, d) {{
    var track = document.getElementById('track_' + uid);
    var cnt   = document.getElementById('counter_' + uid);
    if (!track) return;
    var total = track.children.length;
    if (!cursors[uid]) cursors[uid] = 0;
    cursors[uid] = Math.min(Math.max(cursors[uid] + d, 0), total - 1);
    track.scrollTo({{left: cursors[uid] * cardW, behavior: 'smooth'}});
    if (cnt) cnt.textContent = (cursors[uid] + 1) + ' / ' + total;
  }};
  document.addEventListener('scroll', function() {{
    document.querySelectorAll('[id^="track_"]').forEach(function(track) {{
      var uid = track.id.replace('track_', '');
      var cnt = document.getElementById('counter_' + uid);
      var cur = Math.min(Math.max(Math.round(track.scrollLeft / cardW), 0), track.children.length - 1);
      cursors[uid] = cur;
      if (cnt) cnt.textContent = (cur + 1) + ' / ' + track.children.length;
    }});
  }}, {{passive: true}});
}})();
</script>"""

    return all_body + script


_any_popup_active_1 = (
    st.session_state.get("show_no_kafe_popup", False) or
    st.session_state.get("show_lokasi_only_popup", False) or
    st.session_state.get("analisis_processing", False)
)

# ════════════════════════════════════════════════════════════════
# RENDER BEST KAFE
# [F1][F4] Satu iframe, cache HTML, guard session_state
# ════════════════════════════════════════════════════════════════
st.markdown(f"""
<div id="best-section" style="padding:48px 48px 24px;background:#fff;">
  <div class="section-header-hl blue">
    <div class="hl-icon">&#11088;</div>
    <div>
      <p class="hl-title">Best Kafe Masing-masing Aspek</p>
      <p class="hl-sub">Ranking berdasarkan kategori aspek harga, makanan, pelayanan, suasana.</p>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

if not best_df.empty and not _any_popup_active_1:
    _slides_key_1 = "_all_slides_html_loggedin"
    if _slides_key_1 not in st.session_state:
        MAX_KAFE_PER_CAT = 15
        _top5_serializable = {f"{k}|{c}": v for (k, c), v in _top5_lookup.items()}
        _best_df_trimmed = (
            best_df
            .groupby("category_aspect_kafe", group_keys=False)
            .apply(lambda g: g.head(MAX_KAFE_PER_CAT))
            .reset_index(drop=True)
        )

        _all_html_1 = build_all_slides_html_1(
            best_df_json        = _best_df_trimmed.to_json(orient="records"),
            top5_json           = json.dumps(_top5_serializable),
            jml_review_json     = json.dumps(_jml_review_map),
            reviewer_aktif_json = json.dumps(_reviewer_aktif_map),
            cats_json           = json.dumps(unique_cats),
            clrs_json           = json.dumps(_clrs),
            cat_icons_json      = json.dumps(CAT_ICONS),
            cat_bg_json         = json.dumps(CAT_BG),
            identifier          = _identifier,
            is_google           = _is_google,
            card_w              = CARD_W,
            img_h               = IMG_H,
            top5_h              = TOP5_H,
            body_h              = BODY_H,
        )
        st.session_state[_slides_key_1] = _all_html_1

    _all_html_1 = st.session_state[_slides_key_1]
    if _all_html_1:
        st.markdown(_all_html_1, unsafe_allow_html=True)

elif _any_popup_active_1:
    st.markdown('<div style="padding:24px 48px;color:#78716C;font-size:.88rem;">⏳ Memproses...</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# ANALISIS SENTIMEN
# ════════════════════════════════════════════════════════════════
MAX_REVIEW_BATCH = 20

def _hash_reviews(reviews: list) -> str:
    combined = "||".join(sorted(str(r).strip() for r in reviews))
    return hashlib.md5(combined.encode()).hexdigest()

def run_analysis_optimized(reviews: list, nama_kafe: str) -> dict:
    if not reviews:
        return {"raw_aspects": [], "df_converted": pd.DataFrame()}

    seen_texts     = set()
    unique_reviews = []
    for r in reviews:
        t = r.strip()
        if not t:
            continue
        if t not in seen_texts:
            seen_texts.add(t)
            unique_reviews.append(t)

    was_truncated = len(unique_reviews) > MAX_REVIEW_BATCH
    batch_reviews = unique_reviews[:MAX_REVIEW_BATCH]

    cache_key = f"absa_cache_{_hash_reviews(batch_reviews)}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    if not st.session_state.get("_absa_warmed", False):
        with st.spinner("⏳ Memuat model analisis untuk pertama kali (~30-60 detik)..."):
            ok = _prewarm_absa_models()
        if not ok:
            err = st.session_state.get("_absa_warm_error", "Model gagal di-load")
            raise RuntimeError(f"Model ABSA tidak berhasil dimuat: {err}")

    import torch
    device = torch.device('cpu')

    progress_bar = st.progress(0, text="🔄 Memulai analisis...")
    status_text  = st.empty()

    all_aspects = []
    n = len(batch_reviews)

    translated_reviews = []
    for i, rev in enumerate(batch_reviews):
        pct_now = int((i / n) * 35)
        progress_bar.progress(pct_now, text=f"🌐 Menerjemahkan review {i+1}/{n}...")
        try:
            en = _absa_engine.translate_to_english(rev)
            translated_reviews.append(en)
        except Exception:
            translated_reviews.append(rev)

    for i, (orig_rev, en_rev) in enumerate(zip(batch_reviews, translated_reviews)):
        pct_now = 35 + int((i / n) * 60)
        progress_bar.progress(pct_now, text=f"🔍 Menganalisis aspek review {i+1}/{n}...")
        status_text.markdown(
            f'<div style="font-size:.8rem;color:#78716C;margin-top:4px;">'
            f'Review: <i>"{orig_rev[:60]}{"…" if len(orig_rev)>60 else ""}"</i></div>',
            unsafe_allow_html=True
        )
        try:
            asp_list = _absa_engine.analyze_single_review(en_rev, device=device)
            for asp in asp_list:
                asp["_source_review"] = orig_rev
            all_aspects.extend(asp_list)
        except Exception as e:
            st.warning(f"Review {i+1} gagal dianalisis: {str(e)[:80]}")

    progress_bar.progress(100, text="✅ Analisis selesai!")
    status_text.empty()
    progress_bar.empty()

    # ✅ GANTI blok tersebut dengan:
    df_conv = _absa_engine.convert_aspects_to_kafe_format(all_aspects)
    
    if not df_conv.empty:
        if "review" not in df_conv.columns:
            # ✅ FIX: Assign review dari _source_review tanpa kondisi panjang
            df_conv["review"] = [a.get("_source_review", "") for a in all_aspects]
        
        # ✅ Pastikan kolom skor ada
        if "skor_sentimen" not in df_conv.columns and "sentimen" in df_conv.columns:
            df_conv["skor_sentimen"] = df_conv["sentimen"].apply(
                lambda x: 1.0 if str(x).lower() == "positive" else 0.0
            )
        # Alias skor untuk kompatibilitas hasilanalisis.py
        df_conv["skor"] = pd.to_numeric(df_conv.get("skor_sentimen", 0), errors="coerce").fillna(0)

    result = {
        "raw_aspects"     : all_aspects,
        "df_converted"    : df_conv,
        "original_reviews": reviews,
        "batch_reviews"   : batch_reviews,
        "was_truncated"   : was_truncated,
        "n_original"      : len(reviews),
        "n_analyzed"      : len(batch_reviews),
        "nama_kafe"       : nama_kafe,
        "jumlah_review"   : len(reviews),
    }

    st.session_state[cache_key] = result
    return result

# ════════════════════════════════════════════════════════════════
# RENDER BAGIAN ANALISIS
# ════════════════════════════════════════════════════════════════
@st.fragment
def _render_analisis_section():
    st.markdown('<div id="analisis-section"></div>', unsafe_allow_html=True)
    st.markdown("""
<div style="background:linear-gradient(135deg,#1C1917,#2d1a0e);padding:52px 48px 0;">
  <div style="max-width:680px;margin:0 auto;text-align:center;padding-bottom:4px;">
    <div style="display:inline-block;background:rgba(200,80,42,.25);color:#F9A07A;font-size:.66rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;padding:4px 12px;border-radius:50px;margin-bottom:12px;">📈 Untuk Pemilik Kafe</div>
    <div style="font-family:'Fraunces',serif;font-size:1.45rem;font-weight:700;color:#fff;margin-bottom:6px;">Analisis Review Kafemu</div>
    <p style="font-size:.84rem;color:rgba(255,255,255,.45);line-height:1.6;margin-bottom:20px;">Ingin analisis sentiment review kamu sendiri? analisis disini</p>
  </div>
</div>
<div style="background:linear-gradient(135deg,#1C1917,#2d1a0e);padding:4px 48px 52px;"></div>
""", unsafe_allow_html=True)

    if not _engine_available:
        st.markdown(f'<div style="background:#FFF0EB;border:2px solid #C8502A;border-radius:12px;padding:14px 20px;margin:12px 48px;"><b style="color:#C8502A;">⚠️ absa_engine tidak tersedia.</b><br><span style="font-size:.82rem;color:#78716C;">{_engine_import_error[:200]}</span></div>', unsafe_allow_html=True)

    with st.container():
        _, col_analisis, _ = st.columns([1, 8, 1])
        with col_analisis:
            st.markdown('<div style="padding:12px 0 4px;"><span style="font-size:.84rem;font-weight:700;color:#78716C;letter-spacing:.5px;">☕ NAMA KAFE</span></div>', unsafe_allow_html=True)
            analisis_nama = st.text_input(
                "Nama kafe", placeholder="Masukkan nama kafe",
                key="analisis_nama_kafe", label_visibility="collapsed"
            )
            st.markdown('<div style="padding:18px 0 4px;"><span style="font-size:.84rem;font-weight:700;color:#78716C;letter-spacing:.5px;">📝 SUMBER REVIEW</span></div>', unsafe_allow_html=True)
            tab_choice = st.radio("Sumber review", options=["✏️ Ketik / Tempel Review", "📄 Upload File Excel"],
                                  horizontal=True, key="analisis_tab_radio", label_visibility="collapsed")

            analisis_reviews = []
            if tab_choice == "✏️ Ketik / Tempel Review":
                analisis_review_text = st.text_area("Review",
                    placeholder="Tempel atau ketik review di sini.\nSatu review per baris.",
                    height=160, key="analisis_review_textarea", label_visibility="collapsed")
                if analisis_review_text:
                    analisis_reviews = [r.strip() for r in analisis_review_text.split("\n") if r.strip()]
            else:
                uploaded_file = st.file_uploader("Upload file Excel", type=["xlsx"],
                                                 key="analisis_excel_upload", label_visibility="collapsed")
                if uploaded_file is not None:
                    try:
                        df_uploaded = pd.read_excel(uploaded_file)
                        df_uploaded.columns = [c.strip().lower() for c in df_uploaded.columns]
                        if "review" not in df_uploaded.columns:
                            st.markdown('<div style="background:#FFF0EB;border:1.5px solid #C8502A;border-radius:10px;padding:10px 16px;"><span style="font-size:.84rem;font-weight:700;color:#C8502A;">⚠️ Kolom review tidak ditemukan.</span></div>', unsafe_allow_html=True)
                        else:
                            analisis_reviews = df_uploaded["review"].dropna().astype(str).str.strip().tolist()
                            analisis_reviews = [r for r in analisis_reviews if r]
                            st.markdown(f'<div style="background:#EDFAF2;border:1.5px solid #22C55E;border-radius:10px;padding:10px 16px;"><span style="font-size:.84rem;font-weight:700;color:#1A7A3C;">✅ {len(analisis_reviews)} review siap dari {uploaded_file.name}</span></div>', unsafe_allow_html=True)
                    except Exception as e_up:
                        st.markdown(f'<div style="background:#FFF0EB;border:1.5px solid #C8502A;border-radius:10px;padding:10px 16px;"><span style="font-size:.84rem;font-weight:700;color:#C8502A;">❌ Gagal: {str(e_up)[:80]}</span></div>', unsafe_allow_html=True)

            if analisis_reviews and len(analisis_reviews) > MAX_REVIEW_BATCH:
                st.markdown(
                    f'<div style="background:#FFFBEB;border:1.5px solid #F59E0B;border-radius:10px;'
                    f'padding:8px 14px;margin-top:6px;">'
                    f'<span style="font-size:.84rem;color:#B8730A;">⚡ <b>{len(analisis_reviews)} review</b> terdeteksi. '
                    f'Hanya <b>{MAX_REVIEW_BATCH} review pertama</b> yang dianalisis untuk menjaga performa.</span></div>',
                    unsafe_allow_html=True
                )

            if st.session_state.get("analisis_error"):
                st.markdown(f'<div style="background:#FFF0EB;border:2px solid #C8502A;border-radius:12px;padding:14px 18px;margin-top:8px;"><span style="font-size:.84rem;font-weight:700;color:#C8502A;">❌ Error:</span><br><span style="font-size:.84rem;color:#78716C;">{st.session_state["analisis_error"]}</span></div>', unsafe_allow_html=True)
                _, col_retry = st.columns([7, 2])
                with col_retry:
                    if st.button("🔄 Coba Lagi", key="btn_analisis_retry"):
                        st.session_state["analisis_error"] = ""
                        st.rerun(scope="fragment")

            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            btn_disabled = (not bool(analisis_nama.strip()) or not bool(analisis_reviews) or
                            st.session_state.get("analisis_processing", False) or not _engine_available)
            col_btn_an, col_hint_an = st.columns([2, 5])
            with col_btn_an:
                btn_label    = "⏳ Sedang Diproses..." if st.session_state.get("analisis_processing") else "📊 Analisis Sekarang"
                btn_analisis = st.button(btn_label, key="btn_analisis_main",
                                         disabled=btn_disabled, use_container_width=True)
            with col_hint_an:
                if not _engine_available:
                    st.markdown('<span style="font-size:.84rem;color:#C8502A;">← absa_engine tidak tersedia</span>', unsafe_allow_html=True)
                elif not analisis_nama.strip():
                    st.markdown('<span style="font-size:.84rem;color:#bbb;">← Isi nama kafe dulu</span>', unsafe_allow_html=True)
                elif not analisis_reviews:
                    st.markdown('<span style="font-size:.84rem;color:#bbb;">← Masukkan review dulu</span>', unsafe_allow_html=True)
                else:
                    n_uniq = min(len(set(r.strip() for r in analisis_reviews if r.strip())), MAX_REVIEW_BATCH)
                    st.markdown(f'<span style="font-size:.84rem;color:#78716C;">← {n_uniq} review unik akan dianalisis</span>', unsafe_allow_html=True)

            if analisis_reviews:
                st.session_state["_pending_reviews"] = analisis_reviews
            if analisis_nama.strip():
                st.session_state["_pending_nama"] = analisis_nama.strip()

            if btn_analisis and analisis_nama.strip() and analisis_reviews and _engine_available:
                st.session_state["analisis_processing"] = True
                st.session_state["analisis_error"]      = ""
                st.session_state["_nav_to_analisis"]    = True
                st.rerun(scope="fragment")

            if st.session_state.get("_nav_to_analisis", False) and st.session_state.get("analisis_processing", False):
                st.session_state.pop("_nav_to_analisis", None)
                try:
                    result = run_analysis_optimized(
                        st.session_state.get("_pending_reviews", []),
                        st.session_state.get("_pending_nama", "")
                    )
                    st.session_state["analisis_result"]     = result
                    st.session_state["analisis_processing"] = False
                    st.switch_page("pages/hasilanalisis.py")
                except Exception as e_proc:
                    st.session_state["analisis_processing"] = False
                    err_msg = str(e_proc)
                    if "No module named" in err_msg:
                        err_msg = "Modul analisis tidak ditemukan."
                    st.session_state["analisis_error"] = err_msg[:400]
                    st.rerun(scope="fragment")

_render_analisis_section()

# ════════════════════════════════════════════════════════════════
# FOOTER
# ════════════════════════════════════════════════════════════════
st.markdown('<div class="footer">&copy; 2025 &nbsp;<b>KafeSby</b>&nbsp;&middot; Rekomendasi Kafe Surabaya Berbasis Review Pengunjung</div>', unsafe_allow_html=True)
