# pages/skemacari4.py
# Versi Streamlit Cloud: load_data() via Google Sheets API (utils_kafe.py)
# Perhitungan: IMDb Weighted Rating + SAW
# - Hanya lokasi (tanpa bobot user)  → Kasus B
# - Lokasi + bobot user              → Kasus D
# - Sentimen per kategori di kartu   → Kasus C

import streamlit as st
import pandas as pd
import numpy as np
import json
from utils_kafe import (
    load_data,
    compute_preference_scores_imdb,
    compute_location_scores_imdb,
    compute_category_scores_imdb,
    gdrive_direct_url, COMMON_CSS
)

# Tambahkan di awal setiap pages/*.py
import gc

def _page_crash_guard():
    """
    Guard untuk setiap sub-halaman.
    Jika terjadi OOM atau error fatal, redirect ke app_kafe.py.
    """
    # Cek apakah memory sudah terlalu tinggi sebelum render
    try:
        import resource, platform
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        mem_mb = usage / 1024 if platform.system() != 'Darwin' else usage / (1024*1024)
        
        if mem_mb > 450:  # Di atas 450MB, mulai bersihkan
            heavy_keys = [
                "_all_slides_html_guest", "_all_slides_html_loggedin",
                "_cached_best_df", "_cached_top5",
                "_cached_best_df_1", "_cached_top5_1",
            ]
            for k in heavy_keys:
                if k in st.session_state:
                    del st.session_state[k]
            gc.collect()
    except Exception:
        pass

_page_crash_guard()

