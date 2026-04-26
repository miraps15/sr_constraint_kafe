# ============================================================
# Versi Streamlit Cloud
# Perubahan dari versi Colab:
#   - Akses users.xlsx → users_manager (Google Sheets API)
#   - Akses df_inference_kafe → utils_kafe.load_data()
#   - Tidak ada lagi path /content/drive
# ============================================================

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import os
from urllib.parse import unquote

from utils_kafe import (
    load_data,
    compute_overall_score,
    compute_saw_scores,
    compute_global_C, compute_imdb_wr, M_IMDB,
    gdrive_direct_url, COMMON_CSS,
)
from users_manager import (
    load_users, get_user_favorites, toggle_favorite,
)

st.session_state.setdefault("detail_kid", None)
st.session_state.setdefault("detail_nama", None)

st.set_page_config(page_title="Detail Kafe · KafeSby", page_icon="☕",
                   layout="wide", initial_sidebar_state="collapsed")

if "_go_back" in st.session_state:
    prev_page = st.session_state.pop("_go_back")
    if prev_page == "app_kafe.py":
        prev_page = "pages/app_kafe.py"
    if prev_page == "app_kafe1.py":
        prev_page = "pages/app_kafe1.py"
    try:
        st.switch_page(prev_page)
    except Exception:
        st.switch_page("pages/app_kafe1.py" if st.session_state.get("logged_in") else "app_kafe.py")

if st.session_state.get("_go_to_fav"):
    st.session_state.pop("_go_to_fav")
    st.switch_page("pages/favoritekafe.py")

