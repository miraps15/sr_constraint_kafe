# pages/favoritekafe.py
# PERUBAHAN untuk Streamlit Cloud:
#   - Tidak ada lagi akses file lokal users.xlsx di /content/drive/...
#   - Semua operasi user (load, toggle, remove favorit) menggunakan
#     users_manager.py yang sudah terintegrasi dengan Google Sheets
#   - load_data() menggunakan utils_kafe yang baca dari Google Sheets
#   - os.path.exists / pd.read_excel lokal dihilangkan sepenuhnya
# Fungsionalitas tampilan dan perhitungan SAW tidak diubah.

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import json
import os
from utils_kafe import (
    load_data, compute_saw_scores, compute_overall_score,
    gdrive_direct_url, COMMON_CSS
)
from users_manager import (
    load_users, get_user_favorites, toggle_favorite
)

st.session_state.setdefault("detail_kid", None)
st.session_state.setdefault("detail_nama", None)

st.set_page_config(
    page_title="Favorit Kafe · KafeSby",
    page_icon="❤️", layout="wide",
    initial_sidebar_state="collapsed"
)
st.markdown("""
<style>
div[data-testid="stButton"] > button {
    width: 100%;
    border-radius: 10px;
    font-weight: 700;
}
</style>
""", unsafe_allow_html=True)

# ===== BACK NAVIGATION HANDLER =====
if "_go_back" in st.session_state:
    prev_page = st.session_state.pop("_go_back")
    try:
        st.switch_page(prev_page)
    except Exception:
        st.switch_page("app_kafe.py")