st.set_page_config(
    page_title="Rekomendasi Preferensimu · KafeSby",
    page_icon="☕", layout="wide",
    initial_sidebar_state="collapsed"
)

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
    display: flex; align-items: center; justify-content: space-between;
    padding: 13px 40px; background: #fff;
    border-bottom: 1px solid #E8DDD5;
    box-shadow: 0 2px 16px rgba(28,25,23,.06);
    position: sticky; top: 0; z-index: 999;
}
.topbar-logo {
    font-family: 'Fraunces', serif; font-size: 1.4rem;
    font-weight: 900; color: #1C1917; letter-spacing: -.5px;
}
.topbar-logo span { color: #C8502A; }
.result-hero {
    background: linear-gradient(135deg, #1C1917 0%, #2d1a0e 100%);
    padding: 52px 48px 44px;
}
.result-hero .tag {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(200,80,42,.28); color: #F9A07A;
    font-size: .72rem; font-weight: 700; letter-spacing: 1.5px;
    text-transform: uppercase; padding: 5px 14px;
    border-radius: 50px; margin-bottom: 14px;
}
.result-hero h2 {
    font-family: 'Fraunces', serif;
    font-size: clamp(1.6rem,3vw,2.2rem);
    font-weight: 900; color: #fff; margin: 0 0 8px; line-height: 1.2;
}
.result-hero h2 span { color: #F9A07A; }
.result-hero p { font-size: .88rem; color: rgba(255,255,255,.5); margin: 0 0 16px; }
.pref-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.pref-chip {
    display: inline-flex; align-items: center; gap: 5px;
    background: rgba(200,80,42,.22); color: #F9A07A;
    border: 1px solid rgba(200,80,42,.35);
    border-radius: 50px; padding: 4px 12px;
    font-size: .74rem; font-weight: 600;
}
.pref-chip .w { background: rgba(200,80,42,.5); border-radius: 50px; padding: 1px 7px; font-size: .66px; }
.stats-bar {
    background: #fff; border-radius: 14px; border: 1.5px solid #E8DDD5;
    padding: 16px 24px; margin: 0 40px 24px;
    display: flex; align-items: center; gap: 24px; flex-wrap: wrap;
}
.stats-bar-num { font-family:'Fraunces',serif; font-size:1.6rem; font-weight:900; color:#C8502A; }
.stats-bar-lbl { font-size:.72rem; color:#78716C; font-weight:500; }
.kafe-card-4 {
    background: #fff;
    border-radius: 18px 18px 0 0;
    border: 1.5px solid #E8DDD5;
    border-bottom: none;
    overflow: hidden;
    position: relative;
    display: flex;
    flex-direction: column;
    transition: transform .22s, box-shadow .22s;
}
.kafe-card-4:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 32px rgba(200,80,42,.12);
    border-color: rgba(200,80,42,.3);
}
.kafe-rank-badge {
    position: absolute; top: 10px; left: 10px;
    width: 28px; height: 28px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: .7rem; font-weight: 800; color: #fff; z-index: 2;
    box-shadow: 0 2px 8px rgba(0,0,0,.25);
}
.kafe-card-body { padding: 12px 13px 6px; }
.kafe-card-name {
    font-family: 'Fraunces', serif; font-size: .88rem; font-weight: 800;
    color: #1C1917; margin-bottom: 3px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kafe-card-addr {
    font-size: .68rem; color: #999; margin-bottom: 4px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kafe-card-jam { font-size: .68rem; color: #C8502A; font-weight: 600; margin-bottom: 8px; }
.kafe-stats { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; margin-bottom: 9px; }
.stat-pill { font-size: .64rem; color: #555; background: #F7F3F0; padding: 2px 7px; border-radius: 50px; font-weight: 500; }
.stat-aktif-4 { font-size: .64rem; color: #1A7A3C; background: #EDFAF2; padding: 2px 7px; border-radius: 50px; font-weight: 600; }
.cat-sentimen-desc { border-top: 1px solid #F0EAE4; padding: 9px 13px 12px; background: #FAFAF8; }
.cat-sentimen-desc-title {
    font-size: .62rem; color: #78716C; font-weight: 600;
    text-transform: uppercase; letter-spacing: .7px; margin-bottom: 6px;
}
.cat-sentimen-row { display: flex; align-items: center; gap: 5px; margin-bottom: 4px; }
.cat-sentimen-badge {
    font-size: .60rem; font-weight: 700; padding: 2px 6px;
    border-radius: 50px; flex-shrink: 0; white-space: nowrap;
}
.cat-sentimen-text { font-size: .66rem; color: #44352C; line-height: 1.4; flex: 1; }
.sk4-detail-btn > div[data-testid="stButton"] > button {
    border-radius: 0 0 18px 18px !important;
    min-height: 34px !important;
    padding: 5px 8px !important;
    font-size: .76rem !important;
    font-weight: 600 !important;
    border: 1.5px solid #E8DDD5 !important;
    border-top: none !important;
    box-shadow: none !important;
    width: 100% !important;
    margin-top: 0 !important;
    background: #C8502A !important;
    color: #fff !important;
}
.sk4-detail-btn > div[data-testid="stButton"] > button:hover {
    background: #A33E20 !important;
}
div[data-testid="stButton"] > button {
    background: #C8502A !important; color: #fff !important;
    border: none !important; border-radius: 10px !important;
    font-weight: 600 !important; font-size: .8rem !important;
    padding: 8px 12px !important; width: 100% !important;
    transition: background .18s !important;
}
div[data-testid="stButton"] > button:hover { background: #A33E20 !important; }
.beranda-btn-wrap div[data-testid="stButton"] > button {
    background: transparent !important;
    color: #78716C !important;
    font-size: .78rem !important;
    font-weight: 600 !important;
    min-height: 34px !important;
    padding: 7px 14px !important;
    border-radius: 8px !important;
    border: none !important;
    width: auto !important;
}
.beranda-btn-wrap div[data-testid="stButton"] > button:hover {
    background: #FFF0EB !important;
    color: #C8502A !important;
}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# TENTUKAN HALAMAN BERANDA SESUAI STATUS LOGIN
# ════════════════════════════════════════════════════════════════
_is_logged_in = st.session_state.get("logged_in", False)
_beranda_page = "pages/app_kafe1.py" if _is_logged_in else "app_kafe.py"

# ── Navbar ──────────────────────────────────────────────────────
col_logo, col_nav = st.columns([6, 2])
with col_logo:
    st.markdown("""
<div style="padding: 13px 40px; background: #fff;">
  <div class="topbar-logo">Kafe<span>Sby</span></div>
</div>
""", unsafe_allow_html=True)
with col_nav:
    st.markdown('<div class="beranda-btn-wrap" style="display:flex; justify-content:flex-end; padding-top:8px; padding-right:40px;">', unsafe_allow_html=True)
    if st.button("← Beranda", key="btn_beranda_sk4"):
        st.switch_page(_beranda_page)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("""
<style>
section[data-testid="stVerticalBlock"] > div:first-child {
    position: sticky;
    top: 0;
    z-index: 999;
    background: #fff;
    border-bottom: 1px solid #E8DDD5;
    box-shadow: 0 2px 16px rgba(28,25,23,.06);
}
</style>
""", unsafe_allow_html=True)

# ── Load data ────────────────────────────────────────────────────
# load_data() membaca dari Google Sheets via gsheets_client
@st.cache_data(show_spinner=False)
def get_df():
    df = load_data()
    df["skor_sentimen"] = pd.to_numeric(df["skor_sentimen"], errors="coerce").fillna(0)
    df["kafe_id"] = df["kafe_id"].astype(str)
    return df

df = get_df()

# ── Precompute jumlah review per kafe (dari review_id) ───────────
@st.cache_data(show_spinner=False)
def get_jumlah_review_per_kafe_sk4(_dataframe: pd.DataFrame) -> pd.Series:
    if "review_id" in _dataframe.columns:
        return _dataframe.groupby("kafe_id")["review_id"].nunique()
    elif "review" in _dataframe.columns:
        return _dataframe.groupby("kafe_id")["review"].nunique()
    else:
        return _dataframe.groupby("kafe_id").size()

# ── Precompute persentase reviewer aktif per kafe ────────────────
@st.cache_data(show_spinner=False)
def get_reviewer_aktif_pct_sk4(_dataframe: pd.DataFrame) -> pd.Series:
    if "status_reviewer" not in _dataframe.columns or "review_id" not in _dataframe.columns:
        return pd.Series(dtype=float)
    df_dedup = _dataframe.drop_duplicates(subset=["kafe_id", "review_id"])
    total_per_kafe = df_dedup.groupby("kafe_id")["review_id"].count()
    aktif_per_kafe = df_dedup[
        df_dedup["status_reviewer"].astype(str).str.lower().str.strip() == "aktif"
    ].groupby("kafe_id")["review_id"].count()
    pct = (aktif_per_kafe / total_per_kafe * 100).fillna(0)
    return pct

_jumlah_review_map  = get_jumlah_review_per_kafe_sk4(df)
_reviewer_aktif_pct = get_reviewer_aktif_pct_sk4(df)

# ── Ambil preferensi dari session_state ─────────────────────────
pref_items  = st.session_state.get("pref_items", [])
pref_bobot  = st.session_state.get("pref_bobot", {})
pref_lokasi = st.session_state.get("pref_lokasi", "")

if not pref_items and not pref_lokasi:
    st.error("Preferensi tidak ditemukan. Silakan pilih aspek terlebih dahulu.")
    if st.button("← Kembali ke Beranda", key="btn_kembali_error_sk4"):
        st.switch_page(_beranda_page)
    st.stop()

# ── Tentukan kasus yang digunakan ───────────────────────────────
has_bobot = bool(pref_items)
detail_source_for_sk1 = "kasus_d" if has_bobot else "kasus_b"

# ── Normalisasi bobot user (Kasus D) ────────────────────────────
n_items     = len(pref_items)
bobot_final = {}
if pref_items:
    total_manual = sum(pref_bobot.get(c, 0) for c in pref_items)
    for c in pref_items:
        raw = pref_bobot.get(c, 0)
        bobot_final[c] = raw if total_manual > 0 else 1.0 / n_items
    s = sum(bobot_final.values())
    if s > 0:
        bobot_final = {k: v / s for k, v in bobot_final.items()}
    else:
        bobot_final = {c: 1.0 / n_items for c in pref_items}

# ── Hitung ranking ───────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_result_kasus_b(_df: pd.DataFrame) -> pd.DataFrame:
    return compute_location_scores_imdb(_df)

@st.cache_data(show_spinner=False)
def get_result_kasus_d(_df: pd.DataFrame, pref_json: str, bobot_json: str) -> pd.DataFrame:
    pref_list  = json.loads(pref_json)
    bobot_dict = json.loads(bobot_json)
    return compute_preference_scores_imdb(_df, pref_list, bobot_dict)

if has_bobot:
    pref_json  = json.dumps(sorted(pref_items))
    bobot_json = json.dumps({k: bobot_final[k] for k in sorted(bobot_final.keys())})
    result     = get_result_kasus_d(df, pref_json, bobot_json)
else:
    result = get_result_kasus_b(df)

# ── Filter lokasi ────────────────────────────────────────────────
lokasi_note = ""
if not result.empty and pref_lokasi and "kecamatan_kafe" in result.columns:
    result_lok = result[
        result["kecamatan_kafe"].str.lower() == pref_lokasi.lower()
    ].copy()
    if len(result_lok) > 0:
        result_display = result_lok.reset_index(drop=True)
        lokasi_note    = f" di <b>{pref_lokasi}</b>"
    else:
        result_display = result.reset_index(drop=True)
        lokasi_note    = ""
else:
    result_display = result.reset_index(drop=True)

# ── Skor per kategori (Kasus C) ──────────────────────────────────
@st.cache_data(show_spinner=False)
def get_cat_scores(_df: pd.DataFrame, kid: str) -> pd.DataFrame:
    return compute_category_scores_imdb(_df, kid)

def build_cat_sentimen_desc(kid: str) -> str:
    cat_df = get_cat_scores(df, kid)
    if cat_df.empty:
        return ""
    _cat_badge_colors = ["#C8502A","#B8730A","#1A6EB0","#1A7A3C","#7C3AED","#BE185D"]
    _cat_badge_bgs    = ["#FFF0EB","#FFF7E6","#EBF5FF","#F0FBF0","#F5F0FF","#FFF0F5"]
    unique_cats_list  = sorted(df["category_aspect_kafe"].dropna().unique().tolist())
    rows_html = ""
    for _, r in cat_df.iterrows():
        cat  = r["category_aspect_kafe"]
        pct  = round(float(r["sentimen_pct"]), 1)
        cidx = unique_cats_list.index(cat) % len(_cat_badge_colors) if cat in unique_cats_list else 0
        bc   = _cat_badge_colors[cidx]
        bb   = _cat_badge_bgs[cidx]
        rows_html += f"""
<div class="cat-sentimen-row">
  <span class="cat-sentimen-badge" style="background:{bb};color:{bc};">{cat}</span>
  <span class="cat-sentimen-text">Skor: <b style="color:{bc};">{pct:.1f}%</b></span>
</div>"""
    return f"""
<div class="cat-sentimen-desc">
  <div class="cat-sentimen-desc-title">&#128202; Sentimen per Kategori</div>
  {rows_html}
</div>"""

# ── Hero ─────────────────────────────────────────────────────────
if has_bobot:
    chips_html  = "".join(
        f'<span class="pref-chip">{c} <span class="w">{round(bobot_final.get(c,0)*100)}%</span></span>'
        for c in pref_items
    )
    hero_method = "Berdasarkan preferensi aspek dan bobot yang kamu pilih."
else:
    chips_html  = ""
    hero_method = "Berdasarkan lokasi yang kamu pilih."

lok_html = (
    f'<span class="pref-chip" style="background:rgba(26,110,176,.2);color:#5BA3D4;'
    f'border-color:rgba(26,110,176,.35);">&#128205; {pref_lokasi}</span>'
    if pref_lokasi else ""
)

st.markdown(f"""
<div class="result-hero">
  <div class="tag">&#10003; Hasil Pencarianmu</div>
  <h2>Kafe yang cocok<br><span>untuk kamu</span></h2>
  <p>{hero_method}</p>
  <div class="pref-chips">{chips_html}{lok_html}</div>
</div>
""", unsafe_allow_html=True)

if result_display.empty:
    st.markdown('<div style="padding:40px 48px;">', unsafe_allow_html=True)
    st.info("Tidak ada data kafe yang sesuai preferensi kamu. Silakan kembali dan ubah kriteria.")
    if st.button("← Kembali & Ubah Preferensi", key="btn_kembali_ubah_sk4"):
        st.switch_page(_beranda_page)
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ── Stats bar ─────────────────────────────────────────────────────
top_vi = round(float(result_display.iloc[0]["Vi"]) * 100, 1)
avg_vi = round(float(result_display["Vi"].mean()) * 100, 1)
st.markdown(f"""
<div class="stats-bar" style="margin-top:0;">
  <div>
    <div class="stats-bar-num">{len(result_display)}</div>
    <div class="stats-bar-lbl">Kafe Ditemukan{lokasi_note}</div>
  </div>
  <div style="width:1px;background:#E8DDD5;height:36px;"></div>
  <div>
    <div class="stats-bar-num">{top_vi:.1f}%</div>
    <div class="stats-bar-lbl">Skor Tertinggi</div>
  </div>
  <div style="width:1px;background:#E8DDD5;height:36px;"></div>
  <div>
    <div class="stats-bar-num">{avg_vi:.1f}%</div>
    <div class="stats-bar-lbl">Rata-rata Skor</div>
  </div>
  <div style="flex:1;text-align:right;">
    <span style="font-size:.78rem;color:#78716C;">Klik "Lihat Detail" untuk info lengkap kafe &#8594;</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Helper: render bintang dari Vi (0-1) ─────────────────────────
def vi_to_stars(vi: float) -> str:
    star_val = min(vi, 1.0) * 5.0
    full  = int(star_val)
    half  = 1 if (star_val - full) >= 0.5 else 0
    empty = 5 - full - half
    stars = "★" * full + ("½" if half else "") + "☆" * empty
    return f"{stars} ({vi * 100:.1f}%)"

# ── Grid kartu ────────────────────────────────────────────────────
IMG_H        = 150
RANK_COLORS  = {1: "#D4A017", 2: "#8C8C8C", 3: "#A0522D"}
cols_per_row = 4

st.markdown('<div style="padding: 8px 40px 40px;">', unsafe_allow_html=True)

rows_groups = [result_display.iloc[i:i+cols_per_row]
               for i in range(0, len(result_display), cols_per_row)]

for row_group in rows_groups:
    n_in_row   = len(row_group)
    col_ratios = ([1] * n_in_row + [max(1, cols_per_row - n_in_row)]
                  if n_in_row < cols_per_row else [1] * n_in_row)
    cols_layout = st.columns(col_ratios if n_in_row < cols_per_row else [1] * n_in_row,
                             gap="medium")

    for col_i, (df_idx, kafe_row) in enumerate(row_group.iterrows()):
        rank     = int(df_idx) + 1
        rank_bg  = RANK_COLORS.get(rank, "rgba(28,25,23,.65)")
        nama     = str(kafe_row.get("nama_kafe", "—"))
        alamat   = str(kafe_row.get("alamat_kafe", "—"))
        jam      = str(kafe_row.get("jam_buka", "—"))
        vi_val   = float(kafe_row.get("Vi", 0))
        cover    = str(kafe_row.get("cover", ""))
        direct   = gdrive_direct_url(cover)
        kid      = str(kafe_row.get("kafe_id", ""))

        star_str = vi_to_stars(vi_val)

        # Jumlah review dari review_id
        jml_rev_raw = _jumlah_review_map.get(kid, 0)
        try:
            jml_rev_val = int(float(jml_rev_raw))
            jml_rev_str = f"{jml_rev_val:,}".replace(",", ".")
        except Exception:
            jml_rev_str = "—"

        # Persentase reviewer aktif
        aktif_pct_raw = _reviewer_aktif_pct.get(kid, 0.0)
        try:
            aktif_pct_val = float(aktif_pct_raw)
        except Exception:
            aktif_pct_val = 0.0
        aktif_str = f"{aktif_pct_val:.1f}%"

        if direct:
            img_html = (
                f'<img src="{direct}" alt="{nama}" loading="lazy" '
                f'style="width:100%;height:{IMG_H}px;object-fit:cover;display:block;flex-shrink:0;" '
                f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">'
                f'<div style="display:none;width:100%;height:{IMG_H}px;background:#f5ede5;'
                f'align-items:center;justify-content:center;font-size:2rem;color:#c8a898;'
                f'flex-direction:column;">&#9749;<small style="font-size:.55rem;text-transform:uppercase;">No Photo</small></div>'
            )
        else:
            img_html = (
                f'<div style="width:100%;height:{IMG_H}px;background:#f5ede5;display:flex;'
                f'align-items:center;justify-content:center;font-size:2rem;color:#c8a898;'
                f'flex-direction:column;flex-shrink:0;">&#9749;'
                f'<small style="font-size:.55rem;text-transform:uppercase;">No Photo</small></div>'
            )

        cat_desc_html = build_cat_sentimen_desc(kid)

        card_html = f"""
<div class="kafe-card-4">
  <div class="kafe-rank-badge" style="background:{rank_bg};">{rank}</div>
  <div style="width:100%;height:{IMG_H}px;overflow:hidden;background:#f5ede5;flex-shrink:0;">
    {img_html}
  </div>
  <div class="kafe-card-body">
    <div class="kafe-card-name" title="{nama}">{nama}</div>
    <div class="kafe-card-addr" title="{alamat}">&#128205; {alamat}</div>
    <div class="kafe-card-jam">&#128336; {jam}</div>
    <div style="font-size:.72rem;color:#C8502A;font-weight:700;margin-bottom:6px;">
      Skor: {star_str}
    </div>
    <div class="kafe-stats">
      <span class="stat-pill">&#128101; {jml_rev_str} review</span>
      <span class="stat-aktif-4">&#10003; {aktif_str} aktif</span>
    </div>
  </div>
  {cat_desc_html}
</div>"""

        with cols_layout[col_i]:
            st.markdown(card_html, unsafe_allow_html=True)
            st.markdown('<div class="sk4-detail-btn">', unsafe_allow_html=True)
            if st.button(
                "Lihat Detail →",
                key=f"sk4_btn_{kid}_{rank}_{df_idx}",
                use_container_width=True
            ):
                st.session_state["detail_kid"]      = kid
                st.session_state["detail_nama"]     = nama
                st.session_state["detail_source"]   = detail_source_for_sk1
                st.session_state["detail_vi_score"] = vi_val
                st.session_state["_prev_page"] = "pages/skemacari4.py"
                st.switch_page("pages/skemacari1.py")
            st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
