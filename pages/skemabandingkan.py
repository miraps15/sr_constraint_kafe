# PERBAIKAN STREAMLIT CLOUD:
# - Hapus path lokal /content/drive → gunakan load_data() dari utils_kafe
# - Semua data dibaca via Google Sheets API (gsheets_client)
# - get_df() tidak lagi membaca .xlsx lokal, cukup panggil load_data()
# - Tidak ada perubahan fungsionalitas utama (IMDb WR + SAW, Kasus A/C)

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import json
from utils_kafe import (
    load_data,
    compute_saw_scores,                        # Kasus C: skor per kategori
    compute_overall_score,                     # Kasus A: skor keseluruhan semua kafe
    compute_top5_conditions_for_kafe_kasus_a,  # Kasus A: top-N kondisi per kafe
    compute_global_C, compute_imdb_wr, M_IMDB,
    gdrive_direct_url, COMMON_CSS
)

st.set_page_config(
    page_title="Perbandingan Kafe · KafeSby",
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
    display:flex; align-items:center; justify-content:space-between;
    padding:13px 40px; background:#fff; border-bottom:1px solid #E8DDD5;
    box-shadow:0 2px 16px rgba(28,25,23,.06);
    position:sticky; top:0; z-index:999;
}
.topbar-logo { font-family:'Fraunces',serif; font-size:1.4rem; font-weight:900; color:#1C1917; letter-spacing:-.5px; }
.topbar-logo span { color:#C8502A; }
.compare-hero {
    background: linear-gradient(135deg, #1C1917 0%, #2d1a0e 100%);
    padding: 52px 48px 44px;
}
.compare-hero .tag {
    display:inline-flex; align-items:center; gap:6px;
    background:rgba(200,80,42,.28); color:#F9A07A;
    font-size:.72rem; font-weight:700; letter-spacing:1.5px;
    text-transform:uppercase; padding:5px 14px; border-radius:50px; margin-bottom:14px;
}
.compare-hero h2 {
    font-family:'Fraunces',serif; font-size:clamp(1.6rem,3vw,2.2rem);
    font-weight:900; color:#fff; margin:0 0 8px; line-height:1.2;
}
.compare-hero h2 span { color:#F9A07A; }
.compare-hero p { font-size:.88rem; color:rgba(255,255,255,.5); margin:0; }
.narasi-wrap {
    background:#fff; border-radius:18px; border:1.5px solid #E8DDD5;
    padding:32px 36px; margin:8px 48px 40px;
}
.narasi-title {
    font-family:'Fraunces',serif; font-size:1.1rem; font-weight:800;
    color:#1C1917; margin-bottom:18px; display:flex; align-items:center; gap:8px;
}
.section-divider { border:none; border-top:1px solid #E8DDD5; margin:0; }
div[data-testid="stButton"] > button {
    background: #C8502A !important; color: #fff !important;
    border: none !important; border-radius: 10px !important;
    font-weight: 600 !important; font-size: .8rem !important;
    padding: 8px 12px !important; width: 100% !important;
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
    if st.button("← Beranda", key="btn_beranda_cmp"):
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

# ════════════════════════════════════════════════════════════════
# LOAD DATA — via Google Sheets API (utils_kafe.load_data)
# ════════════════════════════════════════════════════════════════
# PERBAIKAN: Hapus _INFERENCE_PATH dan logika os.path.exists().
# Di Streamlit Cloud tidak ada akses Google Drive lokal.
# Cukup panggil load_data() yang sudah terhubung ke Google Sheets.

@st.cache_data(show_spinner=False, ttl=600)
def get_df() -> pd.DataFrame:
    """
    Load data utama dari Google Sheets melalui utils_kafe.load_data().
    Di-cache 10 menit (ttl=600) agar tidak terlalu sering hit API.
    """
    df = load_data()
    for col in ["skor_sentimen"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["kafe_id"] = df["kafe_id"].astype(str)
    return df

df = get_df()

# ════════════════════════════════════════════════════════════════
# PRECOMPUTE reviewer aktif per kafe_id
# ════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def get_reviewer_aktif_per_kafe(_dataframe: pd.DataFrame) -> dict:
    """
    Hitung persentase reviewer aktif per kafe_id.
    Berdasarkan kombinasi kolom status_reviewer, review_id, dan kafe_id.
    """
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

_reviewer_aktif_map = get_reviewer_aktif_per_kafe(df)

# ════════════════════════════════════════════════════════════════
# Ambil nama kafe dari session_state
# ════════════════════════════════════════════════════════════════
compare_names = st.session_state.get("compare_names", [])

if not compare_names:
    st.error("Daftar kafe untuk dibandingkan tidak ditemukan. Silakan kembali ke beranda.")
    if st.button("← Kembali ke Beranda"):
        st.switch_page(_beranda_page)
    st.stop()

all_nama      = df["nama_kafe"].dropna().unique().tolist()
valid_names   = [n for n in compare_names if n in all_nama]
invalid_names = [n for n in compare_names if n not in all_nama]

if invalid_names:
    st.warning(f"Kafe tidak ditemukan: {', '.join(invalid_names)}", icon="⚠️")

if not valid_names:
    st.error("Tidak ada kafe valid untuk dibandingkan.")
    if st.button("← Kembali ke Beranda"):
        st.switch_page(_beranda_page)
    st.stop()

# ════════════════════════════════════════════════════════════════
# CACHE: SAW score per category (Kasus C) dan overall (Kasus A)
# ════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def get_saw_cat_df() -> pd.DataFrame:
    """Kasus C: skor per kategori untuk semua kafe. Wj = 1/n_cond_per_kategori."""
    return compute_saw_scores(df)

@st.cache_data(show_spinner=False)
def get_overall_df() -> pd.DataFrame:
    """Kasus A: skor Vi keseluruhan semua kafe. Wj = 1/n_cond_global."""
    return compute_overall_score(df)

saw_cat_df = get_saw_cat_df()
overall_df = get_overall_df()

_cat_badge_colors = ["#C8502A","#B8730A","#1A6EB0","#1A7A3C","#7C3AED","#BE185D"]
_cat_badge_bgs    = ["#FFF0EB","#FFF7E6","#EBF5FF","#F0FBF0","#F5F0FF","#FFF0F5"]
unique_cats_list  = sorted(df["category_aspect_kafe"].dropna().unique().tolist())

def build_cat_sentimen_desc_cmp(kid: str) -> str:
    """
    Sentimen per kategori (Kasus C) untuk kartu perbandingan.
    Wj = 1 / jumlah_cond_dalam_kategori (per kategori, independen).
    """
    sub = saw_cat_df[saw_cat_df["kafe_id"] == kid].sort_values("sentimen_pct", ascending=False)
    if sub.empty:
        return ""
    rows_html = ""
    for _, r in sub.iterrows():
        cat  = r["category_aspect_kafe"]
        pct  = round(float(r["sentimen_pct"]), 1)
        cidx = unique_cats_list.index(cat) % len(_cat_badge_colors) if cat in unique_cats_list else 0
        bc   = _cat_badge_colors[cidx]
        bb   = _cat_badge_bgs[cidx]
        rows_html += f"""
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:5px;">
            <span style="font-size:.62rem;font-weight:700;padding:2px 7px;border-radius:50px;
              flex-shrink:0;white-space:nowrap;background:{bb};color:{bc};">{cat}</span>
            <span style="font-size:.7rem;color:#44352C;line-height:1.45;flex:1;">
              Skor: <b style="color:{bc};">{pct}%</b>
            </span>
          </div>"""
    return f"""
      <div style="border-top:1px solid #F0EAE4;padding:10px 15px 14px;background:#FAFAF8;">
        <div style="font-size:.65rem;color:#78716C;font-weight:600;text-transform:uppercase;
          letter-spacing:.7px;margin-bottom:7px;">&#128202; Sentimen per Kategori</div>
        {rows_html}
      </div>"""

# ════════════════════════════════════════════════════════════════
# Hitung top-3 kondisi & overall menggunakan Rumus A (Kasus A)
# ════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def get_top3_conditions_kasus_a(names_json: str, top_n: int = 3) -> dict:
    """
    Top-N aspect_condition per kafe berdasarkan WR tertinggi (Kasus A).
    """
    names  = json.loads(names_json)
    C      = compute_global_C(df)
    result = {}

    for nama in names:
        sub_kafe = df[df["nama_kafe"] == nama].copy()
        if sub_kafe.empty:
            result[nama] = []
            continue

        all_conds = sub_kafe["aspect_condition"].dropna().unique().tolist()
        rows = []
        for cond in all_conds:
            sub_c = sub_kafe[sub_kafe["aspect_condition"] == cond]
            v_val = len(sub_c)
            R_val = float(sub_c["skor_sentimen"].mean())
            wr    = compute_imdb_wr(float(v_val), R_val, C, M_IMDB)
            rows.append({"cond": cond, "wr": wr, "pct": round(wr * 100, 1)})

        rows.sort(key=lambda x: x["wr"], reverse=True)
        result[nama] = [(r["cond"], r["pct"]) for r in rows[:top_n]]

    return result

@st.cache_data(show_spinner=False)
def get_overall_vi_per_kafe(names_json: str) -> dict:
    """Skor Vi (Kasus A, dalam %) per kafe dari overall_df."""
    names  = json.loads(names_json)
    result = {}
    for nama in names:
        sub = df[df["nama_kafe"] == nama]
        if sub.empty:
            result[nama] = 0.0
            continue
        kid = str(sub.iloc[0]["kafe_id"])
        row_o = overall_df[overall_df["kafe_id"] == kid]
        result[nama] = float(row_o.iloc[0]["sentimen_pct_all"]) if not row_o.empty else 0.0
    return result

@st.cache_data(show_spinner=False)
def get_kafeid_per_nama(names_json: str) -> dict:
    names  = json.loads(names_json)
    result = {}
    for nama in names:
        sub = df[df["nama_kafe"] == nama]
        result[nama] = str(sub.iloc[0]["kafe_id"]) if len(sub) else ""
    return result

@st.cache_data(show_spinner=False)
def get_jumlah_review_per_nama(names_json: str) -> dict:
    """Jumlah review unik per kafe berdasarkan review_id."""
    names  = json.loads(names_json)
    result = {}
    for nama in names:
        sub = df[df["nama_kafe"] == nama]
        if sub.empty:
            result[nama] = 0
            continue
        if "review_id" in sub.columns:
            result[nama] = int(sub["review_id"].nunique())
        elif "review" in sub.columns:
            result[nama] = int(sub["review"].nunique())
        else:
            result[nama] = 0
    return result

names_json  = json.dumps(sorted(valid_names))
top_conds   = get_top3_conditions_kasus_a(names_json)
overall_pct = get_overall_vi_per_kafe(names_json)
kafeid_map  = get_kafeid_per_nama(names_json)
jml_rev_map = get_jumlah_review_per_nama(names_json)

info_cols = ["kafe_id","nama_kafe","alamat_kafe","kecamatan_kafe",
             "jam_buka","cover","link_maps","link_ig","whatsapp","menu","range_harga"]
info_cols_exist = [c for c in info_cols if c in df.columns]
kafe_info = (df[info_cols_exist]
             .drop_duplicates("kafe_id")
             .set_index("nama_kafe"))

# Urutkan berdasarkan overall Vi tertinggi (Kasus A)
valid_names_sorted = sorted(valid_names, key=lambda n: overall_pct.get(n, 0), reverse=True)
nama_js_map        = {n: n.replace("'", "").replace('"', "") for n in valid_names_sorted}

# ── Hero ─────────────────────────────────────────────────────────
st.markdown(f"""
<div class="compare-hero">
  <div class="tag">&#9878; Perbandingan Kafe</div>
  <h2>Membandingkan<br><span>{len(valid_names_sorted)} Kafe Pilihanmu</span></h2>
  <p>Berdasarkan analisis sentimen dari ulasan pengunjung</p>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# Helper: bintang dari persentase Vi (Kasus A)
# ════════════════════════════════════════════════════════════════
def vi_pct_to_stars(pct: float) -> str:
    """Konversi persentase Vi (0-100) ke tampilan bintang (0-5)."""
    star_val = min(pct, 100.0) / 100.0 * 5.0
    full  = int(star_val)
    half  = 1 if (star_val - full) >= 0.5 else 0
    empty = 5 - full - half
    return "★" * full + ("½" if half else "") + "☆" * empty

# ════════════════════════════════════════════════════════════════
# Kartu perbandingan + tombol Lihat Detail dalam satu iframe
# ════════════════════════════════════════════════════════════════
RANK_COLORS = {1: "#D4A017", 2: "#8C8C8C", 3: "#A0522D"}
DOT_COLORS  = ["#C8502A", "#B8730A", "#1A6EB0"]
CARD_WIDTH  = 260
CARD_GAP    = 16

st.markdown("""
<div style="padding:32px 48px 4px;background:#fff;">
  <div style="font-family:'Fraunces',serif;font-size:1.2rem;font-weight:800;color:#1C1917;
    margin-bottom:4px;display:flex;align-items:center;gap:10px;">
    &#9878; Kartu Perbandingan
    <span style="font-size:.76rem;color:#bbb;font-weight:400;font-family:'Plus Jakarta Sans',sans-serif;">
      Geser kiri-kanan untuk melihat semua kafe
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

all_cards_html = ""
for rank, nama in enumerate(valid_names_sorted, 1):
    nama_js  = nama_js_map[nama]
    rank_bg  = RANK_COLORS.get(rank, "rgba(28,25,23,.65)")
    row_info = kafe_info.loc[nama] if nama in kafe_info.index else {}
    alamat   = str(row_info.get("alamat_kafe", "—")) if isinstance(row_info, pd.Series) else "—"
    jam      = str(row_info.get("jam_buka", "—")) if isinstance(row_info, pd.Series) else "—"
    cover    = str(row_info.get("cover", "")) if isinstance(row_info, pd.Series) else ""
    kid      = kafeid_map.get(nama, "")

    # Skor Vi dari Kasus A (sentimen_pct_all, sudah dalam %)
    vi_pct   = overall_pct.get(nama, 0.0)
    stars    = vi_pct_to_stars(vi_pct)

    # Jumlah review dari review_id
    jml_rev     = jml_rev_map.get(nama, 0)
    try:
        jml_rev_str = f"{int(jml_rev):,}".replace(",", ".")
    except Exception:
        jml_rev_str = str(jml_rev)

    # Persentase reviewer aktif per kafe_id
    rev_aktif_pct = _reviewer_aktif_map.get(kid, 0.0)
    rev_aktif_str = f"{rev_aktif_pct:.1f}%"

    direct   = gdrive_direct_url(cover)

    if direct:
        img_html = (
            f'<img src="{direct}" alt="{nama}" '
            f'style="width:100%;height:150px;object-fit:cover;display:block;flex-shrink:0;" loading="lazy" '
            f'onerror="this.style.display=\'none\';">'
        )
    else:
        img_html = (
            '<div style="width:100%;height:150px;background:#f5ede5;display:flex;'
            'align-items:center;justify-content:center;font-size:2.5rem;'
            'color:#c8a898;flex-shrink:0;">&#9749;</div>'
        )

    # Top-3 kondisi (Kasus A: WR tertinggi, bobot rata = 1/n_conds)
    top3_items = top_conds.get(nama, [])
    top3_html  = ""
    for t_idx, (cond, pct) in enumerate(top3_items):
        dot_clr    = DOT_COLORS[t_idx % len(DOT_COLORS)]
        bar_w      = min(int(pct), 100)
        cond_short = cond[:26] + ("…" if len(cond) > 26 else "")
        top3_html += f"""
          <div style="display:flex;align-items:center;gap:7px;margin-bottom:5px;">
            <div style="width:16px;height:16px;border-radius:50%;background:{dot_clr};
              display:flex;align-items:center;justify-content:center;
              font-size:.56rem;font-weight:800;color:#fff;flex-shrink:0;">{t_idx+1}</div>
            <div style="font-size:.68rem;color:#1C1917;font-weight:500;flex:1;
              min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
              title="{cond}">{cond_short}</div>
            <div style="width:50px;height:4px;background:#f0e8e3;border-radius:2px;overflow:hidden;flex-shrink:0;">
              <div style="height:4px;border-radius:2px;background:{dot_clr};width:{bar_w}%;"></div>
            </div>
            <div style="font-size:.64rem;color:{dot_clr};font-weight:700;min-width:30px;text-align:right;">{pct:.0f}%</div>
          </div>"""

    # Sentimen per kategori (Kasus C: Wj = 1/n_cond_per_kategori)
    cat_desc = build_cat_sentimen_desc_cmp(kid)

    nama_short   = nama[:28] + ("…" if len(nama) > 28 else "")
    alamat_short = alamat[:32] + ("…" if len(alamat) > 32 else "")

    all_cards_html += f"""
    <div style="width:{CARD_WIDTH}px;min-width:{CARD_WIDTH}px;max-width:{CARD_WIDTH}px;
      flex-shrink:0;display:flex;flex-direction:column;">
      <!-- KARTU -->
      <div style="background:#fff;
        border-radius:18px 18px 0 0;
        border:1.5px solid #E8DDD5;border-bottom:none;
        overflow:hidden;position:relative;
        flex:1;display:flex;flex-direction:column;">
        <div style="position:absolute;top:10px;left:10px;width:28px;height:28px;
          border-radius:50%;background:{rank_bg};display:flex;align-items:center;
          justify-content:center;font-size:.7rem;font-weight:800;color:#fff;
          z-index:2;box-shadow:0 2px 8px rgba(0,0,0,.25);">{rank}</div>
        {img_html}
        <div style="padding:13px 14px 8px;flex:1;">
          <div style="font-family:'Fraunces',serif;font-size:.88rem;font-weight:800;
            color:#1C1917;margin-bottom:3px;white-space:nowrap;overflow:hidden;
            text-overflow:ellipsis;" title="{nama}">{nama_short}</div>
          <div style="font-size:.68rem;color:#999;margin-bottom:4px;white-space:nowrap;
            overflow:hidden;text-overflow:ellipsis;" title="{alamat}">&#128205; {alamat_short}</div>
          <div style="font-size:.68rem;color:#C8502A;font-weight:600;margin-bottom:6px;">&#128336; {jam}</div>
          <!-- Skor Vi (Kasus A) dalam bentuk bintang -->
          <div style="font-size:.72rem;color:#C8502A;font-weight:700;margin-bottom:5px;">
            Skor: {stars} ({vi_pct:.1f}%)
          </div>
          <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin-bottom:9px;">
            <span style="font-size:.62rem;color:#555;background:#F7F3F0;padding:2px 7px;border-radius:50px;font-weight:500;">&#128101; {jml_rev_str} review</span>
            <span style="font-size:.62rem;color:#1A7A3C;background:#EDFAF2;padding:2px 7px;border-radius:50px;font-weight:500;">&#9989; {rev_aktif_str} aktif</span>
          </div>
        </div>
        <div style="border-top:1px solid #F0EAE4;padding:9px 14px 11px;">
          <div style="font-size:.64rem;color:#78716C;font-weight:600;text-transform:uppercase;letter-spacing:.7px;margin-bottom:7px;">&#127942; Top 3 Kondisi Terbaik</div>
          {top3_html if top3_html else '<div style="font-size:.72rem;color:#bbb;font-style:italic;">Tidak ada data</div>'}
        </div>
        {cat_desc}
      </div>
      <!-- TOMBOL LIHAT DETAIL → skemacari1 dengan kasus_a -->
      <button
        onclick="navigateToDetail('{kid}', '{nama_js}')"
        style="width:100%;padding:10px 8px;
          background:#C8502A;color:#fff;
          border:1.5px solid #C8502A;border-top:none;
          border-radius:0 0 18px 18px;
          font-size:.78rem;font-weight:700;
          font-family:'Plus Jakarta Sans',sans-serif;
          cursor:pointer;letter-spacing:.3px;
          transition:background .18s;
          display:block;box-sizing:border-box;"
        onmouseover="this.style.background='#A33E20';this.style.borderColor='#A33E20';"
        onmouseout="this.style.background='#C8502A';this.style.borderColor='#C8502A';">
        Lihat Detail &#8594;
      </button>
    </div>"""

scroll_h    = 580
scroll_html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: 'Plus Jakarta Sans', sans-serif;
  background: transparent;
  overflow: hidden;
}}
.scroll-outer {{
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 12px;
  cursor: grab;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
  scrollbar-color: #C8502A #F0EAE4;
}}
.scroll-outer:active {{ cursor: grabbing; }}
.scroll-outer::-webkit-scrollbar {{ height: 5px; }}
.scroll-outer::-webkit-scrollbar-track {{ background: #F0EAE4; border-radius: 3px; }}
.scroll-outer::-webkit-scrollbar-thumb {{ background: #C8502A; border-radius: 3px; }}
.scroll-inner {{
  display: flex;
  flex-direction: row;
  gap: {CARD_GAP}px;
  align-items: flex-start;
  width: max-content;
  padding-bottom: 4px;
}}
</style>
</head><body>
<div class="scroll-outer" id="scrollOuter">
  <div class="scroll-inner">
    {all_cards_html}
  </div>
</div>
<script>
var el = document.getElementById('scrollOuter');
var isDown = false, startX, scrollLeft;
el.addEventListener('mousedown', function(e) {{
  isDown = true; startX = e.pageX - el.offsetLeft; scrollLeft = el.scrollLeft;
}});
el.addEventListener('mouseleave', function() {{ isDown = false; }});
el.addEventListener('mouseup', function() {{ isDown = false; }});
el.addEventListener('mousemove', function(e) {{
  if (!isDown) return;
  e.preventDefault();
  var x = e.pageX - el.offsetLeft;
  el.scrollLeft = scrollLeft - (x - startX);
}});

function navigateToDetail(kid, nama) {{
  try {{
    var parentUrl  = window.parent.location.href;
    var baseUrl    = parentUrl.split('?')[0].replace(/\\/[^\\/]*$/, '');
    var url        = baseUrl + '/skemacari1?kid=' + encodeURIComponent(kid)
                             + '&nama=' + encodeURIComponent(nama)
                             + '&source=kasus_a';
    window.open(url, '_blank');
  }} catch(e) {{
    window.open('/skemacari1?kid=' + encodeURIComponent(kid)
                + '&nama=' + encodeURIComponent(nama)
                + '&source=kasus_a', '_blank');
  }}
}}
</script>
</body></html>"""

st.markdown('<div style="padding:0 48px 28px;background:#fff;">', unsafe_allow_html=True)
components.html(scroll_html, height=scroll_h, scrolling=False)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<hr style="border:none;border-top:1px solid #E8DDD5;margin:0;">', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# NARASI OTOMATIS
# ════════════════════════════════════════════════════════════════
def build_narasi(names_sorted: list, top_conds_map: dict, pct_map: dict) -> str:
    if not names_sorted:
        return ""
    paragraphs = []
    best_kafe  = names_sorted[0]
    best_pct   = pct_map.get(best_kafe, 0)
    best_conds = [c for c, _ in top_conds_map.get(best_kafe, [])]
    if best_conds:
        conds_str = ", ".join(
            f"<span style='font-style:italic;color:#5B4035;'>{c}</span>" for c in best_conds
        )
        paragraphs.append(
            f"Hasil perbandingan menunjukkan bahwa "
            f"<span style='color:#C8502A;font-weight:700;'>{best_kafe}</span> "
            f"memiliki tingkat kepuasan pelanggan tertinggi dengan skor sentimen "
            f"<b>{best_pct:.1f}%</b>, terutama unggul dalam hal {conds_str}."
        )
    else:
        paragraphs.append(
            f"<span style='color:#C8502A;font-weight:700;'>{best_kafe}</span> "
            f"memiliki skor sentimen tertinggi sebesar <b>{best_pct:.1f}%</b>."
        )
    for nama in names_sorted[1:]:
        pct   = pct_map.get(nama, 0)
        conds = [c for c, _ in top_conds_map.get(nama, [])]
        if conds:
            conds_str = ", ".join(
                f"<span style='font-style:italic;color:#5B4035;'>{c}</span>" for c in conds
            )
            diff   = round(best_pct - pct, 1)
            prefix = "Sementara itu" if diff <= 5 else "Sedangkan"
            suffix = (f"dengan skor sentimen yang hampir setara, yaitu <b>{pct:.1f}%</b>"
                      if diff <= 5 else f"dengan skor sentimen <b>{pct:.1f}%</b>")
            paragraphs.append(
                f"{prefix}, <span style='color:#C8502A;font-weight:700;'>{nama}</span> "
                f"menunjukkan keunggulan dalam hal {conds_str} {suffix}."
            )
        else:
            paragraphs.append(
                f"<span style='color:#C8502A;font-weight:700;'>{nama}</span> "
                f"memiliki skor sentimen <b>{pct:.1f}%</b>."
            )
    if len(names_sorted) >= 2:
        all_mention = " dan ".join(
            f"<span style='color:#C8502A;font-weight:700;'>{n}</span>" for n in names_sorted
        )
        paragraphs.append(
            f"Secara keseluruhan, perbandingan antara {all_mention} "
            f"dapat menjadi pertimbangan dalam memilih kafe yang paling sesuai "
            f"dengan preferensi dan kebutuhan kamu."
        )
    return " ".join(paragraphs)

narasi_html = build_narasi(valid_names_sorted, top_conds, overall_pct)

st.markdown(f"""
<div class="narasi-wrap">
  <div class="narasi-title">&#128203; Hasil Analisis Perbandingan</div>
  <div style="font-size:.9rem;color:#44352C;line-height:1.75;">{narasi_html}</div>
</div>
""", unsafe_allow_html=True)
