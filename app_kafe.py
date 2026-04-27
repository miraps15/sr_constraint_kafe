# ============================================================
# SISTEM REKOMENDASI KAFE SURABAYA — Halaman Utama
# Versi Streamlit Cloud
#
# PERBAIKAN PERFORMA [PATCH-NOFLICKER-V2]:
#   [G1] Slideshow dirender via st.markdown (bukan components.html/iframe)
#        → eliminasi total flicker saat scroll/re-run
#   [G2] CSS slideshow diinjeksi sekali via st.markdown global
#   [G3] HTML slideshow di-cache via @st.cache_data
#   [G4] Guard session_state: HTML hanya dibangun sekali
#   [G5] Perbaikan bug tuple-key top5_lookup
#   [G6] Section login dibungkus dalam satu container HTML
#        → tidak ada flash warna gelap/terang
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import json

from utils_kafe import (
    load_data,
    compute_best_per_category_imdb,
    precompute_top5_conditions_imdb,
    compute_saw_scores,
    compute_overall_score,
    gdrive_direct_url, build_slideshow_html, COMMON_CSS,
)
from users_manager import (
    load_users, upsert_user, check_login,
    get_google_accounts, ensure_google_user,
)

# ── Query param navigation ────────────────────────────────────
import gc as _gc

_qp = st.query_params

# ✅ CRASH RECOVERY: Cukup clear query params berbahaya saja
# Jangan lakukan operasi berat di sini
if _qp.get("nav_kid", "") or _qp.get("nav_nama", ""):
    _has_session = bool(
        st.session_state.get("logged_in") or
        st.session_state.get("_user_interacted")
    )
    if _has_session:
        _kid  = _qp.get("nav_kid", "")
        _nama = _qp.get("nav_nama", "")
        _cat  = _qp.get("nav_cat", "")
        st.query_params.clear()
        st.session_state["detail_kid"]        = _kid
        st.session_state["detail_nama"]       = _nama
        st.session_state["detail_source"]     = "kasus_e"
        st.session_state["detail_cat_chosen"] = _cat
        st.session_state["_prev_page"]        = "app_kafe.py"
        st.switch_page("pages/skemacari1.py")
    else:
        # Session hilang (setelah crash) → buang query params, tampilkan home
        st.query_params.clear()

st.set_page_config(
    page_title="Rekomendasi Kafe Surabaya",
    page_icon="☕", layout="wide",
    initial_sidebar_state="collapsed",
)

import os
_IS_HEALTH_CHECK = os.environ.get("STREAMLIT_HEALTH_CHECK", "") == "true"

