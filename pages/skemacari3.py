# pages/skemacari3.py — Daftar kafe berdasarkan aspect_condition (grid ranking)
# Perhitungan: IMDb Weighted Rating + SAW (Kasus A)
# Versi Streamlit Cloud: load_data() via Google Sheets API (utils_kafe.py)

import streamlit as st
import pandas as pd
from urllib.parse import unquote
from utils_kafe import (
    load_data, compute_aspect_condition_scores_imdb,
    compute_category_scores_imdb,
    compute_imdb_wr, compute_global_C,
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

M_IMDB = 13

st.set_page_config(page_title="Hasil Pencarian · KafeSby", page_icon="☕",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown(COMMON_CSS, unsafe_allow_html=True)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,700;9..144,900&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding-top: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    max-width: 100% !important;
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
    background: linear-gradient(135deg, #1C1917 0%, #3a1a0a 100%);
    padding: 48px 48px 40px;
    margin-bottom: 0;
}
.result-hero .tag {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(200,80,42,.25); color: #F9A07A;
    font-size: .72rem; font-weight: 700; letter-spacing: 1.5px;
    text-transform: uppercase; padding: 5px 14px;
    border-radius: 50px; margin-bottom: 14px;
}
.result-hero h2 {
    font-family: 'Fraunces', serif;
    font-size: clamp(1.6rem, 3vw, 2.2rem);
    font-weight: 900; color: #fff;
    margin: 0 0 8px; line-height: 1.2;
}
.result-hero h2 span { color: #F9A07A; }
.result-hero p { font-size: .88rem; color: rgba(255,255,255,.55); margin: 0; }
.kafe-card-3 {
    background: #fff; border-radius: 18px 18px 0 0;
    border: 1.5px solid #E8DDD5; border-bottom: none; overflow: hidden;
    position: relative; margin-bottom: 0;
    transition: transform .22s, box-shadow .22s;
}
.kafe-card-3:hover {
    transform: translateY(-4px);
    box-shadow: 0 16px 40px rgba(200,80,42,.14);
    border-color: rgba(200,80,42,.3);
}
.kafe-card-3 img {
    width: 100%; height: 150px;
    object-fit: cover; display: block;
}
.kafe-card-3 .placeholder {
    width: 100%; height: 150px; background: #f5ede5;
    display: flex; align-items: center; justify-content: center;
    font-size: 2.2rem; color: #c8a898;
}
.kafe-rank-badge {
    position: absolute; top: 10px; left: 10px;
    width: 30px; height: 30px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: .72rem; font-weight: 800; color: #fff; z-index: 2;
    box-shadow: 0 2px 8px rgba(0,0,0,.25);
}
.kafe-card-body { padding: 13px 14px 12px; }
.kafe-card-name {
    font-family: 'Fraunces', serif; font-size: .9rem;
    font-weight: 800; color: #1C1917; margin-bottom: 3px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kafe-card-addr {
    font-size: .7rem; color: #999; margin-bottom: 5px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kafe-card-jam {
    font-size: .7rem; color: #C8502A; font-weight: 600; margin-bottom: 9px;
}
.kafe-stats {
    display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
}
.stat-pill {
    font-size: .66rem; color: #555; background: #F7F3F0;
    padding: 3px 8px; border-radius: 50px; font-weight: 500;
}
.stat-sentimen {
    margin-left: auto; background: #FFF0EB; color: #C8502A;
    font-weight: 700; font-size: .66rem;
    padding: 3px 9px; border-radius: 50px; white-space: nowrap;
}
.stat-aktif {
    font-size: .64rem; color: #1A7A3C; background: #EDFAF2;
    padding: 3px 8px; border-radius: 50px; font-weight: 600;
}
.cat-sentimen-3 {
    border-top: 1px solid #F0EAE4;
    padding: 9px 13px 12px;
    background: #FAFAF8;
}
.cat-sentimen-3-title {
    font-size: .62rem; color: #78716C; font-weight: 700;
    text-transform: uppercase; letter-spacing: .7px; margin-bottom: 7px;
}
.cat-sentimen-3-row {
    display: flex; align-items: center; gap: 5px; margin-bottom: 4px;
}
.cat-sentimen-3-badge {
    font-size: .60rem; font-weight: 700; padding: 2px 7px;
    border-radius: 50px; flex-shrink: 0; white-space: nowrap;
}
.cat-sentimen-3-text {
    font-size: .66rem; color: #44352C; line-height: 1.4; flex: 1;
}
.sk3-detail-btn > div[data-testid="stButton"] > button {
    border-radius: 0 0 14px 14px !important;
    min-height: 36px !important;
    padding: 6px 10px !important;
    font-size: .78rem !important;
    font-weight: 600 !important;
    border: 1.5px solid #E8DDD5 !important;
    border-top: none !important;
    box-shadow: none !important;
    width: 100% !important;
    margin-top: 0 !important;
}
.stats-bar {
    background: #fff; border-radius: 14px;
    border: 1.5px solid #E8DDD5;
    padding: 16px 24px; margin: 0 40px 24px;
    display: flex; align-items: center; gap: 24px; flex-wrap: wrap;
}
.stats-bar-item { text-align: center; }
.stats-bar-num {
    font-family: 'Fraunces', serif; font-size: 1.6rem;
    font-weight: 900; color: #C8502A;
}
.stats-bar-lbl { font-size: .72rem; color: #78716C; font-weight: 500; }
div[data-testid="stButton"] > button {
    background: #C8502A !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: .8rem !important;
    padding: 8px 12px !important;
    width: 100% !important;
    transition: background .18s !important;
}
div[data-testid="stButton"] > button:hover {
    background: #A33E20 !important;
}
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

# ── Navbar ─────────────────────────────────────────────────────
col_logo, col_nav = st.columns([6, 2])
with col_logo:
    st.markdown("""
<div style="padding: 13px 40px; background: #fff;">
  <div class="topbar-logo">Kafe<span>Sby</span></div>
</div>
""", unsafe_allow_html=True)
with col_nav:
    st.markdown('<div class="beranda-btn-wrap" style="display:flex; justify-content:flex-end; padding-top:8px; padding-right:40px;">', unsafe_allow_html=True)
    if st.button("← Beranda", key="btn_beranda_sk3"):
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

# ── Load data ──────────────────────────────────────────────────
# load_data() sudah membaca dari Google Sheets via gsheets_client
# cache bawaan utils_kafe.py (ttl=600) digunakan otomatis
@st.cache_data(show_spinner=False)
def get_df():
    df = load_data()
    df["skor_sentimen"] = pd.to_numeric(df["skor_sentimen"], errors="coerce").fillna(0)
    df["kafe_id"] = df["kafe_id"].astype(str)
    return df

df = get_df()

kafeid_to_nama = df.drop_duplicates("kafe_id").set_index("kafe_id")["nama_kafe"].to_dict()

# ── Precompute jumlah review per kafe (dari review_id) ──────────
@st.cache_data(show_spinner=False)
def get_jumlah_review_per_kafe_sk3(_dataframe: pd.DataFrame) -> pd.Series:
    if "review_id" in _dataframe.columns:
        return _dataframe.groupby("kafe_id")["review_id"].nunique()
    elif "review" in _dataframe.columns:
        return _dataframe.groupby("kafe_id")["review"].nunique()
    else:
        return _dataframe.groupby("kafe_id").size()

# ── Precompute persentase reviewer aktif per kafe ───────────────
@st.cache_data(show_spinner=False)
def get_reviewer_aktif_pct_sk3(_dataframe: pd.DataFrame) -> pd.Series:
    if "status_reviewer" not in _dataframe.columns or "review_id" not in _dataframe.columns:
        return pd.Series(dtype=float)
    df_dedup = _dataframe.drop_duplicates(subset=["kafe_id", "review_id"])
    total_per_kafe = df_dedup.groupby("kafe_id")["review_id"].count()
    aktif_per_kafe = df_dedup[
        df_dedup["status_reviewer"].astype(str).str.lower().str.strip() == "aktif"
    ].groupby("kafe_id")["review_id"].count()
    pct = (aktif_per_kafe / total_per_kafe * 100).fillna(0)
    return pct

_jumlah_review_map  = get_jumlah_review_per_kafe_sk3(df)
_reviewer_aktif_pct = get_reviewer_aktif_pct_sk3(df)

# ── Ambil kondisi ──────────────────────────────────────────────
params = st.query_params

cond_p = st.session_state.get("detail_cond", None)
if not cond_p:
    raw = params.get("cond", "")
    if raw:
        cond_p = unquote(raw)

if not cond_p:
    st.error("Kondisi tidak ditemukan. Silakan kembali ke beranda.")
    if st.button("← Kembali ke Beranda", key="btn_kembali_error"):
        st.switch_page(_beranda_page)
    st.stop()

# ── Hero banner ────────────────────────────────────────────────
st.markdown(f"""
<div class="result-hero">
  <div class="tag">&#128269; Hasil Pencarian</div>
  <h2>Kafe dengan kondisi<br><span>"{cond_p}"</span></h2>
  <p>Diurutkan berdasarkan skor sentimen tertinggi untuk aspek {cond_p}.</p>
</div>
""", unsafe_allow_html=True)

# ── Hitung skor Kasus A ─────────────────────────────────────────
result = compute_aspect_condition_scores_imdb(df, cond_p)

if result.empty:
    st.markdown('<div style="padding:40px 48px;">', unsafe_allow_html=True)
    st.info(f'Tidak ada kafe yang memiliki kondisi "{cond_p}" dalam dataset.')
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ── Hitung skor Kasus C per kartu ──────────────────────────────
@st.cache_data(show_spinner=False)
def get_cat_scores_sk3(kid: str) -> pd.DataFrame:
    return compute_category_scores_imdb(df, kid)


def build_cat_sentimen_html_sk3(kid: str) -> str:
    cat_df = get_cat_scores_sk3(kid)
    if cat_df.empty:
        return ""

    _cat_badge_colors = ["#C8502A", "#B8730A", "#1A6EB0", "#1A7A3C", "#7C3AED", "#BE185D"]
    _cat_badge_bgs    = ["#FFF0EB", "#FFF7E6", "#EBF5FF", "#F0FBF0", "#F5F0FF", "#FFF0F5"]
    unique_cats_list  = sorted(df["category_aspect_kafe"].dropna().unique().tolist())

    rows_html = ""
    for _, r in cat_df.iterrows():
        cat  = r["category_aspect_kafe"]
        pct  = round(float(r["sentimen_pct"]), 1)
        cidx = unique_cats_list.index(cat) % len(_cat_badge_colors) if cat in unique_cats_list else 0
        bc   = _cat_badge_colors[cidx]
        bb   = _cat_badge_bgs[cidx]
        rows_html += f"""
<div class="cat-sentimen-3-row">
  <span class="cat-sentimen-3-badge" style="background:{bb};color:{bc};">{cat}</span>
  <span class="cat-sentimen-3-text">Skor: <b style="color:{bc};">{pct:.1f}%</b></span>
</div>"""

    return f"""
<div class="cat-sentimen-3">
  <div class="cat-sentimen-3-title">&#128202; Sentimen per Kategori</div>
  {rows_html}
</div>"""


# ── Stats bar ──────────────────────────────────────────────────
top_pct = round(float(result.iloc[0]["sentimen_pct"]), 1) if len(result) else 0
avg_pct = round(float(result["sentimen_pct"].mean()), 1) if len(result) else 0
st.markdown(f"""
<div class="stats-bar" style="margin-top:0;">
  <div class="stats-bar-item">
    <div class="stats-bar-num">{len(result)}</div>
    <div class="stats-bar-lbl">Kafe Ditemukan</div>
  </div>
  <div style="width:1px;background:#E8DDD5;height:36px;"></div>
  <div class="stats-bar-item">
    <div class="stats-bar-num">{top_pct:.1f}%</div>
    <div class="stats-bar-lbl">Skor Tertinggi</div>
  </div>
  <div style="width:1px;background:#E8DDD5;height:36px;"></div>
  <div class="stats-bar-item">
    <div class="stats-bar-num">{avg_pct:.1f}%</div>
    <div class="stats-bar-lbl">Rata-rata Skor</div>
  </div>
  <div style="flex:1;text-align:right;">
    <span style="font-size:.78rem;color:#78716C;">Klik tombol detail untuk melihat info kafe &#8594;</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Grid kartu ─────────────────────────────────────────────────
RANK_COLORS = {1: "#D4A017", 2: "#8C8C8C", 3: "#A0522D"}

cols_per_row = 4
st.markdown('<div style="padding: 8px 40px 40px;">', unsafe_allow_html=True)

rows_groups = [result.iloc[i:i+cols_per_row] for i in range(0, len(result), cols_per_row)]

for row_group in rows_groups:
    n_in_row = len(row_group)
    col_ratios = (
        [1] * n_in_row + [max(1, cols_per_row - n_in_row)]
        if n_in_row < cols_per_row else [1] * n_in_row
    )
    cols = st.columns(col_ratios if n_in_row < cols_per_row else [1] * n_in_row, gap="medium")

    for col_idx, (df_idx, row) in enumerate(row_group.iterrows()):
        rank     = int(df_idx) + 1
        rank_bg  = RANK_COLORS.get(rank, "rgba(28,25,23,.65)")
        nama     = str(row.get("nama_kafe", "—"))
        alamat   = str(row.get("alamat_kafe", "—"))
        jam      = str(row.get("jam_buka", "—"))
        kid      = str(row.get("kafe_id", ""))

        sentimen_pct = float(row.get("sentimen_pct", 0))

        cover  = str(row.get("cover", ""))
        direct = gdrive_direct_url(cover)

        # Jumlah review dari review_id
        jml_rev_raw = _jumlah_review_map.get(kid, 0)
        try:
            jml_rev = f"{int(float(jml_rev_raw)):,}".replace(",", ".")
        except Exception:
            jml_rev = "—"

        # Persentase reviewer aktif
        aktif_pct_raw = _reviewer_aktif_pct.get(kid, 0.0)
        try:
            aktif_pct_val = float(aktif_pct_raw)
        except Exception:
            aktif_pct_val = 0.0
        aktif_str = f"{aktif_pct_val:.1f}%"

        if direct:
            img_html = (
                f'<img src="{direct}" alt="{nama}" '
                f'style="width:100%;height:150px;object-fit:cover;display:block;" loading="lazy" '
                f'onerror="this.style.display=\'none\';">'
            )
        else:
            img_html = '<div class="placeholder">☕</div>'

        cat_sentimen_html = build_cat_sentimen_html_sk3(kid)

        card_html = f"""
<div class="kafe-card-3">
  <div class="kafe-rank-badge" style="background:{rank_bg};">{rank}</div>
  {img_html}
  <div class="kafe-card-body">
    <div class="kafe-card-name" title="{nama}">{nama}</div>
    <div class="kafe-card-addr" title="{alamat}">&#128205; {alamat}</div>
    <div class="kafe-card-jam">&#128336; {jam}</div>
    <div class="kafe-stats">
      <span class="stat-pill">&#11088; {sentimen_pct:.1f}%</span>
      <span class="stat-pill">&#128101; {jml_rev} review</span>
      <span class="stat-aktif">&#10003; {aktif_str} aktif</span>
    </div>
  </div>
  {cat_sentimen_html}
</div>"""

        with cols[col_idx]:
            st.markdown(card_html, unsafe_allow_html=True)
            st.markdown('<div class="sk3-detail-btn">', unsafe_allow_html=True)
            if st.button(
                "Lihat Detail →",
                key=f"sk3_btn_{kid}_{rank}_{col_idx}",
                use_container_width=True
            ):
                if "detail_cond" in st.session_state:
                    del st.session_state["detail_cond"]
                st.session_state["detail_kid"]         = kid
                st.session_state["detail_nama"]        = kafeid_to_nama.get(kid, nama)
                st.session_state["detail_source"]      = "kasus_a"
                st.session_state["detail_cond_chosen"] = cond_p
                vi_score = float(row.get("Vi", 0))
                st.session_state["detail_vi_score"]    = vi_score
                st.session_state["_prev_page"] = "pages/skemacari3.py"
                st.switch_page("pages/skemacari1.py")
            st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