st.markdown(COMMON_CSS, unsafe_allow_html=True)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,700;9..144,900&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top:0!important;padding-left:0!important;padding-right:0!important;max-width:100%!important; }
.stApp { background: #F9F6F3; }
.topbar { display:flex;align-items:center;justify-content:space-between;padding:13px 40px;background:#fff;border-bottom:1px solid #E8DDD5;box-shadow:0 2px 16px rgba(28,25,23,.06);position:sticky;top:0;z-index:999; }
.topbar-logo { font-family:'Fraunces',serif;font-size:1.4rem;font-weight:900;color:#1C1917;letter-spacing:-.5px; }
.topbar-logo span { color:#C8502A; }
.info-grid { display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin:16px 0 20px; }
.info-card { background:#fff;border-radius:12px;border:1.5px solid #E8DDD5;padding:14px 16px;transition:box-shadow .2s,transform .2s; }
.info-card:hover { box-shadow:0 4px 16px rgba(200,80,42,.1);transform:translateY(-2px); }
.info-label { font-size:.66rem;color:#78716C;font-weight:700;text-transform:uppercase;letter-spacing:.9px;margin-bottom:5px; }
.info-value { font-size:.88rem;color:#1C1917;font-weight:600;line-height:1.4; }
.info-value a { color:#C8502A;text-decoration:none; }
.info-value a:hover { text-decoration:underline; }
.score-hero { background:linear-gradient(135deg,#1C1917 0%,#2d1a0e 100%);border-radius:18px;padding:22px 26px;margin:0 0 16px;display:flex;align-items:center;gap:20px; }
.score-big-num { font-family:'Fraunces',serif;font-size:2.8rem;font-weight:900;color:#F9A07A;line-height:1;text-align:center;min-width:90px; }
.score-big-lbl { font-size:.7rem;color:rgba(255,255,255,.4);text-align:center;margin-top:3px; }
.cat-section { background:#fff;border-radius:14px;border:1.5px solid #E8DDD5;padding:18px 22px;margin-bottom:14px;overflow:hidden; }
div[data-testid="stButton"] > button { border-radius:50px!important;background:#C8502A!important;color:white!important;border:none!important;font-weight:700!important;font-size:.88rem!important;min-height:44px!important;transition:background .18s!important; }
div[data-testid="stButton"] > button:hover { background:#A33E20!important; }
div[data-testid="stButton"] > button:disabled { background:#E8DDD5!important;color:#aaa!important; }
.beranda-btn-wrap div[data-testid="stButton"] > button { background:transparent!important;color:#78716C!important;font-size:.78rem!important;font-weight:600!important;min-height:34px!important;padding:7px 14px!important;border-radius:8px!important;border:none!important; }
.beranda-btn-wrap div[data-testid="stButton"] > button:hover { background:#FFF0EB!important;color:#C8502A!important; }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# TENTUKAN HALAMAN BERANDA
# ════════════════════════════════════════════════════════════════
_is_logged_in = st.session_state.get("logged_in", False)
_beranda_page = "pages/app_kafe1.py" if _is_logged_in else "app_kafe.py"

# ════════════════════════════════════════════════════════════════
# NAVBAR
# ════════════════════════════════════════════════════════════════
col_logo, col_nav = st.columns([6, 2])
with col_logo:
    st.markdown('<div class="topbar" style="border-bottom:none;box-shadow:none;padding:13px 0;"><div class="topbar-logo">Kafe<span>Sby</span></div></div>', unsafe_allow_html=True)
with col_nav:
    st.markdown('<div class="beranda-btn-wrap" style="display:flex;justify-content:flex-end;padding-top:8px;">', unsafe_allow_html=True)
    if st.button("← Beranda", key="btn_beranda_sk1"):
        prev_page = st.session_state.get("_prev_page", _beranda_page)
        if prev_page == "app_kafe.py":
            prev_page = "pages/app_kafe.py"
        if prev_page == "app_kafe1.py":
            prev_page = "pages/app_kafe1.py"
        try:
            st.switch_page(prev_page)
        except Exception:
            st.switch_page(_beranda_page)
    st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# LOAD DATA
# ════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def get_df():
    df = load_data()
    for col in ["skor_sentimen"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["kafe_id"] = df["kafe_id"].astype(str)
    return df

df = get_df()

# ════════════════════════════════════════════════════════════════
# AMBIL PARAMETER KAFE
# ════════════════════════════════════════════════════════════════
params = st.query_params

kid_p     = st.session_state.get("detail_kid") or params.get("kid")
nama_p    = st.session_state.get("detail_nama") or (
            unquote(params.get("nama")) if params.get("nama") else None)
alamat_p  = st.session_state.pop("detail_alamat", None) or (
            unquote(params.get("alamat", "")) if params.get("alamat") else None)

detail_source      = st.session_state.pop("detail_source", None) or params.get("source", "kasus_a")
detail_vi_score    = st.session_state.pop("detail_vi_score", None)
detail_cond_chosen = st.session_state.pop("detail_cond_chosen", None)
detail_cat_chosen  = st.session_state.pop("detail_cat_chosen", None)

if not detail_cat_chosen:
    detail_cat_chosen = params.get("nav_cat", None)
    if detail_cat_chosen:
        detail_cat_chosen = unquote(detail_cat_chosen)

kafe_id = None
if kid_p:
    kafe_id = str(kid_p)
elif nama_p:
    match = df[df["nama_kafe"] == nama_p]["kafe_id"].values
    if len(match):
        kafe_id = str(match[0])
elif alamat_p:
    match = df[df["alamat_kafe"] == alamat_p]["kafe_id"].values
    if len(match):
        kafe_id = str(match[0])

if not kafe_id:
    st.error("Kafe tidak ditemukan. Silakan kembali ke beranda.")
    if st.button("← Beranda"):
        st.switch_page(_beranda_page)
    st.stop()

sub = df[df["kafe_id"] == kafe_id]
if sub.empty:
    st.error(f"Kafe ID '{kafe_id}' tidak ditemukan.")
    st.stop()

row       = sub.drop_duplicates("kafe_id").iloc[0]
nama_kafe = str(row.get("nama_kafe", "—"))

st.session_state["_current_kafe_id"]   = kafe_id
st.session_state["_current_kafe_nama"] = nama_kafe

# ════════════════════════════════════════════════════════════════
# INFO USER & FAVORIT
# ════════════════════════════════════════════════════════════════
_login_username = st.session_state.get("login_username", "")
_login_google   = st.session_state.get("login_google", "")
_is_google_user = bool(_login_google)
_identifier     = _login_google if _is_google_user else _login_username

_fav_state_key = f"is_fav_{kafe_id}"
if _fav_state_key not in st.session_state:
    if _is_logged_in and _identifier:
        favs = get_user_favorites(_identifier, _is_google_user)
        st.session_state[_fav_state_key] = nama_kafe in favs
    else:
        st.session_state[_fav_state_key] = False

_is_fav = st.session_state[_fav_state_key]

# ════════════════════════════════════════════════════════════════
# HITUNG SKOR SENTIMEN
# ════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def get_overall_scores_kasus_a(dataframe: pd.DataFrame) -> pd.DataFrame:
    return compute_overall_score(dataframe)

@st.cache_data(show_spinner=False)
def get_saw_scores_all(dataframe: pd.DataFrame) -> pd.DataFrame:
    return compute_saw_scores(dataframe)

@st.cache_data(show_spinner=False)
def get_best_per_category_cached(dataframe: pd.DataFrame) -> pd.DataFrame:
    from utils_kafe import compute_best_per_category_imdb
    return compute_best_per_category_imdb(dataframe)

overall_df = get_overall_scores_kasus_a(df)
saw_scores = get_saw_scores_all(df)
sub_kafe   = df[df["kafe_id"] == kafe_id].copy()

# Tentukan skor sesuai asal navigasi
if detail_source == "kasus_e" and detail_cat_chosen:
    best_cat_df  = get_best_per_category_cached(df)
    kafe_cat_row = best_cat_df[
        (best_cat_df["kafe_id"] == kafe_id) &
        (best_cat_df["category_aspect_kafe"] == detail_cat_chosen)
    ]
    if not kafe_cat_row.empty:
        overall_saw_score = float(kafe_cat_row.iloc[0]["saw_score"])
        overall_saw_pct   = float(kafe_cat_row.iloc[0]["sentimen_pct"])
    elif detail_vi_score is not None:
        overall_saw_score = float(detail_vi_score)
        overall_saw_pct   = float(detail_vi_score) * 100
    else:
        overall_saw_score = overall_saw_pct = 0.0
elif detail_vi_score is not None:
    overall_saw_pct   = float(detail_vi_score) * 100
    overall_saw_score = float(detail_vi_score)
else:
    kafe_overall = overall_df[overall_df["kafe_id"] == kafe_id]
    if not kafe_overall.empty:
        overall_saw_pct   = float(kafe_overall.iloc[0]["sentimen_pct_all"])
        overall_saw_score = float(kafe_overall.iloc[0]["overall_score"])
    else:
        overall_saw_pct = overall_saw_score = 0.0

kafe_saw = saw_scores[saw_scores["kafe_id"] == kafe_id].sort_values("sentimen_pct", ascending=False)

# Jumlah review
if "review_id" in sub_kafe.columns:
    jml_review_kafe = sub_kafe["review_id"].nunique()
elif "review" in sub_kafe.columns:
    jml_review_kafe = sub_kafe["review"].nunique()
else:
    jml_review_kafe = len(sub_kafe)

# Reviewer aktif
def compute_reviewer_aktif(sub: pd.DataFrame) -> float:
    if "status_reviewer" not in sub.columns or "review_id" not in sub.columns:
        return 0.0
    dedup = sub.drop_duplicates(subset=["review_id"])
    total = len(dedup)
    if total == 0:
        return 0.0
    aktif = dedup["status_reviewer"].astype(str).str.lower().str.strip().eq("aktif").sum()
    return round((aktif / total) * 100, 1)

reviewer_aktif_pct = compute_reviewer_aktif(sub_kafe)
reviewer_aktif_str = f"{reviewer_aktif_pct:.1f}%"

# ════════════════════════════════════════════════════════════════
# DATA KAFE
# ════════════════════════════════════════════════════════════════
alamat    = str(row.get("alamat_kafe", "—"))
jam       = str(row.get("jam_buka", "—"))
wa        = str(row.get("whatsapp", "#"))
harga     = str(row.get("range_harga", "—"))
menu_link = str(row.get("menu", "#"))
ig_link   = str(row.get("link_ig", ""))
ig_handle = ig_link.split("instagram.com/")[-1].rstrip("/") if "instagram.com/" in ig_link else ig_link
maps_link = str(row.get("link_maps", ""))

# ── Label skor ────────────────────────────────────────────────
source_label_map = {"kasus_a": "IMDb WR + SAW (Kasus A)", "kasus_b": "IMDb WR + SAW (Kasus B)",
                    "kasus_d": "IMDb WR + SAW (Kasus D)", "kasus_e": "IMDb WR + SAW (Kasus E)"}
score_source_label = source_label_map.get(detail_source, "IMDb WR + SAW")

if detail_source == "kasus_a" and detail_cond_chosen:
    score_main_title = "Sangat cocok untuk preferensi kamu"
    score_desc = f"Kafe ini unggul pada aspek <b>{detail_cond_chosen}</b> sesuai yang kamu prioritaskan"
elif detail_source == "kasus_e" and detail_cat_chosen:
    score_main_title = "Sangat cocok untuk preferensi kamu"
    score_desc = f"Kafe ini unggul pada category <b>{detail_cat_chosen}</b> sesuai yang kamu pilih"
else:
    if overall_saw_pct > 65:
        score_main_title = "Skor Sentimen Keseluruhan"
        score_desc = "Pengunjung umumnya sangat puas dengan kafe ini."
    elif overall_saw_pct > 50:
        score_main_title = "Skor Sentimen Keseluruhan"
        score_desc = "Mayoritas pengunjung memberikan respons positif."
    elif overall_saw_pct > 35:
        score_main_title = "Skor Sentimen Keseluruhan"
        score_desc = "Pengalaman pengunjung bervariasi, ada pro dan kontra."
    else:
        score_main_title = "Skor Sentimen Keseluruhan"
        score_desc = "Banyak aspek yang perlu ditingkatkan."

if overall_saw_pct > 65:
    sentiment_label, sentiment_color = "Sangat Positif", "#6EE7B7"
elif overall_saw_pct > 50:
    sentiment_label, sentiment_color = "Positif", "#93C5FD"
elif overall_saw_pct > 35:
    sentiment_label, sentiment_color = "Netral", "#FCD34D"
else:
    sentiment_label, sentiment_color = "Perlu Perbaikan", "#FCA5A5"

# ════════════════════════════════════════════════════════════════
# LAYOUT UTAMA
# ════════════════════════════════════════════════════════════════
st.markdown('<div style="padding:0 40px 48px;">', unsafe_allow_html=True)
st.markdown(f"""
<div style="padding:28px 0 0;">
  <h1 style="font-family:'Fraunces',serif;font-size:clamp(1.6rem,3vw,2.4rem);font-weight:900;color:#1C1917;margin:0 0 6px;line-height:1.15;">{nama_kafe}</h1>
  <p style="color:#78716C;font-size:.88rem;margin:0 0 4px;">&#128205; {alamat}</p>
</div>
""", unsafe_allow_html=True)

col_img, col_info = st.columns([5, 5], gap="large")

# ── KOLOM KIRI: Foto & Maps ────────────────────────────────────
with col_img:
    covers = []
    for c in ["cover", "slide_1", "slide_2"]:
        u = str(row.get(c, "")).strip()
        d = gdrive_direct_url(u)
        if d:
            covers.append(d)

    if covers:
        n_slides     = len(covers)
        slides_inner = "".join(
            f'<div id="slide_{i}" style="display:{"block" if i==0 else "none"};width:100%;height:320px;border-radius:16px;overflow:hidden;background:#f5ede5;">'
            f'<img src="{src}" alt="foto kafe" style="width:100%;height:320px;object-fit:cover;display:block;" loading="lazy" '
            f'onerror="this.parentElement.style.background=\'#f5ede5\';"></div>'
            for i, src in enumerate(covers)
        )
        nav_btns = ""
        if n_slides > 1:
            nav_btns = """
<button onclick="goSlide((cur-1+n)%n)" style="position:absolute;top:50%;left:10px;transform:translateY(-50%);width:34px;height:34px;border-radius:50%;border:none;background:rgba(0,0,0,.45);color:#fff;font-size:1rem;cursor:pointer;z-index:10;padding:0;" onmouseover="this.style.background='rgba(200,80,42,.85)';" onmouseout="this.style.background='rgba(0,0,0,.45)';">&#9664;</button>
<button onclick="goSlide((cur+1)%n)" style="position:absolute;top:50%;right:10px;transform:translateY(-50%);width:34px;height:34px;border-radius:50%;border:none;background:rgba(0,0,0,.45);color:#fff;font-size:1rem;cursor:pointer;z-index:10;padding:0;" onmouseover="this.style.background='rgba(200,80,42,.85)';" onmouseout="this.style.background='rgba(0,0,0,.45)';">&#9654;</button>"""
        dots_inner = ""
        if n_slides > 1:
            dots_inner = '<div style="text-align:center;margin-top:10px;">' + "".join(
                f'<button id="dot_{i}" onclick="goSlide({i})" style="width:{"14px" if i==0 else "8px"};height:8px;border-radius:50px;border:none;background:{"#C8502A" if i==0 else "#D6CEC8"};cursor:pointer;margin:0 3px;padding:0;transition:all .2s;"></button>'
                for i in range(n_slides)
            ) + '</div>'

        maps_section = ""
        maps_height  = 0
        if maps_link and maps_link not in ["#", "nan", "None", ""]:
            q_enc = nama_kafe.replace(" ", "+") + "+Surabaya"
            maps_section = f"""
<div style="margin-top:14px;"><a href="{maps_link}" target="_blank" style="display:inline-flex;align-items:center;gap:8px;background:#1C1917;color:#fff;padding:10px 20px;border-radius:50px;text-decoration:none;font-size:.82rem;font-weight:700;font-family:'Plus Jakarta Sans',sans-serif;">&#128205; Lihat di Google Maps</a></div>
<div style="border-radius:14px;overflow:hidden;margin-top:10px;"><iframe src="https://maps.google.com/maps?q={q_enc}&output=embed" width="100%" height="180" style="border:0;display:block;" allowfullscreen loading="lazy"></iframe></div>"""
            maps_height = 250

        js_code = f"""<script>
var cur=0, n={n_slides};
function goSlide(i){{
  for(var j=0;j<n;j++){{var s=document.getElementById('slide_'+j),d=document.getElementById('dot_'+j);if(s)s.style.display=j===i?'block':'none';if(d){{d.style.background=j===i?'#C8502A':'#D6CEC8';d.style.width=j===i?'14px':'8px';}}}}cur=i;
}}
if(n>1)setInterval(function(){{goSlide((cur+1)%n);}},3800);
</script>"""
        total_h = 320 + (30 if n_slides > 1 else 0) + maps_height + 40
        components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>*{{box-sizing:border-box;margin:0;padding:0;}}body{{background:transparent;overflow:hidden;}}</style></head><body>
<div style="width:100%;"><div style="position:relative;width:100%;border-radius:16px;overflow:hidden;">{slides_inner}{nav_btns}</div>{dots_inner}{maps_section}</div>{js_code}</body></html>""",
                         height=total_h, scrolling=False)
    else:
        maps_section = ""
        maps_height  = 0
        if maps_link and maps_link not in ["#", "nan", "None", ""]:
            q_enc        = nama_kafe.replace(" ", "+") + "+Surabaya"
            maps_section = f"""<div style="margin-top:14px;"><a href="{maps_link}" target="_blank" style="display:inline-flex;align-items:center;gap:8px;background:#1C1917;color:#fff;padding:10px 20px;border-radius:50px;text-decoration:none;font-size:.82rem;font-weight:700;font-family:sans-serif;">&#128205; Lihat di Google Maps</a></div><div style="border-radius:14px;overflow:hidden;margin-top:10px;"><iframe src="https://maps.google.com/maps?q={q_enc}&output=embed" width="100%" height="180" style="border:0;display:block;" allowfullscreen loading="lazy"></iframe></div>"""
            maps_height  = 250
        components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>*{{box-sizing:border-box;margin:0;padding:0;}}body{{background:transparent;}}</style></head><body>
<div style="width:100%;height:320px;border-radius:16px;background:#f5ede5;display:flex;align-items:center;justify-content:center;font-size:5rem;color:#c8a898;">&#9749;</div>
{maps_section}</body></html>""", height=320 + maps_height + 20, scrolling=False)

# ── KOLOM KANAN: Skor + Info + Favorit ───────────────────────
with col_info:
    st.markdown(f"""
<div class="score-hero">
  <div><div class="score-big-num">{overall_saw_pct:.1f}%</div><div class="score-big-lbl">Skor Sentimen</div></div>
  <div style="flex:1;">
    <div style="display:inline-block;background:rgba(255,255,255,.1);color:{sentiment_color};font-size:.72rem;font-weight:700;padding:3px 10px;border-radius:50px;margin-bottom:8px;">{sentiment_label}</div>
    <div style="font-size:.88rem;color:#fff;font-weight:700;margin-bottom:4px;">{score_main_title}</div>
    <div style="font-size:.78rem;color:rgba(255,255,255,.6);line-height:1.55;">{score_desc}<br><span style="font-size:.72rem;color:rgba(255,255,255,.4);">Mayoritas pengunjung memberikan respons positif.</span></div>
  </div>
</div>
""", unsafe_allow_html=True)

    if _is_logged_in and _identifier:
        if _is_fav:
            fav_label = "✅ Sudah Difavoritkan"
            fav_info  = "✓ Kafe ini tersimpan di daftar favorit kamu"
            fav_info_c = "#1A7A3C"
        else:
            fav_label = "❤️ Favoritkan Kafe Ini"
            fav_info  = "Klik untuk menyimpan kafe ini ke daftar favorit"
            fav_info_c = "#78716C"
        col_fav, _ = st.columns([4, 3])
        with col_fav:
            btn_fav_clicked = st.button(fav_label, key=f"btn_fav_{kafe_id}", use_container_width=True)
        st.markdown(f'<p style="font-size:.74rem;color:{fav_info_c};margin-top:2px;margin-bottom:12px;">{fav_info}</p>', unsafe_allow_html=True)
        if btn_fav_clicked:
            new_state = toggle_favorite(_identifier, _is_google_user, nama_kafe)
            st.session_state[_fav_state_key] = new_state
            if new_state:
                removed = st.session_state.get("_fav_removed_set", set())
                if nama_kafe in removed:
                    removed.remove(nama_kafe)
                    st.session_state["_fav_removed_set"] = removed
                st.session_state["last_favorited_kafe"] = {
                    "kafe_id": kafe_id, "nama_kafe": nama_kafe,
                    "alamat_kafe": alamat, "jam_buka": jam,
                    "total_review": jml_review_kafe, "cover": row.get("cover", ""),
                }
            if new_state:
                st.session_state.update({"detail_kid": str(kafe_id),
                                          "detail_nama": nama_kafe, "_go_to_fav": True})
                st.rerun()
    else:
        col_fav, _ = st.columns([4, 3])
        with col_fav:
            st.button("🔒 Favoritkan Kafe", key=f"btn_fav_disabled_{kafe_id}",
                      disabled=True, use_container_width=True)
        st.markdown('<p style="font-size:.74rem;color:#bbb;margin-top:2px;margin-bottom:12px;">🔒 Login terlebih dahulu untuk menyimpan ke favorit</p>', unsafe_allow_html=True)

    st.markdown(f"""
<div class="info-grid">
  <div class="info-card"><div class="info-label">&#128336; Jam Buka</div><div class="info-value">{jam}</div></div>
  <div class="info-card"><div class="info-label">&#128176; Harga</div><div class="info-value">{harga}</div></div>
  <div class="info-card"><div class="info-label">&#128101; Total Review</div><div class="info-value">{jml_review_kafe:,} review</div></div>
  <div class="info-card"><div class="info-label">&#9989; Reviewer Aktif</div><div class="info-value">{reviewer_aktif_str}</div></div>
  <div class="info-card"><div class="info-label">&#128222; WhatsApp</div><div class="info-value"><a href="{wa}" target="_blank">Hubungi via WA &#8594;</a></div></div>
  <div class="info-card"><div class="info-label">&#128196; Menu</div><div class="info-value"><a href="{menu_link}" target="_blank">Lihat Menu &#8594;</a></div></div>
  <div class="info-card"><div class="info-label">&#128247; Instagram</div><div class="info-value"><a href="{ig_link}" target="_blank">@{ig_handle}</a></div></div>
</div>
""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# ANALISIS SENTIMEN PER KATEGORI (Kasus C)
# ════════════════════════════════════════════════════════════════
st.markdown('<hr style="border:none;border-top:1px solid #E8DDD5;margin:0;">', unsafe_allow_html=True)
st.markdown("""
<div style="padding:36px 40px 8px;background:#F9F6F3;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px;">
    <div style="width:4px;height:36px;background:#C8502A;border-radius:2px;"></div>
    <div>
      <h3 style="font-family:'Fraunces',serif;font-size:1.25rem;font-weight:900;color:#1C1917;margin:0 0 2px;">Analisis Sentimen per Kategori</h3>
      <p style="font-size:.8rem;color:#78716C;margin:0;">Ringkasan sentimen berdasarkan ulasan pengunjung</p>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

_cat_colors = ["#C8502A","#B8730A","#1A6EB0","#1A7A3C","#7C3AED","#BE185D"]
_cat_bgs    = ["#FFF0EB","#FFF7E6","#EBF5FF","#F0FBF0","#F5F0FF","#FFF0F5"]
_cat_borders= ["#FDDDD5","#FDECC8","#C3DEFF","#BBF0CC","#D9C9FF","#FFC9DE"]
_cat_icons  = ["🍽️","⭐","✨","💚","💜","💗"]

unique_cats_kafe = kafe_saw["category_aspect_kafe"].tolist() if not kafe_saw.empty else []
st.markdown('<div style="padding:16px 40px 40px;background:#F9F6F3;">', unsafe_allow_html=True)

if kafe_saw.empty:
    st.markdown('<div style="background:#fff;border-radius:14px;border:1.5px solid #E8DDD5;padding:32px;text-align:center;color:#aaa;"><div style="font-size:2rem;margin-bottom:8px;">📊</div>Belum ada data analisis sentimen untuk kafe ini.</div>', unsafe_allow_html=True)
else:
    n_cats = len(unique_cats_kafe)
    cols   = st.columns(2, gap="medium") if n_cats > 1 else [st.container()]

    C_val          = compute_global_C(df)
    all_conds_kafe = sub_kafe["aspect_condition"].dropna().unique().tolist()
    cond_wr_kafe   = {}
    for cond in all_conds_kafe:
        sub_c         = sub_kafe[sub_kafe["aspect_condition"] == cond]
        wr            = compute_imdb_wr(float(len(sub_c)), float(sub_c["skor_sentimen"].mean()), C_val, M_IMDB)
        cond_wr_kafe[cond] = round(wr * 100, 1)

    for idx_cat, cat_row in kafe_saw.iterrows():
        cat        = cat_row["category_aspect_kafe"]
        saw_v      = float(cat_row.get("saw_score", 0) or 0)
        sentimen_v = float(cat_row.get("sentimen_pct", 0) or 0)
        if cat not in unique_cats_kafe:
            continue
        col_idx  = unique_cats_kafe.index(cat) % len(_cat_colors)
        c_color  = _cat_colors[col_idx]
        c_bg     = _cat_bgs[col_idx]
        c_border = _cat_borders[col_idx]
        c_icon   = _cat_icons[col_idx]

        sub_cat_kafe = sub_kafe[sub_kafe["category_aspect_kafe"] == cat].copy()
        cond_scores  = sorted(
            [{"cond": cn, "pct": cond_wr_kafe.get(cn, 0.0), "n": len(cdf)}
             for cn, cdf in sub_cat_kafe.groupby("aspect_condition")],
            key=lambda x: x["pct"], reverse=True
        )
        saw_pct     = round(saw_v * 100, 1)
        cat_display = cat.replace("_", " ").title()
        col_target  = cols[unique_cats_kafe.index(cat) % len(cols)] if n_cats > 1 else cols[0]

        bars_html = ""
        for cs in cond_scores:
            bar_w     = min(cs["pct"], 100)
            bar_c     = c_color if cs["pct"] >= 50 else "#EF4444"
            bars_html += f"""
<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
  <div style="font-size:.76rem;font-weight:500;color:#1C1917;min-width:150px;max-width:150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{cs['cond']}">{cs['cond']}</div>
  <div style="flex:1;height:7px;background:#EDE8E4;border-radius:50px;overflow:hidden;"><div style="height:7px;width:{bar_w}%;background:{bar_c};border-radius:50px;"></div></div>
  <div style="font-size:.76rem;font-weight:700;min-width:40px;text-align:right;color:{bar_c};">{cs['pct']}%</div>
  <div style="font-size:.62rem;color:#bbb;min-width:44px;text-align:right;">{cs['n']} ulasan</div>
</div>"""

        with col_target:
            st.markdown(f"""
<div style="background:#fff;border-radius:14px;border:2px solid {c_border};padding:18px 20px;margin-bottom:14px;box-shadow:0 2px 8px rgba(0,0,0,.04);">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
    <div style="display:flex;align-items:center;gap:9px;">
      <div style="width:36px;height:36px;border-radius:10px;background:{c_bg};display:flex;align-items:center;justify-content:center;font-size:.95rem;">{c_icon}</div>
      <div><div style="font-family:'Fraunces',serif;font-size:.9rem;font-weight:800;color:#1C1917;">{cat_display}</div><div style="font-size:.66rem;color:#aaa;">Berdasarkan ulasan pengunjung</div></div>
    </div>
    <div style="text-align:right;"><div style="font-family:'Fraunces',serif;font-size:1.4rem;font-weight:900;color:{c_color};">{saw_pct}%</div><div style="font-size:.64rem;color:#aaa;">Skor Kategori</div></div>
  </div>
  <div style="margin-bottom:6px;padding:6px 10px;background:{c_bg};border-radius:8px;"><span style="font-size:.66rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:{c_color};">{cat_display} · Detail Aspect Condition</span></div>
  {bars_html if bars_html else '<p style="font-size:.76rem;color:#bbb;padding:4px 0;">Tidak ada data kondisi.</p>'}
</div>
""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# FOOTER
# ════════════════════════════════════════════════════════════════
st.markdown("""
<div style="background:#111;padding:22px 48px;text-align:center;color:rgba(255,255,255,.22);font-size:.74rem;">
  &copy; 2025 &nbsp;<b style="color:#C8502A;">KafeSby</b>&nbsp;&middot; Rekomendasi Kafe Surabaya Berbasis Review Pengunjung
</div>
""", unsafe_allow_html=True)