# ✅ ANTI-STUCK: Inject JS redirect cleaner di setiap load app_kafe.py
# Ini memastikan URL bersih dari query params berbahaya
st.markdown("""
<script>
(function() {
    // Bersihkan query params berbahaya dari URL tanpa reload
    var url = new URL(window.location.href);
    var dangerous = ['nav_kid', 'nav_nama', 'nav_cat', 'kid', 'nama', 
                     'source', 'cond', 'user', 'is_google'];
    var hadDangerous = false;
    dangerous.forEach(function(p) {
        if (url.searchParams.has(p)) {
            url.searchParams.delete(p);
            hadDangerous = true;
        }
    });
    if (hadDangerous) {
        window.history.replaceState({}, '', url.pathname);
    }
})();
</script>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# LOAD DATA
# ════════════════════════════════════════════════════════════════
# ── Load data ringan dulu ──────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=1800)
def get_df():
    try:
        df = load_data()
        df["skor_sentimen"] = pd.to_numeric(
            df["skor_sentimen"], errors="coerce"
        ).fillna(0)
        df["kafe_id"] = df["kafe_id"].astype(str)
        return df
    except Exception:
        return pd.DataFrame(columns=[
            "kafe_id","nama_kafe","alamat_kafe","kecamatan_kafe",
            "jam_buka","cover","skor_sentimen","category_aspect_kafe",
            "aspect_condition","sentimen","review_id",
        ])

df = get_df()

# ── Lookup tables — HANYA jika df tidak kosong ────────────────
if not df.empty:
    all_nama             = sorted(df["nama_kafe"].dropna().unique().tolist())
    all_kecamatan_search = sorted(df["kecamatan_kafe"].dropna().unique().tolist()) \
                           if "kecamatan_kafe" in df.columns else []
    all_condition        = sorted(df["aspect_condition"].dropna().unique().tolist())
    unique_cats          = sorted(df["category_aspect_kafe"].dropna().unique().tolist())
    all_kecamatan        = all_kecamatan_search
    cat_cond_map         = {
        cat: sorted(df[df["category_aspect_kafe"]==cat]["aspect_condition"]
                    .dropna().unique().tolist())
        for cat in unique_cats
    }
    nama_to_kafeid       = df.drop_duplicates("nama_kafe")\
                             .set_index("nama_kafe")["kafe_id"].to_dict()
    kecamatan_to_kafeid  = {}
    if "kecamatan_kafe" in df.columns:
        for kec in all_kecamatan_search:
            kecamatan_to_kafeid[kec] = df[
                df["kecamatan_kafe"] == kec
            ]["kafe_id"].unique().tolist()
    nama_set      = set(all_nama)
    kecamatan_set = set(all_kecamatan_search)
    cond_set      = set(all_condition)
else:
    all_nama = all_kecamatan_search = all_condition = []
    unique_cats = all_kecamatan = []
    cat_cond_map = nama_to_kafeid = kecamatan_to_kafeid = {}
    nama_set = kecamatan_set = cond_set = set()

# ── Precompute LAZY ────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=3600)
def get_best_per_category(_df_shape, _df_hash):
    try:
        return compute_best_per_category_imdb(df)
    except Exception:
        return pd.DataFrame()

@st.cache_data(show_spinner=False, ttl=3600)
def precompute_all_top5(_df_shape, _df_hash):
    try:
        return precompute_top5_conditions_imdb(df)
    except Exception:
        return {}

# Default kosong — akan diisi lazy di section Best Kafe
best_df      = pd.DataFrame()
_top5_lookup = {}

if "_cached_reviewer_pct" not in st.session_state:
    st.session_state["_cached_reviewer_pct"] = get_reviewer_aktif_pct_per_kafe(df)
_reviewer_aktif_pct = st.session_state["_cached_reviewer_pct"]

if "_cached_saw_cat" not in st.session_state:
    st.session_state["_cached_saw_cat"] = compute_saw_scores(df)

if "_cached_overall" not in st.session_state:
    st.session_state["_cached_overall"] = compute_overall_score(df)

_any_popup_active = (
    st.session_state.get("show_no_kafe_popup", False) or
    st.session_state.get("show_lokasi_only_popup", False) or
    st.session_state.get("show_google_popup", False) or
    st.session_state.get("show_daftar_popup", False)
)

# ════════════════════════════════════════════════════════════════
# PREFERENSI — helper functions
# ════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def get_kafe_per_condition(cond: str) -> set:
    sub = df[df["aspect_condition"] == cond]
    return set(sub["kafe_id"].unique().tolist())

def find_kafe_for_prefs(pref_items: list, lokasi: str) -> tuple:
    if not pref_items:
        if lokasi and "kecamatan_kafe" in df.columns:
            sub  = df[df["kecamatan_kafe"].str.lower() == lokasi.lower()]
            kids = set(sub["kafe_id"].unique().tolist())
        else:
            kids = set(df["kafe_id"].unique().tolist())
        return kids, {}
    per_cond = {cond: get_kafe_per_condition(cond) for cond in pref_items}
    valid    = None
    for kids in per_cond.values():
        valid = set(kids) if valid is None else valid & kids
    if valid is None:
        valid = set()
    if lokasi and "kecamatan_kafe" in df.columns:
        lok_kids = set(df[df["kecamatan_kafe"].str.lower() == lokasi.lower()]["kafe_id"].unique())
        valid    = valid & lok_kids
    return valid, per_cond

def suggest_remove_aspect(pref_items: list, lokasi: str) -> list:
    suggestions = []
    for cond in pref_items:
        remaining  = [c for c in pref_items if c != cond]
        valid_kids, _ = find_kafe_for_prefs(remaining, lokasi)
        if valid_kids:
            suggestions.append((cond, len(valid_kids)))
    return sorted(suggestions, key=lambda x: x[1], reverse=True)

# ════════════════════════════════════════════════════════════════
# LOOKUP TABLES
# ════════════════════════════════════════════════════════════════
if "_cond_cache_ready" not in st.session_state:
    _all_cond_cache = {c: get_kafe_per_condition(c) for c in all_condition}
    st.session_state["_cond_cache_ready"] = True

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
    badge_css += (f".{CAT_BADGE[cat]}{{background:{bg_c};color:{fg_c};}}"
                  f".{CAT_ICON_CLS[cat]}{{background:{bg_c};}}\n")

# ════════════════════════════════════════════════════════════════
# CSS
# [G2] Tambah CSS slideshow langsung di sini (bukan di iframe)
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
div[data-testid="stSelectbox"] > div > div {{border-radius:60px!important;border:2px solid #E8DDD5!important;box-shadow:0 6px 28px rgba(200,80,42,.11)!important;font-size:.95rem!important;background:#fff!important;}}
div[data-testid="stSelectbox"] > div > div:focus-within {{border-color:#C8502A!important;box-shadow:0 6px 28px rgba(200,80,42,.22)!important;}}
div[data-testid="stSelectbox"] label {{display:none!important;}}
div[data-testid="stButton"] button {{border-radius:50px!important;background:#C8502A!important;color:white!important;border:none!important;font-weight:700!important;font-size:.9rem!important;padding:10px 28px!important;min-height:46px!important;}}
div[data-testid="stButton"] button:hover {{background:#A33E20!important;}}
div[data-testid="stMultiSelect"] > label {{display:none!important;}}
div[data-testid="stMultiSelect"] > div {{border-radius:12px!important;border:1.5px solid #E8DDD5!important;background:#fff!important;font-size:.88rem!important;}}
div[data-testid="stMultiSelect"] > div:focus-within {{border-color:#C8502A!important;box-shadow:0 0 0 2px rgba(200,80,42,.18)!important;}}
div[data-testid="stNumberInput"] > label {{font-size:.78rem!important;color:#78716C!important;font-weight:600!important;}}
div[data-testid="stNumberInput"] > div > input {{border-radius:8px!important;border:1.5px solid #E8DDD5!important;font-size:.85rem!important;}}
div[data-testid="stExpander"] {{border:1.5px solid #E8DDD5!important;border-radius:12px!important;background:#fff!important;}}
div[data-testid="stExpander"] summary {{font-size:.84rem!important;font-weight:600!important;color:#C8502A!important;}}
.pref-native-wrap {{background:#fff;padding:32px 48px 40px;}}
.pref-section-hdr {{display:flex;align-items:center;gap:16px;padding:18px 28px;border-radius:14px;margin-bottom:28px;background:linear-gradient(90deg,#EDFAF2,#F4FDF7);border-left:4px solid #22C55E;}}
.pref-hdr-icon {{font-size:1.8rem;flex-shrink:0;}}
.pref-hdr-title {{font-family:'Fraunces',serif;font-size:1.45rem;font-weight:900;color:#1C1917;margin:0;}}
.pref-hdr-sub {{font-size:.84rem;color:#78716C;margin:0;line-height:1.5;}}
.cat-block-native {{background:#FAFAF8;border:1.5px solid #E8DDD5;border-radius:14px;padding:16px 20px 14px;margin-bottom:12px;}}
.cat-block-ico {{width:30px;height:30px;border-radius:8px;background:#FFF0EB;display:flex;align-items:center;justify-content:center;font-size:.9rem;flex-shrink:0;}}
.cat-block-nm {{font-family:'Fraunces',serif;font-size:.92rem;font-weight:700;color:#1C1917;text-transform:capitalize;}}
.cmp-native-wrap {{background:#FAFAF8;padding:32px 48px 40px;}}
.cmp-section-hdr {{display:flex;align-items:center;gap:16px;padding:18px 28px;border-radius:14px;margin-bottom:28px;background:linear-gradient(90deg,#FFFBEB,#FFFDF5);border-left:4px solid #F59E0B;}}
#login-section-light [data-testid="stTextInput"] input {{background:#fff!important;border:1.5px solid #E8DDD5!important;border-radius:10px!important;color:#1C1917!important;font-size:.92rem!important;padding:12px 16px!important;}}
#login-section-light [data-testid="stTextInput"] input:focus {{border-color:#C8502A!important;box-shadow:0 0 0 3px rgba(200,80,42,.15)!important;}}
#login-section-light [data-testid="stButton"] button {{background:#C8502A!important;color:#fff!important;border-radius:50px!important;font-weight:700!important;font-size:.92rem!important;width:100%!important;min-height:50px!important;border:none!important;}}
#login-section-light .google-btn button {{background:#fff!important;color:#1C1917!important;border:1.5px solid #E8DDD5!important;font-weight:600!important;}}
#login-section-light .daftar-btn button {{background:transparent!important;color:#C8502A!important;border:2px solid #C8502A!important;font-weight:700!important;}}
#login-section-light .error-msg {{background:#FFF0EB!important;border:1px solid #C8502A!important;border-radius:10px!important;padding:10px 14px!important;font-size:.82rem!important;color:#C8502A!important;margin:8px 0!important;text-align:center!important;font-weight:500!important;}}
.lokasi-label {{font-size:.84rem!important;font-weight:600!important;color:#78716C!important;margin-bottom:4px!important;}}
/* [G2] CSS untuk slideshow inline (non-iframe) */
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
    ("show_google_popup", False), ("show_daftar_popup", False),
    ("login_error", ""), ("daftar_error", ""),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

if st.session_state.get("_nav_to_detail"):
    _kid  = st.session_state.pop("_nav_to_detail")
    _nama = st.session_state.pop("_nav_to_detail_nama", "")
    st.session_state["detail_kid"]  = _kid
    st.session_state["detail_nama"] = _nama
    st.switch_page("pages/skemacari1.py")

# ════════════════════════════════════════════════════════════════
# LOGIN SECTION — definisi fragment dipindah ke sini agar tidak error
# ════════════════════════════════════════════════════════════════
@st.fragment
def _render_login_section():
    st.markdown('<div id="login-anchor"></div>', unsafe_allow_html=True)
    st.markdown("""
<div style="background:linear-gradient(160deg,#2d1a0e,#1C1917);padding:56px 48px 48px;text-align:center;">
  <div style="max-width:440px;margin:0 auto;">
    <div style="font-size:2.6rem;margin-bottom:12px;">&#9749;</div>
    <div style="font-family:'Fraunces',serif;font-size:2rem;font-weight:900;color:#fff;margin-bottom:8px;">Masuk Dulu, Yuk!</div>
    <p style="font-size:.88rem;color:rgba(255,255,255,.65);margin-bottom:0;line-height:1.7;">Simpan kafe favorit dan coba fitur analisis sentimen.</p>
  </div>
</div>
""", unsafe_allow_html=True)

    st.markdown('<div id="login-section-light">', unsafe_allow_html=True)
    _, col_login, _ = st.columns([1, 2, 1])
    with col_login:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        with st.form("login_form", clear_on_submit=False):
            st.markdown('<p style="color:#1C1917;font-size:.78rem;font-weight:600;letter-spacing:.4px;margin-bottom:2px;">USERNAME</p>', unsafe_allow_html=True)
            login_username = st.text_input("Username", placeholder="Masukkan username kamu", label_visibility="collapsed")
            st.markdown('<p style="color:#1C1917;font-size:.78rem;font-weight:600;letter-spacing:.4px;margin-bottom:2px;margin-top:10px;">PASSWORD</p>', unsafe_allow_html=True)
            login_password = st.text_input("Password", placeholder="Masukkan password kamu", type="password", label_visibility="collapsed")
            if st.session_state.get("login_error", ""):
                st.markdown(f'<div class="error-msg">⚠️ {st.session_state["login_error"]}</div>', unsafe_allow_html=True)
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            btn_masuk = st.form_submit_button("Masuk Sekarang →", use_container_width=True)

        st.markdown('<div style="display:flex;align-items:center;gap:12px;margin:14px 0;"><div style="flex:1;height:1px;background:#E8DDD5;"></div><span style="color:#999;font-size:.74rem;">atau</span><div style="flex:1;height:1px;background:#E8DDD5;"></div></div>', unsafe_allow_html=True)
        st.markdown('<div class="google-btn">', unsafe_allow_html=True)
        btn_google = st.button("🔑 Lanjut dengan Google", key="btn_google_login", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div style="text-align:center;padding:14px 0 4px;"><span style="font-size:.80rem;color:#999;">Belum punya akun?</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="daftar-btn">', unsafe_allow_html=True)
        btn_daftar_link = st.button("📝 Daftar Gratis", key="btn_daftar_link", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    if btn_masuk:
        uname = login_username.strip()
        pwd   = login_password.strip()
        if not uname or not pwd:
            st.session_state["login_error"] = "Username dan password tidak boleh kosong."
            st.rerun(scope="fragment")
        elif check_login(uname, pwd):
            st.session_state.update({"login_error": "", "logged_in": True,
                                      "login_username": uname, "login_google": ""})
            st.switch_page("pages/app_kafe1.py")
        else:
            st.session_state["login_error"] = "Username atau password salah."
            st.rerun(scope="fragment")

    if btn_google:
        st.session_state["show_google_popup"] = True
        st.rerun(scope="fragment")
    if btn_daftar_link:
        st.session_state["show_daftar_popup"] = True
        st.rerun(scope="fragment")

    # Popup Google
    if st.session_state.get("show_google_popup", False):
        google_accounts = get_google_accounts()
        _, col_gpop, _ = st.columns([1, 4, 1])
        with col_gpop:
            st.markdown('<div style="background:#FFF8F3;border:2px solid #E8DDD5;border-radius:16px;padding:20px 24px;margin:16px 0;"><div style="font-family:Fraunces,serif;font-size:1.1rem;font-weight:800;color:#1C1917;margin-bottom:12px;">🔑 Pilih Akun Google</div>', unsafe_allow_html=True)
            if not google_accounts:
                st.markdown('<div style="background:#FFFBEB;border:1px solid #F59E0B;border-radius:10px;padding:10px 14px;font-size:.82rem;color:#B8730A;margin-bottom:12px;">ℹ️ Belum ada akun Google yang terdaftar. Masukkan email Google kamu untuk melanjutkan.</div>', unsafe_allow_html=True)
                with st.form("google_manual_form", clear_on_submit=True):
                    g_email_input = st.text_input("Email Google", placeholder="contoh@gmail.com", key="google_email_manual_input")
                    col_ok, col_batal = st.columns([3, 2])
                    with col_ok:
                        btn_google_manual = st.form_submit_button("✅ Lanjutkan", use_container_width=True)
                    with col_batal:
                        btn_google_cancel = st.form_submit_button("✕ Batal", use_container_width=True)
                if btn_google_manual and g_email_input.strip():
                    g_acc     = g_email_input.strip()
                    disp_name = ensure_google_user(g_acc)
                    st.session_state.update({"show_google_popup": False, "logged_in": True,
                                              "login_username": disp_name, "login_google": g_acc})
                    st.switch_page("pages/app_kafe1.py")
                elif btn_google_cancel:
                    st.session_state["show_google_popup"] = False
                    st.rerun(scope="fragment")
            else:
                for g_acc in google_accounts:
                    c1, c2 = st.columns([5, 2])
                    with c1:
                        st.markdown(f'<div style="padding:10px 14px;background:#fff;border:1.5px solid #E8DDD5;border-radius:10px;font-size:.85rem;color:#1C1917;">📧 {g_acc}</div>', unsafe_allow_html=True)
                    with c2:
                        if st.button("Pilih", key=f"btn_gpick_{g_acc}", use_container_width=True):
                            disp_name = ensure_google_user(g_acc)
                            st.session_state.update({"show_google_popup": False, "logged_in": True,
                                                      "login_username": disp_name, "login_google": g_acc})
                            st.switch_page("pages/app_kafe1.py")
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                with st.expander("➕ Gunakan akun Google lain", expanded=False):
                    with st.form("google_new_form", clear_on_submit=True):
                        g_new_input    = st.text_input("Email Google baru", placeholder="contoh@gmail.com", key="google_new_email_input")
                        btn_add_google = st.form_submit_button("✅ Lanjutkan", use_container_width=True)
                    if btn_add_google and g_new_input.strip():
                        g_acc     = g_new_input.strip()
                        disp_name = ensure_google_user(g_acc)
                        st.session_state.update({"show_google_popup": False, "logged_in": True,
                                                  "login_username": disp_name, "login_google": g_acc})
                        st.switch_page("pages/app_kafe1.py")
                if st.button("✕ Batal", key="btn_close_google_popup", use_container_width=True):
                    st.session_state["show_google_popup"] = False
                    st.rerun(scope="fragment")
            st.markdown('</div>', unsafe_allow_html=True)

    # Popup Daftar
    if st.session_state.get("show_daftar_popup", False):
        _, col_dpop, _ = st.columns([1, 4, 1])
        with col_dpop:
            st.markdown('<div style="background:#fff;border:2px solid #C8502A;border-radius:16px;padding:24px 28px;margin:16px 0;"><div style="font-family:Fraunces,serif;font-size:1.1rem;font-weight:800;color:#1C1917;margin-bottom:12px;">📝 Daftar Akun Baru</div>', unsafe_allow_html=True)
            with st.form("daftar_form", clear_on_submit=False):
                d_email = st.text_input("Email", placeholder="Email aktif kamu", key="daftar_email_input")
                d_uname = st.text_input("Username", placeholder="Pilih username unik", key="daftar_username_input")
                d_pwd   = st.text_input("Password", placeholder="Buat password kuat", type="password", key="daftar_password_input")
                if st.session_state.get("daftar_error", ""):
                    st.markdown(f'<div style="background:#FFF0EB;border:1px solid #C8502A;border-radius:8px;padding:8px 14px;font-size:.82rem;color:#C8502A;">⚠️ {st.session_state["daftar_error"]}</div>', unsafe_allow_html=True)
                c_daftar, c_tutup = st.columns([3, 2])
                with c_daftar:
                    btn_daftar_submit = st.form_submit_button("✅ Daftar Sekarang", use_container_width=True)
                with c_tutup:
                    btn_daftar_tutup = st.form_submit_button("✕ Tutup", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            if btn_daftar_tutup:
                st.session_state.update({"show_daftar_popup": False, "daftar_error": ""})
                st.rerun(scope="fragment")
            if btn_daftar_submit:
                if not d_email.strip() or not d_uname.strip() or not d_pwd.strip():
                    st.session_state["daftar_error"] = "Semua field harus diisi."
                    st.rerun(scope="fragment")
                else:
                    ok, msg = upsert_user(email=d_email.strip(), username=d_uname.strip(), password=d_pwd.strip())
                    if ok:
                        st.session_state.update({"daftar_error": "", "show_daftar_popup": False,
                                                 "logged_in": True, "login_username": d_uname.strip(),
                                                 "login_google": ""})
                        st.switch_page("pages/app_kafe1.py")
                    else:
                        st.session_state["daftar_error"] = msg
                        st.rerun(scope="fragment")
                        
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
    <a class="nav-link" href="#login-anchor">&#128274; Masuk</a>
  </nav>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# HERO
# ════════════════════════════════════════════════════════════════
st.markdown("""
<div style="text-align:center;background:linear-gradient(135deg,#FFF8F3,#FFF1E8 55%,#FFE8D6);
  padding:56px 48px 28px;position:relative;overflow:hidden;">
  <div style="position:absolute;font-size:260px;opacity:.03;top:-40px;right:-10px;
    transform:rotate(12deg);pointer-events:none;">☕</div>
  <div style="display:inline-flex;align-items:center;gap:6px;background:#C8502A;color:#fff;
    font-size:.7rem;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;
    padding:5px 14px;border-radius:50px;margin-bottom:18px;">
    ☕ Rekomendasi Berbasis Review Pengguna
  </div>
  <h1 style="font-family:'Fraunces',serif;font-size:clamp(2rem,4vw,3.2rem);font-weight:900;
    color:#1C1917;line-height:1.12;margin:0 0 14px;letter-spacing:-.8px;">
    Sistem Rekomendasi<br>Kafe di <span style="color:#C8502A;">Surabaya</span>
  </h1>
  <p style="color:#78716C;font-size:1rem;margin:0 auto 22px;max-width:540px;line-height:1.65;">
    Temukan kafe terbaik berdasarkan preferensimu — dari pelayanan, makanan, suasana, hingga harga yang pas.
  </p>
  <div style="display:inline-flex;align-items:flex-start;gap:10px;background:rgba(200,80,42,.07);
    border:1px solid rgba(200,80,42,.18);border-radius:12px;padding:12px 18px;max-width:620px;
    margin:0 auto 28px;text-align:left;">
    <span style="font-size:1.1rem;flex-shrink:0;margin-top:1px;">💡</span>
    <span style="font-size:.84rem;color:#1C1917;line-height:1.6;">
      Rekomendasi ini didasarkan pada <b style="color:#C8502A;">ulasan Google dari pengunjung kafe di Surabaya tahun 2025</b>.
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# SEARCH BOX
# ════════════════════════════════════════════════════════════════
with st.container():
    st.markdown("""
    <div style="background:linear-gradient(135deg,#FFF8F3,#FFF1E8 55%,#FFE8D6);
      padding:0 48px 12px;text-align:center;">
      <p style="font-size:.84rem;color:#78716C;margin-bottom:4px;font-weight:500;">
        Ketik nama kafe, kecamatan, atau kondisi yang kamu cari:
      </p>
    </div>
    """, unsafe_allow_html=True)
    col_search, col_btn = st.columns([5, 1])
    with col_search:
        search_input = st.selectbox(
            "Cari kafe",
            options=[""] + all_nama + all_kecamatan_search + all_condition,
            index=0, placeholder="Cari nama kafe, kecamatan, atau suasana…",
            key="main_search_select", label_visibility="collapsed",
        )
    with col_btn:
        search_btn = st.button("🔍 Cari", key="main_search_btn", use_container_width=True)
    st.markdown("""
    <div style="background:linear-gradient(135deg,#FFF8F3,#FFF1E8 55%,#FFE8D6);
      padding:4px 48px 52px;text-align:center;">
      <p style="font-size:.74rem;color:#bbb;margin-top:2px;">
        Contoh: &ldquo;Arung Senja&rdquo; &middot; &ldquo;Wonokromo&rdquo; &middot; &ldquo;makanan enak&rdquo;
      </p>
    </div>
    """, unsafe_allow_html=True)

def navigate_from_query(q: str):
    if not q or q.strip() == "":
        return
    st.session_state["_user_interacted"] = True  # ✅ Tambahkan baris ini saja
    q = q.strip()
    if q in nama_set:
        st.session_state.update({"detail_kid": nama_to_kafeid.get(q, ""), "detail_nama": q})
        st.switch_page("pages/skemacari1.py"); return
    if q in kecamatan_set:
        st.session_state.update({"detail_cond": q, "pref_items": [],
                                  "pref_bobot": {}, "pref_lokasi": q})
        st.switch_page("pages/skemacari4.py"); return
    if q in cond_set:
        st.session_state["detail_cond"] = q
        st.switch_page("pages/skemacari3.py"); return
    q_lower = q.lower()
    nm = next((n for n in all_nama if q_lower in n.lower()), None)
    if nm:
        st.session_state.update({"detail_kid": nama_to_kafeid.get(nm, ""), "detail_nama": nm})
        st.switch_page("pages/skemacari1.py"); return
    kec = next((k for k in all_kecamatan_search if q_lower in k.lower()), None)
    if kec:
        st.session_state.update({"pref_items": [], "pref_bobot": {}, "pref_lokasi": kec})
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
            placeholder="Ketik nama kecamatan…", key="pref_lokasi_select",
            label_visibility="collapsed",
        )
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        selected_per_cat = {}
        for cat in unique_cats:
            icon_html = CAT_ICONS.get(cat, "&#9749;")
            conds     = cat_cond_map.get(cat, [])
            if not conds:
                continue
            st.markdown(f"""
            <div class="cat-block-native">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
                <div class="cat-block-ico">{icon_html}</div>
                <div class="cat-block-nm">{cat}</div>
              </div>
            </div>""", unsafe_allow_html=True)
            chosen = st.multiselect(
                f"Aspek {cat}", options=conds, default=[],
                key=f"pref_cat_{cat}", label_visibility="collapsed",
                placeholder=f"Pilih aspek {cat}…",
            )
            st.session_state[f"_sel_{cat}"] = chosen
            selected_per_cat[cat] = chosen

        all_selected = []
        for v in selected_per_cat.values():
            all_selected.extend(v)

        if all_selected:
            n_sel     = len(all_selected)
            default_w = round(1.0 / n_sel, 4)
            chips_preview = " ".join(
                f'<span style="display:inline-flex;align-items:center;gap:5px;background:#FFF0EB;color:#C8502A;'
                f'border:1px solid rgba(200,80,42,.25);border-radius:50px;padding:4px 12px;font-size:.76rem;'
                f'font-weight:600;margin:3px 2px;">{c}'
                f'<span style="background:#C8502A;color:#fff;border-radius:50px;padding:1px 7px;font-size:.66rem;">'
                f'{round(default_w*100)}%</span></span>' for c in all_selected
            )
            st.markdown(f'<div style="padding:12px 0 8px;line-height:2;"><span style="font-size:.84rem;font-weight:600;color:#78716C;">✏️ Kriteria:</span><br>{chips_preview}</div>', unsafe_allow_html=True)

            manual_bobots = {}
            bobot_ok      = True
            with st.expander("⚙️ Ubah bobot secara manual? (opsional)", expanded=False):
                for cond in all_selected:
                    manual_bobots[cond] = st.number_input(
                        cond, min_value=0.0, max_value=1.0, value=default_w,
                        step=0.01, format="%.2f", key=f"bobot_{cond}_{n_sel}",
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
            btn_pref_disabled = (
                (len(all_selected) == 0 and not pref_lokasi_input) or
                (len(all_selected) > 0 and bool(manual_bobots) and not bobot_ok)
            )
            btn_pref = st.button("💾 Simpan Preferensi", key="btn_simpan_pref",
                                 disabled=btn_pref_disabled, use_container_width=True)

        if btn_pref:
            if not all_selected:
                st.session_state.update({"show_lokasi_only_popup": True,
                                          "pending_lokasi": pref_lokasi_input or ""})
                st.rerun()
            else:
                bobot_final = ({k: v for k, v in manual_bobots.items() if k in all_selected}
                               if (manual_bobots and bobot_ok)
                               else {c: round(1.0/len(all_selected), 4) for c in all_selected})
                s = sum(bobot_final.values())
                if s > 0:
                    bobot_final = {k: v/s for k, v in bobot_final.items()}
                valid_kids, _ = find_kafe_for_prefs(all_selected, pref_lokasi_input)
                if len(valid_kids) == 0:
                    st.session_state.update({
                        "show_no_kafe_popup":  True,
                        "no_kafe_suggestions": suggest_remove_aspect(all_selected, pref_lokasi_input),
                        "pending_lokasi":      pref_lokasi_input,
                    })
                    st.rerun()
                else:
                    st.session_state.update({
                        "show_no_kafe_popup": False, "show_lokasi_only_popup": False,
                        "pref_items": all_selected, "pref_bobot": bobot_final,
                        "pref_lokasi": pref_lokasi_input or "",
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
                    st.session_state["show_no_kafe_popup"] = False
                    st.rerun()

        if st.session_state.get("show_lokasi_only_popup", False):
            pending = st.session_state.get("pending_lokasi", "")
            lok_l   = f"lokasi <b>{pending}</b>" if pending else "tanpa aspek"
            st.markdown(f'<div style="background:#FFFBEB;border:2px solid #F59E0B;border-radius:16px;padding:20px 24px;margin-top:14px;"><p style="font-size:.84rem;color:#1C1917;margin:0 0 14px;">Lanjutkan hanya berdasarkan {lok_l}?</p></div>', unsafe_allow_html=True)
            col_lanjut, col_batal, _ = st.columns([2, 2, 3])
            with col_lanjut:
                if st.button("✅ Lanjutkan", key="btn_confirm_lokasi_only"):
                    st.session_state.update({"show_lokasi_only_popup": False,
                                              "pref_items": [], "pref_bobot": {},
                                              "pref_lokasi": pending})
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
        compare_selected = st.multiselect(
            "Pilih kafe", options=all_nama, default=[],
            key="compare_multiselect", label_visibility="collapsed",
            placeholder="Ketik nama kafe…", max_selections=5,
        )
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
# [G1] Render via st.markdown (BUKAN components.html/iframe)
#      → tidak ada iframe = tidak ada flicker sama sekali
# [G3] HTML di-cache via @st.cache_data
# [G4] Guard session_state
# [G5] Perbaikan bug tuple-key
# ════════════════════════════════════════════════════════════════

CARD_W = 220; IMG_H = 128; TOP5_H = 108; BODY_H = 118


def _build_one_card_html(row, rank, cat, bg_sec, top5_lookup, reviewer_aktif_pct):
    rank_bg_map = {1: "#D4A017", 2: "#8C8C8C", 3: "#A0522D"}
    rank_bg     = rank_bg_map.get(rank, "rgba(28,25,23,.65)")
    nama_display = str(row.get("nama_kafe", "—"))
    alamat       = str(row.get("alamat_kafe", "—"))
    jam          = str(row.get("jam_buka", "—"))
    kid          = str(row.get("kafe_id", ""))
    saw_pct      = f"{float(row.get('saw_score', 0)) * 100:.1f}%"
    try:
        jml_r = f"{int(float(row.get('jumlah_review', 0))):,}".replace(",", ".")
    except Exception:
        jml_r = str(row.get("jumlah_review", 0))
    try:
        aktif_pct_val = float(reviewer_aktif_pct.get(kid, 0.0))
    except Exception:
        aktif_pct_val = 0.0
    aktif_str  = f"{aktif_pct_val:.1f}%"
    direct     = gdrive_direct_url(str(row.get("cover", "")))
    if direct:
        img_html = (f'<img src="{direct}" alt="{nama_display}" style="width:100%;height:{IMG_H}px;object-fit:cover;display:block;" loading="lazy" '
                    f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">'
                    f'<div style="display:none;width:100%;height:{IMG_H}px;background:#f5ede5;align-items:center;justify-content:center;font-size:2rem;color:#c8a898;flex-direction:column;">&#9749;<small style="font-size:.55rem;text-transform:uppercase;">No Photo</small></div>')
    else:
        img_html = (f'<div style="width:100%;height:{IMG_H}px;background:#f5ede5;display:flex;align-items:center;justify-content:center;font-size:2rem;color:#c8a898;flex-direction:column;">&#9749;<small style="font-size:.55rem;text-transform:uppercase;">No Photo</small></div>')

    # [G5] key adalah string "kid|cat", bukan tuple
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

    cat_encoded = cat.replace(" ", "+")
    nav_url     = f"?nav_kid={kid}&nav_nama={nama_display.replace(' ', '+')}&nav_cat={cat_encoded}"
    return f"""
<div class="slide-card" style="width:{CARD_W}px;">
  <div class="slide-card-inner">
    <div style="position:relative;">
      <div style="position:absolute;top:8px;left:8px;background:{rank_bg};color:#fff;font-size:.66rem;font-weight:700;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;z-index:2;box-shadow:0 2px 6px rgba(0,0,0,.25);">{rank}</div>
      <div style="width:100%;height:{IMG_H}px;overflow:hidden;background:#f5ede5;">{img_html}</div>
    </div>
    <div style="padding:9px 11px 10px;height:{BODY_H}px;box-sizing:border-box;overflow:hidden;">
      <div style="font-family:'Fraunces',serif;font-size:.80rem;font-weight:700;color:#1C1917;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{nama_display}">{nama_display}</div>
      <div style="font-size:.62rem;color:#999;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{alamat}">&#128205; {alamat}</div>
      <div style="font-size:.62rem;color:#C8502A;font-weight:600;margin-bottom:6px;">&#128336; {jam}</div>
      <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;">
        <span style="font-size:.62rem;color:#fff;background:#C8502A;padding:2px 8px;border-radius:50px;font-weight:700;">&#11088; {saw_pct}</span>
        <span style="font-size:.60rem;color:#555;background:#F7F3F0;padding:2px 6px;border-radius:50px;font-weight:500;">&#128101; {jml_r} review</span>
        <span style="font-size:.60rem;color:#1A7A3C;background:#EDFAF2;padding:2px 6px;border-radius:50px;font-weight:600;">&#10003; {aktif_str} aktif</span>
      </div>
    </div>
    {top5_html}
    <a href="{nav_url}" style="display:block;text-align:center;padding:10px 8px;background:#C8502A;color:#fff;font-size:.73rem;font-weight:700;text-decoration:none;border-radius:0 0 12px 12px;">Lihat Detail →</a>
  </div>
</div>"""


@st.cache_data(show_spinner=False)
def build_all_slides_html(
    best_df_json: str,
    top5_json: str,
    reviewer_pct_json: str,
    cats_json: str,
    clrs_json: str,
    cat_icons_json: str,
    cat_bg_json: str,
    card_w: int, img_h: int, top5_h: int, body_h: int,
) -> str:
    """
    [G1][G3] Bangun HTML slideshow semua kategori sebagai string murni
    (bukan full HTML document) — akan di-render via st.markdown, bukan iframe.
    [G5] Key top5_lookup sudah string "kid|cat" sejak serialisasi.
    """
    import io
    best_df      = pd.read_json(io.StringIO(best_df_json), orient="records")
    top5_lookup  = json.loads(top5_json)   # key: "kid|cat" string
    reviewer_pct = json.loads(reviewer_pct_json)
    unique_cats  = json.loads(cats_json)
    clrs         = json.loads(clrs_json)
    cat_icons    = json.loads(cat_icons_json)
    cat_bg       = json.loads(cat_bg_json)

    if best_df.empty:
        return ""

    card_total_w = card_w + 16
    body_parts   = []

    for idx_cat, cat in enumerate(unique_cats):
        cat_ranked = best_df[best_df["category_aspect_kafe"] == cat].reset_index(drop=True)
        if cat_ranked.empty:
            continue

        bg_sec             = cat_bg.get(cat, "#fff")
        icon               = cat_icons.get(cat, "&#9749;")
        accentbg, accentfg = clrs[idx_cat % len(clrs)]
        n_total            = len(cat_ranked)
        uid                = cat.replace(" ", "_").replace("/", "_").lower()

        # [G5] subset top5 dengan key string
        kids_in_cat = set(cat_ranked["kafe_id"].astype(str).tolist())
        top5_subset = {
            key: v
            for key, v in top5_lookup.items()
            if isinstance(key, str) and "|" in key
            and key.split("|", 1)[0] in kids_in_cat
            and key.split("|", 1)[1] == cat
        }

        all_cards_html = "".join(
            _build_one_card_html(row, i + 1, cat, bg_sec, top5_subset, reviewer_pct)
            for i, (_, row) in enumerate(cat_ranked.iterrows())
        )

        section_html = f"""
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
        body_parts.append(section_html)

    if not body_parts:
        return ""

    divider = '<hr style="border:none;border-top:1px solid #E8DDD5;margin:0;">'
    all_body = divider.join(body_parts)

    # Script slideshow: satu fungsi global, bukan per-kategori
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


# ── Render Best Kafe ──────────────────────────────────────────
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

_pref_active = bool(all_selected) or bool(pref_lokasi_input)

# ✅ Load precompute LAZY — hanya di sini, setelah UI dasar sudah render
if not _any_popup_active and not _pref_active and not df.empty:
    if "_cached_best_df" not in st.session_state:
        try:
            with st.spinner("☕ Memuat ranking kafe..."):
                _df_cache_key = (
                    df.shape,
                    hash(str(df.iloc[0].values.tolist()) if len(df) > 0 else "empty")
                )
                best_df      = get_best_per_category(_df_cache_key[0], _df_cache_key[1])
                _top5_lookup = precompute_all_top5(_df_cache_key[0], _df_cache_key[1])
            st.session_state["_cached_best_df"] = best_df
            st.session_state["_cached_top5"]    = _top5_lookup
        except Exception:
            best_df      = pd.DataFrame()
            _top5_lookup = {}
            st.session_state["_cached_best_df"] = best_df
            st.session_state["_cached_top5"]    = _top5_lookup
    else:
        best_df      = st.session_state["_cached_best_df"]
        _top5_lookup = st.session_state["_cached_top5"]

if not best_df.empty and not _any_popup_active and not _pref_active:
    _slides_key = "_all_slides_html_guest"
    if _slides_key not in st.session_state:
        MAX_KAFE_PER_CAT = 15
        _top5_serializable = {f"{k}|{c}": v for (k, c), v in _top5_lookup.items()}
        _best_df_trimmed = (
            best_df
            .groupby("category_aspect_kafe", group_keys=False)
            .apply(lambda g: g.head(MAX_KAFE_PER_CAT))
            .reset_index(drop=True)
        )

        _all_html = build_all_slides_html(
            best_df_json      = _best_df_trimmed.to_json(orient="records"),
            top5_json         = json.dumps(_top5_serializable),
            reviewer_pct_json = json.dumps(_reviewer_pct_dict),
            cats_json         = json.dumps(unique_cats),
            clrs_json         = json.dumps(_clrs),
            cat_icons_json    = json.dumps(CAT_ICONS),
            cat_bg_json       = json.dumps(CAT_BG),
            card_w            = CARD_W,
            img_h             = IMG_H,
            top5_h            = TOP5_H,
            body_h            = BODY_H,
        )
        st.session_state[_slides_key] = _all_html

    _all_html = st.session_state[_slides_key]
    if _all_html:
        st.markdown(_all_html, unsafe_allow_html=True)
        if len(_all_html) > 500_000:
            del st.session_state[_slides_key]

elif _pref_active and not _any_popup_active:
    st.markdown("""
    <div style="padding:24px 48px;background:#FFF8F3;border-top:1px solid #E8DDD5;">
      <div style="font-size:.88rem;color:#78716C;text-align:center;">
        ✏️ Selesaikan pilihan preferensi di atas, lalu klik
        <b style="color:#C8502A;">Simpan Preferensi</b> untuk melihat rekomendasi.
      </div>
    </div>
    """, unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# ANALISIS SENTIMEN — locked
# ════════════════════════════════════════════════════════════════
st.markdown('<div id="analisis-section"></div>', unsafe_allow_html=True)
st.markdown("""
<div style="background:linear-gradient(135deg,#1C1917,#2d1a0e);padding:52px 48px 48px;">
  <div style="max-width:660px;margin:0 auto;">
    <div style="text-align:center;margin-bottom:24px;">
      <div style="display:inline-block;background:rgba(200,80,42,.25);color:#F9A07A;font-size:.66rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;padding:4px 12px;border-radius:50px;margin-bottom:12px;">📈 Ingin analisis sentiment review kamu sendiri? analisis disini</div>
      <div style="font-family:'Fraunces',serif;font-size:1.45rem;font-weight:700;color:#fff;margin-bottom:6px;">Analisis Review Kafemu</div>
    </div>
    <div style="background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:20px;padding:28px 32px 32px;">
      <div style="display:flex;align-items:flex-start;gap:10px;background:rgba(200,80,42,.14);border:1px solid rgba(200,80,42,.28);border-radius:10px;padding:12px 16px;margin-bottom:18px;">
        <span style="font-size:1rem;">🔒</span>
        <span style="font-size:.82rem;color:#F9A07A;line-height:1.5;">Fitur ini butuh login dulu. Daftar gratis di bawah.</span>
      </div>
      <div style="background:rgba(255,255,255,.05);border:1.5px solid rgba(255,255,255,.1);border-radius:10px;padding:12px 16px;margin-bottom:14px;">
        <div style="font-size:.65rem;color:rgba(255,255,255,.35);font-weight:600;text-transform:uppercase;letter-spacing:.6px;margin-bottom:4px;">☕ Nama Kafe</div>
        <div style="height:20px;background:rgba(255,255,255,.04);border-radius:6px;"></div>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:14px;">
        <div style="flex:1;background:rgba(200,80,42,.2);border-radius:8px;padding:10px;text-align:center;font-size:.8rem;color:#F9A07A;font-weight:600;cursor:default;">✏️ Ketik Review</div>
        <div style="flex:1;background:rgba(255,255,255,.04);border-radius:8px;padding:10px;text-align:center;font-size:.8rem;color:rgba(255,255,255,.3);cursor:default;">📄 Upload Excel</div>
      </div>
      <div style="background:rgba(255,255,255,.04);border:1.5px dashed rgba(255,255,255,.12);border-radius:10px;padding:24px 16px;text-align:center;margin-bottom:14px;">
        <div style="font-size:.82rem;color:rgba(255,255,255,.3);">Tempel atau ketik review di sini...</div>
      </div>
      <div style="width:100%;padding:14px;background:rgba(200,80,42,.25);color:rgba(255,255,255,.4);border:1.5px solid rgba(200,80,42,.2);border-radius:50px;text-align:center;font-size:.9rem;font-weight:700;cursor:not-allowed;">
        🔒 Analisis Sekarang — Login Dulu
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# LOGIN SECTION
# ════════════════════════════════════════════════════════════════
_render_login_section()

# ════════════════════════════════════════════════════════════════
# FOOTER
# ════════════════════════════════════════════════════════════════
st.markdown('<div class="footer">&copy; 2025 &nbsp;<b>KafeSby</b>&nbsp;&middot; Rekomendasi Kafe Surabaya Berbasis Review Pengunjung</div>', unsafe_allow_html=True)