st.markdown(COMMON_CSS, unsafe_allow_html=True)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,700;9..144,900&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding-top: 0 !important; padding-left: 0 !important;
    padding-right: 0 !important; max-width: 100% !important;
}
.stApp { background: #F9F6F3; }
.topbar {
    display:flex; align-items:center; justify-content:space-between;
    padding:13px 40px; background:#fff; border-bottom:1px solid #E8DDD5;
    box-shadow:0 2px 16px rgba(28,25,23,.06);
    position:sticky; top:0; z-index:999;
}
.topbar-logo { font-family:'Fraunces',serif; font-size:1.4rem; font-weight:900; color:#1C1917; letter-spacing:-.5px; }
.topbar-logo span { color:#C8502A; }
.fav-hero {
    background: linear-gradient(135deg,#1C1917 0%,#2d1a0e 100%);
    padding: 52px 48px 44px;
}
.fav-hero .tag {
    display:inline-flex;align-items:center;gap:6px;
    background:rgba(200,80,42,.28);color:#F9A07A;
    font-size:.72rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
    padding:5px 14px;border-radius:50px;margin-bottom:14px;
}
.fav-hero h2 {
    font-family:'Fraunces',serif;font-size:clamp(1.6rem,3vw,2.2rem);
    font-weight:900;color:#fff;margin:0 0 8px;line-height:1.2;
}
.fav-hero h2 span { color:#F9A07A; }
.fav-hero p { font-size:.88rem; color:rgba(255,255,255,.5); margin:0; }
div[data-testid="stButton"] > button {
    background: #C8502A !important; color: #fff !important;
    border: none !important; border-radius: 10px !important;
    font-weight: 700 !important; font-size: .84rem !important;
    padding: 8px 16px !important;
}
div[data-testid="stButton"] > button:hover { background: #A33E20 !important; }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# GUARD
# ════════════════════════════════════════════════════════════════
if not st.session_state.get("logged_in", False):
    st.switch_page("app_kafe.py")

# ════════════════════════════════════════════════════════════════
# FUNGSI HAPUS FAVORIT — menggunakan users_manager
# ════════════════════════════════════════════════════════════════
def remove_favorite(identifier: str, is_google: bool, nama_kafe: str):
    """
    Hapus satu kafe dari daftar favorit user.
    Menggunakan toggle_favorite dari users_manager (via Google Sheets).
    """
    try:
        # Cek dulu apakah kafe ini benar ada di favorit
        current_favs = get_user_favorites(identifier, is_google)
        if nama_kafe in current_favs:
            # toggle_favorite akan menghapus jika sudah ada
            toggle_favorite(identifier, is_google, nama_kafe)
    except Exception as e:
        st.warning(f"Gagal menghapus favorit: {e}")

# ════════════════════════════════════════════════════════════════
# INFO USER
# ════════════════════════════════════════════════════════════════
_login_username = st.session_state.get("login_username", "")
_login_google   = st.session_state.get("login_google", "")
_is_google      = bool(_login_google)
_display_name   = _login_username
_identifier     = _login_google if _is_google else _login_username

# ════════════════════════════════════════════════════════════════
# NAVBAR
# ════════════════════════════════════════════════════════════════
st.markdown("""
<div class="topbar">
  <div class="topbar-logo">
    <a href="/" target="_self" style="text-decoration:none;color:inherit;">Kafe<span>Sby</span></a>
  </div>
  <nav style="display:flex;gap:4px;">
    <a href="/app_kafe1" target="_self"
       style="text-decoration:none;color:#78716C;font-size:.78rem;font-weight:600;
              padding:7px 14px;border-radius:8px;transition:background .18s;"
       onmouseover="this.style.background='#FFF0EB';this.style.color='#C8502A';"
       onmouseout="this.style.background='';this.style.color='#78716C';">
      &#8592; Kembali ke Beranda
    </a>
  </nav>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# LOAD DATA — via utils_kafe (Google Sheets)
# ════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False, ttl=600)
def get_df():
    df = load_data()
    df["skor_sentimen"] = pd.to_numeric(df["skor_sentimen"], errors="coerce").fillna(0)
    df["kafe_id"] = df["kafe_id"].astype(str)
    return df

df = get_df()
M_SHRINKAGE = 10

@st.cache_data(show_spinner=False, ttl=600)
def get_overall_df(_dataframe_hash: int, dataframe: pd.DataFrame) -> pd.DataFrame:
    return compute_overall_score(dataframe)

@st.cache_data(show_spinner=False, ttl=600)
def get_saw_df(_dataframe_hash: int, dataframe: pd.DataFrame) -> pd.DataFrame:
    return compute_saw_scores(dataframe)

# Gunakan hash shape sebagai cache key agar cache tidak stale
_df_hash = hash(str(df.shape))
overall_df = get_overall_df(_df_hash, df)
saw_df     = get_saw_df(_df_hash, df)

# ════════════════════════════════════════════════════════════════
# AMBIL FAVORIT USER — via users_manager (Google Sheets)
# ════════════════════════════════════════════════════════════════
fav_names = get_user_favorites(_identifier, _is_google)

# Tambahkan realtime favorit dari session state (jika baru difavoritkan)
if "last_favorited_kafe" in st.session_state:
    last = st.session_state["last_favorited_kafe"]
    if last and "nama_kafe" in last:
        if last["nama_kafe"] not in fav_names:
            fav_names.append(last["nama_kafe"])

# Sinkronisasi dengan daftar yang sudah dihapus di session
removed_set = set(st.session_state.get("_fav_removed_set", set()))
fav_names   = [n for n in fav_names if n not in removed_set]

n_fav = len(fav_names)

# ════════════════════════════════════════════════════════════════
# HERO SECTION
# ════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="fav-hero">
  <div class="tag">&#10084; Kafe Favoritmu</div>
  <h2>Daftar Kafe Favorit<br><span>{_display_name}</span></h2>
  <p>{n_fav} kafe tersimpan dalam daftar favoritmu.</p>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# JIKA TIDAK ADA FAVORIT
# ════════════════════════════════════════════════════════════════
if not fav_names:
    st.markdown("""
<div style="padding:48px;background:#fff;text-align:center;">
  <div style="font-size:3.5rem;margin-bottom:16px;">☕</div>
  <div style="font-family:'Fraunces',serif;font-size:1.2rem;font-weight:800;
    color:#1C1917;margin-bottom:8px;">Belum Ada Kafe Favorit</div>
  <p style="font-size:.88rem;color:#78716C;max-width:400px;margin:0 auto 24px;">
    Jelajahi kafe-kafe di Surabaya dan klik
    <b style="color:#C8502A;">❤️ Favoritkan Kafe Ini</b>
    di halaman detail kafe untuk menyimpannya di sini.
  </p>
</div>
""", unsafe_allow_html=True)
    col_btn, _ = st.columns([2, 6])
    with col_btn:
        if st.button("🔍 Jelajahi Kafe", key="btn_jelajahi", use_container_width=True):
            st.switch_page("pages/app_kafe1.py")
    st.stop()

# ════════════════════════════════════════════════════════════════
# FILTER NAMA VALID
# ════════════════════════════════════════════════════════════════
all_nama_set = set(df["nama_kafe"].dropna().unique())
valid_fav    = [n for n in fav_names if n in all_nama_set]
invalid_fav  = [n for n in fav_names if n not in all_nama_set]

if invalid_fav:
    st.markdown(f"""
<div style="background:#FFFBEB;border:1.5px solid #F59E0B;border-radius:10px;
  padding:10px 20px;margin:8px 48px 0;">
  <span style="font-size:.82rem;color:#B8730A;">
    ⚠️ Beberapa kafe tidak ditemukan di dataset: {', '.join(invalid_fav)}
  </span>
</div>
""", unsafe_allow_html=True)

if not valid_fav:
    st.markdown('<div style="padding:32px 48px;text-align:center;"><p style="color:#78716C;">Tidak ada kafe favorit yang dapat ditampilkan.</p></div>', unsafe_allow_html=True)
    st.stop()

# ════════════════════════════════════════════════════════════════
# KOMPUTASI DATA PER KAFE FAVORIT
# ════════════════════════════════════════════════════════════════
info_cols_need  = ["kafe_id","nama_kafe","alamat_kafe","jam_buka",
                   "cover","link_maps","link_ig","whatsapp","menu","range_harga"]
info_cols_exist = [c for c in info_cols_need if c in df.columns]
kafe_info_df    = df[info_cols_exist].drop_duplicates("kafe_id").set_index("nama_kafe")

def get_kafe_data(nama: str) -> dict:
    sub = df[df["nama_kafe"] == nama]
    if sub.empty:
        return {}

    row_info = kafe_info_df.loc[nama] if nama in kafe_info_df.index else pd.Series()
    kid      = str(sub.iloc[0]["kafe_id"])

    # Jumlah review unik
    if "review_id" in sub.columns:
        jml_review = sub["review_id"].nunique()
    elif "review" in sub.columns:
        jml_review = sub["review"].nunique()
    else:
        jml_review = 0

    # Persentase reviewer aktif
    if "status_reviewer" in sub.columns and "review_id" in sub.columns:
        rev_status = sub.drop_duplicates(subset=["review_id", "kafe_id"])[["review_id", "status_reviewer"]]
        total_rev  = len(rev_status)
        aktif_rev  = (rev_status["status_reviewer"].str.lower().str.strip() == "aktif").sum()
        pct_aktif  = round((aktif_rev / total_rev * 100), 1) if total_rev > 0 else 0.0
    else:
        pct_aktif = 0.0

    # Skor SAW dari compute_overall_score
    kafe_ov = overall_df[overall_df["kafe_id"] == kid]
    saw_pct = round(float(kafe_ov.iloc[0]["sentimen_pct_all"]), 1) if not kafe_ov.empty else 0.0

    # Top 5 aspect_condition
    mu_global_kafe = df.groupby("aspect_condition")["skor_sentimen"].mean()
    grp  = sub.groupby("aspect_condition")
    r_i  = grp["skor_sentimen"].mean()
    n_i  = grp["skor_sentimen"].count()
    cond_base = pd.concat([r_i.rename("r_i"), n_i.rename("n_i")], axis=1).reset_index()
    cond_base = cond_base.merge(mu_global_kafe.rename("mu_j").reset_index(), on="aspect_condition", how="left")
    cond_base["mu_j"] = cond_base["mu_j"].fillna(cond_base["r_i"])
    cond_base["shrink"] = (
        (cond_base["n_i"] / (cond_base["n_i"] + M_SHRINKAGE)) * cond_base["r_i"] +
        (M_SHRINKAGE / (cond_base["n_i"] + M_SHRINKAGE)) * cond_base["mu_j"]
    )
    cond_base["pct"] = (cond_base["shrink"] * 100).round(1)
    top5_conds = cond_base.nlargest(5, "shrink")[["aspect_condition","pct"]].values.tolist()

    return {
        "kid"       : kid,
        "nama"      : nama,
        "alamat"    : str(row_info.get("alamat_kafe", "—")) if isinstance(row_info, pd.Series) else "—",
        "jam"       : str(row_info.get("jam_buka", "—")) if isinstance(row_info, pd.Series) else "—",
        "cover"     : str(row_info.get("cover", "")) if isinstance(row_info, pd.Series) else "",
        "jml_review": jml_review,
        "pct_aktif" : pct_aktif,
        "saw_pct"   : saw_pct,
        "top5_conds": top5_conds,
        "maps_link" : str(row_info.get("link_maps", "")) if isinstance(row_info, pd.Series) else "",
    }

# Urutkan berdasarkan skor SAW (tertinggi dulu)
kafe_data_list = []
for nama in valid_fav:
    data = get_kafe_data(nama)
    if data:
        kafe_data_list.append(data)

kafe_data_list.sort(key=lambda x: x["saw_pct"], reverse=True)

# ════════════════════════════════════════════════════════════════
# HANDLE NAVIGASI DETAIL
# ════════════════════════════════════════════════════════════════
if st.session_state.get("_fav_nav_to_detail"):
    nav_data = st.session_state.pop("_fav_nav_to_detail")
    st.session_state["detail_kid"]  = nav_data.get("kid", "")
    st.session_state["detail_nama"] = nav_data.get("nama", "")
    st.session_state["_prev_page"]  = "pages/favoritekafe.py"
    st.switch_page("pages/skemacari1.py")

# ════════════════════════════════════════════════════════════════
# RENDER KARTU FAVORIT
# ════════════════════════════════════════════════════════════════
CARD_W      = 280
CARD_GAP    = 16
RANK_COLORS = {1: "#D4A017", 2: "#8C8C8C", 3: "#A0522D"}
DOT_COLORS  = ["#C8502A","#B8730A","#1A6EB0","#1A7A3C","#7C3AED"]

st.markdown("""
<div style="padding:32px 48px 8px;background:#fff;">
  <div style="font-family:'Fraunces',serif;font-size:1.2rem;font-weight:800;
    color:#1C1917;display:flex;align-items:center;gap:10px;">
    ❤️ Kafe Favoritmu
    <span style="font-size:.76rem;color:#bbb;font-weight:400;
      font-family:'Plus Jakarta Sans',sans-serif;">
      Diurutkan berdasarkan skor SAW Shrinkage tertinggi
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

all_cards_html_list = []
for rank, data in enumerate(kafe_data_list, 1):
    rank_bg     = RANK_COLORS.get(rank, "rgba(28,25,23,.65)")
    nama        = data["nama"]
    alamat      = data["alamat"]
    jam         = data["jam"]
    cover       = data["cover"]
    kid         = data["kid"]
    jml_review  = data["jml_review"]
    pct_aktif   = data["pct_aktif"]
    saw_pct     = data["saw_pct"]
    top5_conds  = data["top5_conds"]

    direct = gdrive_direct_url(cover)

    if direct:
        img_html = (
            f'<img src="{direct}" alt="{nama}" '
            f'style="width:100%;height:160px;object-fit:cover;display:block;flex-shrink:0;" '
            f'loading="lazy" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">'
            f'<div style="display:none;width:100%;height:160px;background:#f5ede5;'
            f'align-items:center;justify-content:center;font-size:3rem;color:#c8a898;flex-shrink:0;">&#9749;</div>'
        )
    else:
        img_html = (
            '<div style="width:100%;height:160px;background:#f5ede5;display:flex;'
            'align-items:center;justify-content:center;font-size:3rem;'
            'color:#c8a898;flex-shrink:0;">&#9749;</div>'
        )

    if saw_pct > 65:
        sent_lbl = "Sangat Positif"; sent_c = "#1A7A3C"; sent_bg = "#EDFAF2"
    elif saw_pct > 50:
        sent_lbl = "Positif"; sent_c = "#1A6EB0"; sent_bg = "#EBF5FF"
    elif saw_pct > 35:
        sent_lbl = "Netral"; sent_c = "#B8730A"; sent_bg = "#FFF7E6"
    else:
        sent_lbl = "Perlu Perbaikan"; sent_c = "#C8502A"; sent_bg = "#FFF0EB"

    top5_html = ""
    for t_idx, (cond, pct) in enumerate(top5_conds):
        dot_clr    = DOT_COLORS[t_idx % len(DOT_COLORS)]
        bar_w      = min(int(pct), 100)
        cond_short = str(cond)[:28] + ("…" if len(str(cond)) > 28 else "")
        top5_html += f"""
<div style="display:flex;align-items:center;gap:6px;margin-bottom:5px;">
  <div style="width:18px;height:18px;border-radius:50%;background:{dot_clr};
    display:flex;align-items:center;justify-content:center;
    font-size:.56rem;font-weight:900;color:#fff;flex-shrink:0;">{t_idx+1}</div>
  <div style="font-size:.7rem;font-weight:500;color:#1C1917;flex:1;
    min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
    title="{cond}">{cond_short}</div>
  <div style="width:60px;height:4px;background:#EDE8E4;border-radius:2px;overflow:hidden;flex-shrink:0;">
    <div style="height:4px;border-radius:2px;background:{dot_clr};width:{bar_w}%;"></div>
  </div>
  <div style="font-size:.66rem;font-weight:700;color:{dot_clr};min-width:34px;text-align:right;">{pct:.0f}%</div>
</div>"""

    nama_short   = nama[:30] + ("…" if len(nama) > 30 else "")
    alamat_short = alamat[:35] + ("…" if len(alamat) > 35 else "")

    _card = f"""
<div style="background:#fff;border-radius:18px 18px 0 0;border:1.5px solid #E8DDD5;
  overflow:hidden;display:flex;flex-direction:column;">
  <div style="position:relative;flex-shrink:0;">
    <div style="position:absolute;top:10px;left:10px;width:28px;height:28px;
      border-radius:50%;background:{rank_bg};display:flex;align-items:center;
      justify-content:center;font-size:.68rem;font-weight:900;color:#fff;
      z-index:2;box-shadow:0 2px 8px rgba(0,0,0,.3);">{rank}</div>
    <div style="position:absolute;top:10px;right:10px;width:26px;height:26px;
      border-radius:50%;background:rgba(200,80,42,.88);display:flex;align-items:center;
      justify-content:center;font-size:.75rem;z-index:2;">&#10084;</div>
    {img_html}
  </div>
  <div style="padding:14px 16px 12px;flex:1;">
    <div style="font-family:'Fraunces',serif;font-size:.92rem;font-weight:800;
      color:#1C1917;margin-bottom:3px;white-space:nowrap;overflow:hidden;
      text-overflow:ellipsis;" title="{nama}">{nama_short}</div>
    <div style="font-size:.7rem;color:#999;margin-bottom:3px;white-space:nowrap;
      overflow:hidden;text-overflow:ellipsis;" title="{alamat}">
      &#128205; {alamat_short}
    </div>
    <div style="font-size:.7rem;color:#C8502A;font-weight:600;margin-bottom:10px;">
      &#128336; {jam}
    </div>
    <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
      <span style="font-size:.64rem;color:#555;background:#F7F3F0;
        padding:3px 8px;border-radius:50px;font-weight:500;">&#128101; {jml_review:,} review</span>
      <span style="font-size:.64rem;color:#1A7A3C;background:#EDFAF2;
        padding:3px 8px;border-radius:50px;font-weight:500;white-space:nowrap;">&#9989; {pct_aktif:.1f}% aktif</span>
      <span style="margin-left:auto;background:{sent_bg};color:{sent_c};
        font-weight:700;font-size:.62rem;padding:3px 9px;border-radius:50px;white-space:nowrap;">
        {saw_pct:.1f}% SAW
      </span>
    </div>
    <div style="display:inline-flex;align-items:center;gap:5px;
      background:{sent_bg};border:1px solid {sent_c}22;
      border-radius:8px;padding:5px 10px;margin-bottom:12px;width:100%;box-sizing:border-box;">
      <div style="font-size:.64rem;font-weight:700;color:{sent_c};">{sent_lbl}</div>
      <div style="flex:1;height:4px;background:{sent_c}22;border-radius:50px;overflow:hidden;margin:0 4px;">
        <div style="height:4px;background:{sent_c};border-radius:50px;width:{min(int(saw_pct),100)}%;"></div>
      </div>
    </div>
  </div>
  <div style="border-top:1px solid #F0EAE4;padding:10px 16px 14px;background:#FAFAF8;">
    <div style="font-size:.64rem;color:#78716C;font-weight:700;text-transform:uppercase;
      letter-spacing:.7px;margin-bottom:8px;">&#127942; Top 5 Aspek Terbaik</div>
    {top5_html if top5_html else '<div style="font-size:.72rem;color:#bbb;font-style:italic;">Tidak ada data aspek</div>'}
  </div>
</div>"""
    all_cards_html_list.append(_card)

# Render kolom dan tombol
n_cards = len(kafe_data_list)
cols = st.columns(n_cards) if n_cards > 0 else [st.container()]

for i, data in enumerate(kafe_data_list):
    col = cols[i % n_cards]
    card_html = all_cards_html_list[i]

    with col:
        st.markdown(card_html, unsafe_allow_html=True)

        # Tombol Detail
        if st.button(
            "📄 Detail",
            key=f"detail_{data['kid']}_{i}",
            use_container_width=True
        ):
            st.session_state["detail_kid"]  = data["kid"]
            st.session_state["detail_nama"] = data["nama"]
            st.session_state["_prev_page"]  = "pages/favoritekafe.py"
            st.switch_page("pages/skemacari1.py")

        # Tombol Hapus — menggunakan users_manager (Google Sheets)
        if st.button(
            "🗑 Hapus",
            key=f"hapus_{data['kid']}_{i}",
            use_container_width=True
        ):
            remove_favorite(_identifier, _is_google, data["nama"])
            # Tambahkan ke removed_set agar tidak muncul lagi sebelum rerun
            removed = set(st.session_state.get("_fav_removed_set", set()))
            removed.add(data["nama"])
            st.session_state["_fav_removed_set"] = removed
            st.rerun()

# ════════════════════════════════════════════════════════════════
# ANALISIS PREFERENSI FAVORIT
# ════════════════════════════════════════════════════════════════
def get_top_fav_conditions(fav_names_list: list, top_n: int = 5) -> list:
    if not fav_names_list:
        return []
    all_sub = df[df["nama_kafe"].isin(fav_names_list)].copy()
    if all_sub.empty:
        return []
    mu_global = df.groupby("aspect_condition")["skor_sentimen"].mean()
    grp  = all_sub.groupby("aspect_condition")
    r_i  = grp["skor_sentimen"].mean()
    n_i  = grp["skor_sentimen"].count()
    base = pd.concat([r_i.rename("r_i"), n_i.rename("n_i")], axis=1).reset_index()
    base = base.merge(mu_global.rename("mu_j").reset_index(), on="aspect_condition", how="left")
    base["mu_j"] = base["mu_j"].fillna(base["r_i"])
    base["shrink"] = (
        (base["n_i"] / (base["n_i"] + M_SHRINKAGE)) * base["r_i"] +
        (M_SHRINKAGE / (base["n_i"] + M_SHRINKAGE)) * base["mu_j"]
    )
    base["pct"] = (base["shrink"] * 100).round(1)
    top = base.nlargest(top_n, "shrink")[["aspect_condition","pct"]]
    return list(zip(top["aspect_condition"], top["pct"]))

top_fav_conds = get_top_fav_conditions(valid_fav)

best_kafe = kafe_data_list[0]["nama"]  if kafe_data_list else "—"
best_saw  = kafe_data_list[0]["saw_pct"] if kafe_data_list else 0

if len(valid_fav) == 1:
    opening = f"Kamu telah menyimpan <b style='color:#C8502A;'>{best_kafe}</b> sebagai kafe favoritmu dengan skor SAW Shrinkage <b>{best_saw:.1f}%</b>."
else:
    kafe_mentions = ", ".join(f"<b style='color:#C8502A;'>{d['nama']}</b>" for d in kafe_data_list[:3])
    sisa = len(kafe_data_list) - 3
    if sisa > 0:
        kafe_mentions += f" dan <b>{sisa} kafe lainnya</b>"
    opening = f"Kamu telah menyimpan <b>{len(valid_fav)} kafe</b> dalam daftar favorit, termasuk {kafe_mentions}."

pref_html = ""
if top_fav_conds:
    conds_str = " ".join(
        f'<span style="display:inline-block;background:#FFF0EB;color:#C8502A;'
        f'border-radius:50px;padding:3px 12px;font-size:.8rem;font-weight:700;'
        f'border:1px solid rgba(200,80,42,.2);margin:2px;">{c} ({p:.0f}%)</span>'
        for c, p in top_fav_conds
    )
    pref_html = (
        f"<br><br>Berdasarkan pola favoritmu, kamu tampaknya menyukai kafe dengan "
        f"kualitas tinggi pada aspek: {conds_str}"
    )

closing = "<br><br>Terus jelajahi kafe-kafe baru di Surabaya dan tambahkan ke favorit untuk rekomendasi yang semakin personal! ☕"
narasi  = opening + pref_html + closing

st.markdown(f"""
<div style="background:#fff;border-radius:18px;border:1.5px solid #E8DDD5;
  padding:32px 36px;margin:8px 48px 40px;">
  <div style="font-family:'Fraunces',serif;font-size:1.1rem;font-weight:800;
    color:#1C1917;margin-bottom:14px;display:flex;align-items:center;gap:8px;">
    &#128149; Preferensi Kafe Kamu
  </div>
  <div style="font-size:.88rem;color:#44352C;line-height:1.85;">{narasi}</div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# FOOTER
# ════════════════════════════════════════════════════════════════
st.markdown("""
<div style="background:#111;padding:22px 48px;text-align:center;color:rgba(255,255,255,.22);font-size:.74rem;">
  &copy; 2025 &nbsp;<b style="color:#C8502A;">KafeSby</b>&nbsp;&middot; Rekomendasi Kafe Surabaya Berbasis ABSA &amp; SAW
</div>
""", unsafe_allow_html=True)
