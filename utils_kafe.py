# ============================================================
# Versi Streamlit Cloud
# Perubahan dari versi Colab:
#   - load_data()    → membaca dari Google Sheets via gsheets_client
#   - Tidak ada lagi path /content/drive atau file .xlsx lokal
#   - Semua logika IMDb WR + SAW tidak diubah
# ============================================================

import pandas as pd
import numpy as np
import streamlit as st

from gsheets_client import read_sheet_as_df

M_IMDB = 13  # threshold minimum untuk IMDb Weighted Rating


# ─── LOAD DATA ───────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=600)
def load_data() -> pd.DataFrame:
    """
    Baca df_inference_kafe dari Google Sheets.
    Di-cache selama 10 menit (ttl=600) agar tidak terlalu sering hit API.
    Fallback ke dummy data jika akses API gagal (misal saat development lokal).
    """
    try:
        df = read_sheet_as_df("df_inference_kafe")
        if df.empty:
            raise ValueError("Sheet kosong, gunakan dummy data.")
        # Normalisasi nama kolom
        if "skor sentimen" in df.columns and "skor_sentimen" not in df.columns:
            df = df.rename(columns={"skor sentimen": "skor_sentimen"})
        # Pastikan tipe numerik
        df["skor_sentimen"] = pd.to_numeric(df.get("skor_sentimen", 0), errors="coerce").fillna(0)
        df["kafe_id"]       = df["kafe_id"].astype(str)
        return df
    except Exception as e:
        # Fallback: tampilkan warning dan gunakan dummy data
        import streamlit as _st
        _st.warning(
            f"⚠️ Gagal membaca Google Sheets ({e}). Menggunakan data contoh.",
            icon="⚠️"
        )
        return _build_dummy_data()


def _build_dummy_data() -> pd.DataFrame:
    """Data dummy untuk development / fallback."""
    cat_condition_map = {
        "food": {
            "food taste":    ["makanan enak","rasa pas","cita rasa khas"],
            "food portion":  ["porsi banyak","porsi cukup","porsi kecil"],
            "food quality":  ["bahan segar","kualitas baik","tidak basi"],
            "beverage":      ["kopi enak","minuman segar","banyak pilihan"],
        },
        "service": {
            "staff behavior":["pelayan ramah","staff helpful","respon cepat"],
            "waiting time":  ["tidak lama nunggu","antrian teratur"],
            "prayer room":   ["ada mushola","fasilitas ibadah"],
        },
        "ambience": {
            "atmosphere":      ["suasana nyaman","tempat tenang","enak buat kerja"],
            "cleanliness":     ["toilet bersih","meja bersih","area rapi"],
            "interior design": ["interior keren","dekorasi unik","estetik"],
            "noise level":     ["tidak berisik","suara oke"],
            "parking":         ["parkir luas","mudah parkir"],
        },
        "price": {
            "value for money":      ["harga worth it","sebanding kualitas"],
            "price affordability":  ["harga terjangkau","murah meriah"],
        },
    }
    np.random.seed(42)
    nama_list = [
        "Arung Senja","Titik Kumpul","Rempah Nusantara","Kopi Langit",
        "Ruang Teduh","Senja & Cerita","Kopilandia","Warung Rasa",
        "Sudut Cerah","Kopi Susu Dua","Dapur Nostalgia","Loka Kopi",
        "Lereng Hijau","Pintu Kayu","Bukit Kafein","Sore Indah",
        "Gelas Kenangan","Awan Putih","Bumi Kopi","Mentari Pagi",
    ]
    jalan           = ["Darmo","Basuki Rahmat","Raya Gubeng","Pemuda","HR Muhammad"]
    kecamatan_list  = ["Wonokromo","Gubeng","Jambangan","Mulyorejo","Rungkut",
                       "Sukolilo","Tambaksari","Sawahan","Tegalsari","Genteng"]
    reviews_pool    = [
        "Tempatnya nyaman banget, cocok buat kerja.",
        "Kopinya enak tapi pelayanan agak lambat.",
        "Suasana tenang, harga oke. Recommended!",
        "Interior keren, foto-fotoan seru di sini.",
        "Makanannya lezat, porsinya juga cukup besar.",
        "Staf ramah dan cekatan, pasti balik lagi.",
        "Harga sedikit mahal tapi worth it banget.",
        "Parkir susah tapi tempatnya bagus.",
    ]
    rows = []
    for i, nama in enumerate(nama_list):
        kid    = str(i + 1)
        kec    = kecamatan_list[i % len(kecamatan_list)]
        alamat = f"Jl. {jalan[i%5]} No.{10+i*3}, {kec}, Surabaya"
        jam    = f"{np.random.randint(7,10):02d}.00 - {np.random.randint(20,23):02d}.00"
        jml_r  = int(np.random.randint(200, 4500))
        rat    = round(float(np.random.uniform(3.8, 5.0)), 1)
        hlo    = np.random.randint(15, 30) * 1000
        hhi    = np.random.randint(50, 90) * 1000
        wa     = f"https://wa.me/628{np.random.randint(10000000,99999999)}"
        ig     = f"https://instagram.com/{nama.lower().replace(' ','_').replace('&','dan')}"
        maps   = f"https://maps.google.com/?q={nama.replace(' ','+')}+Surabaya"
        rid    = 1
        for cat, term_cond in cat_condition_map.items():
            for term, conditions in term_cond.items():
                n_rev = np.random.randint(3, 9)
                for _ in range(n_rev):
                    cond = np.random.choice(conditions)
                    sent = np.random.choice(["positive","negative"], p=[0.72,0.28])
                    rows.append({
                        "kafe_id": kid, "nama_kafe": nama,
                        "status_jumlah_ulasan_user": f"Local Guide · {np.random.randint(1,120)} ulasan",
                        "waktu": "2 hari lalu",
                        "alamat_kafe": alamat,
                        "kecamatan_kafe": kec,
                        "review_id": f"{rid}",
                        "review": reviews_pool[np.random.randint(0, len(reviews_pool))],
                        "aspect_term": term.split()[0],
                        "category_aspect_term": term,
                        "category_aspect_kafe": cat,
                        "aspect_condition": cond,
                        "sentimen": sent,
                        "confidence": f"{np.random.randint(70,100)}%",
                        "skor_sentimen": 1 if sent=="positive" else 0,
                        "jumlah_rating": jml_r, "rating_maps": rat,
                        "link_maps": maps, "link_ig": ig, "jam_buka": jam,
                        "whatsapp": wa,
                        "menu": "https://drive.google.com/file/d/DEMO/view",
                        "range_harga": f"Rp {hlo:,} - Rp {hhi:,}".replace(",","."),
                        "cover": "", "slide_1": "", "slide_2": "",
                    })
                    rid += 1
    return pd.DataFrame(rows)


# ─── ENGINE: IMDb Weighted Rating + SAW (RUMUS A) ────────────────────────────
def compute_global_C(dataframe: pd.DataFrame) -> float:
    total_pos = dataframe["skor_sentimen"].sum()
    total_v   = len(dataframe)
    return float(total_pos / total_v) if total_v > 0 else 0.5


def compute_imdb_wr(v: float, R: float, C: float, m: int = M_IMDB) -> float:
    return (v / (m + v)) * R + (m / (m + v)) * C


def _get_jumlah_review(dataframe: pd.DataFrame) -> pd.Series:
    if "review_id" in dataframe.columns:
        return dataframe.groupby("kafe_id")["review_id"].nunique().rename("jumlah_review")
    elif "review" in dataframe.columns:
        return dataframe.groupby("kafe_id")["review"].nunique().rename("jumlah_review")
    else:
        return dataframe.groupby("kafe_id")["jumlah_rating"].first().rename("jumlah_review")


def _merge_info(result: pd.DataFrame, dataframe: pd.DataFrame) -> pd.DataFrame:
    info_cols = ["kafe_id","nama_kafe","alamat_kafe","kecamatan_kafe","jam_buka",
                 "jumlah_rating","rating_maps","cover","link_maps","link_ig",
                 "whatsapp","menu","range_harga"]
    ic_exist = [c for c in info_cols if c in dataframe.columns]
    info     = dataframe[ic_exist].drop_duplicates("kafe_id")
    jml_rev  = _get_jumlah_review(dataframe)

    result = result.merge(info, on="kafe_id", how="left")
    result = result.merge(jml_rev.reset_index(), on="kafe_id", how="left")
    result["jumlah_review"] = result["jumlah_review"].fillna(
        result.get("jumlah_rating", pd.Series(0, index=result.index))
    ).astype(int)
    return result


# ─── KASUS A ──────────────────────────────────────────────────
def compute_aspect_condition_scores_imdb(dataframe: pd.DataFrame,
                                          condition: str) -> pd.DataFrame:
    sub = dataframe[dataframe["aspect_condition"] == condition].copy()
    if sub.empty:
        return pd.DataFrame()

    C   = compute_global_C(dataframe)
    grp = sub.groupby("kafe_id")
    r_i = grp["skor_sentimen"].mean().rename("R")
    v_i = grp["skor_sentimen"].count().rename("v")
    base = pd.concat([r_i, v_i], axis=1).reset_index()

    base["WR"]  = base.apply(
        lambda row: compute_imdb_wr(float(row["v"]), float(row["R"]), C, M_IMDB), axis=1)
    max_wr      = base["WR"].max()
    base["Rij"] = base["WR"] / (max_wr if max_wr > 0 else 1e-9)
    base["Vi"]  = base["Rij"]
    base["sentimen_pct"] = (base["Vi"] * 100).round(1)

    result = _merge_info(base, dataframe)
    return result.sort_values("Vi", ascending=False).reset_index(drop=True)


def compute_top5_conditions_for_kafe_kasus_a(dataframe: pd.DataFrame,
                                              kid: str) -> pd.DataFrame:
    C        = compute_global_C(dataframe)
    sub_kafe = dataframe[dataframe["kafe_id"] == kid]
    if sub_kafe.empty:
        return pd.DataFrame()

    all_conds = sub_kafe["aspect_condition"].dropna().unique().tolist()
    rows = []
    for cond in all_conds:
        sub_c = sub_kafe[sub_kafe["aspect_condition"] == cond]
        v_val = len(sub_c)
        R_val = sub_c["skor_sentimen"].mean()
        wr    = compute_imdb_wr(float(v_val), float(R_val), C, M_IMDB)
        rows.append({"aspect_condition": cond, "v": v_val,
                     "R": round(R_val, 4), "WR": round(wr, 4),
                     "sentimen_pct": round(wr * 100, 1)})
    if not rows:
        return pd.DataFrame()
    return (pd.DataFrame(rows)
              .sort_values("WR", ascending=False)
              .head(5)
              .reset_index(drop=True))


# ─── KASUS B ──────────────────────────────────────────────────
def compute_location_scores_imdb(dataframe: pd.DataFrame) -> pd.DataFrame:
    C         = compute_global_C(dataframe)
    all_conds = dataframe["aspect_condition"].dropna().unique().tolist()
    all_kids  = dataframe["kafe_id"].unique().tolist()
    if not all_conds:
        return pd.DataFrame()

    n_conds = len(all_conds)
    wj      = 1.0 / n_conds
    wr_matrix       = {}
    max_wr_per_cond = {}

    for cond in all_conds:
        sub_cond = dataframe[dataframe["aspect_condition"] == cond]
        grp  = sub_cond.groupby("kafe_id")
        r_i  = grp["skor_sentimen"].mean()
        v_i  = grp["skor_sentimen"].count()
        max_wr = 0.0
        for kid in r_i.index:
            wr = compute_imdb_wr(float(v_i[kid]), float(r_i[kid]), C, M_IMDB)
            wr_matrix[(kid, cond)] = wr
            if wr > max_wr:
                max_wr = wr
        max_wr_per_cond[cond] = max_wr if max_wr > 0 else 1e-9

    records = []
    for kid in all_kids:
        vi     = 0.0
        detail = {}
        for cond in all_conds:
            wr  = wr_matrix.get((kid, cond), 0.0)
            rij = wr / max_wr_per_cond[cond]
            vi += wj * rij
            detail[cond] = round(wr * 100, 1)
        rec = {"kafe_id": kid, "Vi": round(vi, 4)}
        rec.update({f"d_{c}": v for c, v in detail.items()})
        records.append(rec)

    result_df = pd.DataFrame(records)
    result_df = _merge_info(result_df, dataframe)
    return result_df.sort_values("Vi", ascending=False).reset_index(drop=True)


# ─── KASUS D ──────────────────────────────────────────────────
def compute_preference_scores_imdb(dataframe: pd.DataFrame,
                                    pref_items: list,
                                    bobot_final: dict) -> pd.DataFrame:
    C = compute_global_C(dataframe)
    if not pref_items:
        return compute_location_scores_imdb(dataframe)

    valid_kids = None
    for cond in pref_items:
        kids_cond  = set(dataframe[dataframe["aspect_condition"] == cond]["kafe_id"].unique())
        valid_kids = kids_cond if valid_kids is None else valid_kids & kids_cond
    kids = list(valid_kids) if valid_kids else []
    if not kids:
        return pd.DataFrame()

    sub_all         = dataframe[dataframe["kafe_id"].isin(kids)].copy()
    wr_records      = {}
    max_wr_per_cond = {}

    for cond in pref_items:
        sub_cond = sub_all[sub_all["aspect_condition"] == cond]
        grp  = sub_cond.groupby("kafe_id")
        r_i  = grp["skor_sentimen"].mean()
        v_i  = grp["skor_sentimen"].count()
        wr_series = {}
        for kid in kids:
            wr = compute_imdb_wr(float(v_i[kid]), float(r_i[kid]), C, M_IMDB) \
                 if kid in r_i.index else 0.0
            wr_series[kid]          = wr
            wr_records[(kid, cond)] = wr
        max_wr_per_cond[cond] = max(wr_series.values()) if wr_series else 1e-9

    records = []
    for kid in kids:
        vi     = 0.0
        detail = {}
        for cond in pref_items:
            wr     = wr_records.get((kid, cond), 0.0)
            max_wr = max_wr_per_cond.get(cond, 1e-9)
            rij    = wr / max_wr if max_wr > 0 else 0.0
            wj     = bobot_final.get(cond, 1.0 / len(pref_items))
            vi    += wj * rij
            detail[cond] = round(wr * 100, 1)
        rec = {"kafe_id": kid, "Vi": round(vi, 4)}
        rec.update({f"d_{c}": v for c, v in detail.items()})
        records.append(rec)

    result_df = pd.DataFrame(records)
    result_df = _merge_info(result_df, dataframe)
    return result_df.sort_values("Vi", ascending=False).reset_index(drop=True)


# ─── KASUS C ──────────────────────────────────────────────────
def compute_category_scores_imdb(dataframe: pd.DataFrame, kid: str) -> pd.DataFrame:
    C         = compute_global_C(dataframe)
    all_conds = dataframe["aspect_condition"].dropna().unique().tolist()
    sub_kafe  = dataframe[dataframe["kafe_id"] == kid]

    cond_cat_map = (dataframe[["aspect_condition","category_aspect_kafe"]]
                    .drop_duplicates()
                    .set_index("aspect_condition")["category_aspect_kafe"]
                    .to_dict())
    cat_conds = {}
    for cond in all_conds:
        cat = cond_cat_map.get(cond, "unknown")
        cat_conds.setdefault(cat, []).append(cond)

    max_wr_per_cond = {}
    wr_all = {}
    for cond in all_conds:
        sub_cond = dataframe[dataframe["aspect_condition"] == cond]
        grp  = sub_cond.groupby("kafe_id")
        r_i  = grp["skor_sentimen"].mean()
        v_i  = grp["skor_sentimen"].count()
        max_wr = 0.0
        for k in r_i.index:
            wr = compute_imdb_wr(float(v_i[k]), float(r_i[k]), C, M_IMDB)
            wr_all[(k, cond)] = wr
            if wr > max_wr:
                max_wr = wr
        max_wr_per_cond[cond] = max_wr if max_wr > 0 else 1e-9

    kafe_conds = set(sub_kafe["aspect_condition"].unique())
    cond_rij   = {}
    for cond in all_conds:
        if cond in kafe_conds:
            wr  = wr_all.get((kid, cond), 0.0)
            rij = wr / max_wr_per_cond[cond]
        else:
            rij = 0.0
        cond_rij[cond] = rij

    results = []
    for cat, conds_in_cat in cat_conds.items():
        n_conds = len(conds_in_cat)
        wj      = 1.0 / n_conds if n_conds > 0 else 1.0
        v_cat   = sum(wj * cond_rij.get(cond, 0.0) for cond in conds_in_cat)
        results.append({"category_aspect_kafe": cat,
                        "saw_score":    round(v_cat, 4),
                        "sentimen_pct": round(v_cat * 100, 1)})
    return pd.DataFrame(results).sort_values("sentimen_pct", ascending=False)


# ─── KASUS E ──────────────────────────────────────────────────
def compute_best_per_category_imdb(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    [PATCH-2] Tambah early-exit guard dan vectorized WR calculation.
    Logika ranking tidak berubah.
    """
    import pandas as _pd
 
    if dataframe.empty:
        return _pd.DataFrame()
 
    C           = compute_global_C(dataframe)
    unique_cats = dataframe["category_aspect_kafe"].dropna().unique().tolist()
 
    if not unique_cats:
        return _pd.DataFrame()
 
    jml_rev = _get_jumlah_review(dataframe)
 
    # Hitung WR sekali untuk semua (kid, cond) — vectorized
    m    = M_IMDB
    grp  = dataframe.groupby(["kafe_id", "aspect_condition", "category_aspect_kafe"])
    stats = _pd.concat([
        grp["skor_sentimen"].mean().rename("R"),
        grp["skor_sentimen"].count().rename("v"),
    ], axis=1).reset_index()
 
    stats["WR"] = (stats["v"] / (m + stats["v"])) * stats["R"] + \
                  (m / (m + stats["v"])) * C
 
    all_records = []
    for cat in unique_cats:
        sub_cat = stats[stats["category_aspect_kafe"] == cat].copy()
        if sub_cat.empty:
            continue
 
        all_conds_cat  = sub_cat["aspect_condition"].unique().tolist()
        n_conds        = len(all_conds_cat)
        if n_conds == 0:
            continue
        wj = 1.0 / n_conds
 
        # Normalisasi per kondisi
        max_wr = sub_cat.groupby("aspect_condition")["WR"].max().rename("max_WR")
        sub_cat = sub_cat.merge(max_wr.reset_index(), on="aspect_condition", how="left")
        sub_cat["max_WR"]  = sub_cat["max_WR"].replace(0, 1e-9)
        sub_cat["Rij"]     = sub_cat["WR"] / sub_cat["max_WR"]
        sub_cat["weighted"] = wj * sub_cat["Rij"]
 
        vi_series = sub_cat.groupby("kafe_id")["weighted"].sum()
 
        for kid, vi in vi_series.items():
            all_records.append({
                "kafe_id"              : kid,
                "category_aspect_kafe" : cat,
                "saw_score"            : round(float(vi), 4),
                "sentimen_pct"         : round(float(vi) * 100, 1),
            })
 
    if not all_records:
        return _pd.DataFrame()
 
    result = _pd.DataFrame(all_records)
 
    info_cols = ["kafe_id", "nama_kafe", "alamat_kafe", "kecamatan_kafe", "jam_buka",
                 "cover", "link_maps", "link_ig", "whatsapp", "menu", "range_harga"]
    ic_exist  = [c for c in info_cols if c in dataframe.columns]
    info      = dataframe[ic_exist].drop_duplicates("kafe_id")
 
    result = result.merge(info, on="kafe_id", how="left")
    result = result.merge(jml_rev.reset_index(), on="kafe_id", how="left")
    result["jumlah_review"] = result["jumlah_review"].fillna(0).astype(int)
 
    return result.sort_values(
        ["category_aspect_kafe", "saw_score"], ascending=[True, False]
    )


def precompute_top5_conditions_imdb(dataframe: pd.DataFrame) -> dict:
    """
    Versi hemat memory: simpan list of tuple, bukan DataFrame.
    Key: (kid, cat) → list of (aspect_condition, sentimen_pct)
    """
    import pandas as _pd

    if dataframe.empty:
        return {}

    C = compute_global_C(dataframe)
    m = M_IMDB

    # Hitung WR vectorized sekali
    grp = dataframe.groupby(["kafe_id", "aspect_condition"])
    stats = _pd.concat([
        grp["skor_sentimen"].mean().rename("R"),
        grp["skor_sentimen"].count().rename("v"),
    ], axis=1).reset_index()

    stats["WR"] = (stats["v"] / (m + stats["v"])) * stats["R"] + \
                  (m / (m + stats["v"])) * C
    stats["sentimen_pct"] = (stats["WR"] * 100).round(1)

    # Merge category
    cat_map = (
        dataframe[["aspect_condition", "category_aspect_kafe"]]
        .drop_duplicates()
    )
    stats = stats.merge(cat_map, on="aspect_condition", how="left")

    result = {}
    for (kid, cat), grp_df in stats.groupby(["kafe_id", "category_aspect_kafe"]):
        top5 = (
            grp_df.nlargest(5, "WR")[["aspect_condition", "sentimen_pct"]]
            .values.tolist()  # simpan sebagai list of list, BUKAN DataFrame
        )
        if top5:
            result[(kid, cat)] = top5  # [(cond, pct), ...]

    return result

# ─── KASUS A: skor keseluruhan satu kafe ──────────────────────
def compute_overall_score(dataframe: pd.DataFrame) -> pd.DataFrame:
    C = compute_global_C(dataframe)
    m = M_IMDB

    # Vectorized: hitung WR semua (kid, cond) sekaligus
    grp = dataframe.groupby(["kafe_id", "aspect_condition"])
    stats = pd.concat([
        grp["skor_sentimen"].mean().rename("R"),
        grp["skor_sentimen"].count().rename("v"),
    ], axis=1).reset_index()

    stats["WR"] = (stats["v"] / (m + stats["v"])) * stats["R"] + \
                  (m / (m + stats["v"])) * C

    # Normalisasi per kondisi
    max_wr = stats.groupby("aspect_condition")["WR"].max().rename("max_WR")
    stats  = stats.merge(max_wr.reset_index(), on="aspect_condition", how="left")
    stats["max_WR"] = stats["max_WR"].replace(0, 1e-9)
    stats["Rij"]    = stats["WR"] / stats["max_WR"]

    # Bobot rata: 1 / jumlah kondisi unik global
    n_conds = stats["aspect_condition"].nunique()
    wj      = 1.0 / n_conds if n_conds > 0 else 1.0

    # Vi per kafe
    vi_df = (stats.groupby("kafe_id")["Rij"]
               .sum()
               .mul(wj)
               .reset_index()
               .rename(columns={"Rij": "overall_score"}))
    vi_df["sentimen_pct_all"] = (vi_df["overall_score"] * 100).round(1)

    return vi_df

# ─── compute_saw_scores: Kasus C semua kafe ───────────────────
def compute_saw_scores(dataframe: pd.DataFrame) -> pd.DataFrame:
    C = compute_global_C(dataframe)
    m = M_IMDB

    # Vectorized WR
    grp = dataframe.groupby(["kafe_id", "aspect_condition"])
    stats = pd.concat([
        grp["skor_sentimen"].mean().rename("R"),
        grp["skor_sentimen"].count().rename("v"),
    ], axis=1).reset_index()

    stats["WR"] = (stats["v"] / (m + stats["v"])) * stats["R"] + \
                  (m / (m + stats["v"])) * C

    # Merge category
    cat_map = (dataframe[["aspect_condition", "category_aspect_kafe"]]
               .drop_duplicates())
    stats = stats.merge(cat_map, on="aspect_condition", how="left")

    # Max WR per kondisi (untuk normalisasi)
    max_wr = stats.groupby("aspect_condition")["WR"].max().rename("max_WR")
    stats  = stats.merge(max_wr.reset_index(), on="aspect_condition", how="left")
    stats["max_WR"] = stats["max_WR"].replace(0, 1e-9)
    stats["Rij"]    = stats["WR"] / stats["max_WR"]

    # Bobot per kategori: 1 / jumlah kondisi dalam kategori
    n_cond_per_cat = (stats.groupby("category_aspect_kafe")["aspect_condition"]
                      .nunique().rename("n_conds"))
    stats = stats.merge(n_cond_per_cat.reset_index(), on="category_aspect_kafe", how="left")
    stats["wj"]      = 1.0 / stats["n_conds"].replace(0, 1.0)
    stats["weighted"] = stats["wj"] * stats["Rij"]

    # Vi per (kafe, kategori)
    result = (stats.groupby(["kafe_id", "category_aspect_kafe"])["weighted"]
              .sum()
              .reset_index()
              .rename(columns={"weighted": "saw_score"}))
    result["sentimen_pct"] = (result["saw_score"] * 100).round(1)

    return result.sort_values(["kafe_id", "sentimen_pct"], ascending=[True, False])


# ─── compute_overall_score: Kasus A semua kafe ────────────────
def compute_overall_score(dataframe: pd.DataFrame) -> pd.DataFrame:
    C         = compute_global_C(dataframe)
    all_conds = dataframe["aspect_condition"].dropna().unique().tolist()
    all_kids  = dataframe["kafe_id"].unique().tolist()
    if not all_conds:
        return pd.DataFrame(columns=["kafe_id","overall_score","sentimen_pct_all"])

    n_conds         = len(all_conds)
    wj              = 1.0 / n_conds
    max_wr_per_cond = {}
    wr_matrix       = {}

    for cond in all_conds:
        sub_cond = dataframe[dataframe["aspect_condition"] == cond]
        grp  = sub_cond.groupby("kafe_id")
        r_i  = grp["skor_sentimen"].mean()
        v_i  = grp["skor_sentimen"].count()
        max_wr = 0.0
        for k in r_i.index:
            wr = compute_imdb_wr(float(v_i[k]), float(r_i[k]), C, M_IMDB)
            wr_matrix[(k, cond)] = wr
            if wr > max_wr:
                max_wr = wr
        max_wr_per_cond[cond] = max_wr if max_wr > 0 else 1e-9

    records = []
    for kid in all_kids:
        vi = 0.0
        for cond in all_conds:
            wr  = wr_matrix.get((kid, cond), 0.0)
            rij = wr / max_wr_per_cond[cond]
            vi += wj * rij
        records.append({"kafe_id":          kid,
                         "overall_score":    round(vi, 4),
                         "sentimen_pct_all": round(vi * 100, 1)})
    return pd.DataFrame(records)


# ─── HELPER: GDrive direct URL ───────────────────────────────
def gdrive_direct_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return ""
    url = url.strip()
    if not url or url.lower() in ["nan","none",""]:
        return ""
    if "drive.google.com" not in url:
        return url if url.startswith("http") else ""
    if "uc?" in url and "id=" in url:
        try:
            fid = url.split("id=")[1].split("&")[0]
            return f"https://lh3.googleusercontent.com/d/{fid}"
        except Exception:
            return url
    if "/d/" in url:
        try:
            fid = url.split("/d/")[1].split("/")[0]
            return f"https://lh3.googleusercontent.com/d/{fid}"
        except Exception:
            return url
    return url


# ─── HELPER: GDrive file ID → URL download ───────────────────
def gdrive_file_id_to_download_url(file_id: str) -> str:
    """Konversi file ID Google Drive ke URL download langsung."""
    return f"https://drive.google.com/uc?export=download&id={file_id}"


# ─── HELPER: slideshow HTML ──────────────────────────────────
def build_slideshow_html(covers: list) -> str:
    if not covers:
        return ('<div style="width:100%;height:320px;border-radius:16px;background:#f5ede5;'
                'display:flex;align-items:center;justify-content:center;font-size:4rem;color:#c8a898;">&#9749;</div>')
    slides = ""
    for i, src in enumerate(covers):
        disp    = "block" if i == 0 else "none"
        slides += (
            f'<div id="slide_{i}" style="display:{disp};width:100%;height:340px;'
            f'border-radius:16px;overflow:hidden;background:#f5ede5;">'
            f'<img src="{src}" style="width:100%;height:340px;object-fit:cover;display:block;" '
            f'loading="lazy" onerror="this.parentElement.style.background=\'#f5ede5\';">'
            f'</div>'
        )
    dots = ""
    if len(covers) > 1:
        dots = '<div style="text-align:center;margin-top:10px;">' + "".join(
            f'<button onclick="showSlide({i})" id="dot_{i}" style="width:{14 if i==0 else 8}px;height:8px;'
            f'border-radius:50px;border:none;background:{"#C8502A" if i==0 else "#ddd"};'
            f'cursor:pointer;transition:.2s;margin:0 3px;padding:0;"></button>'
            for i in range(len(covers))
        ) + '</div>'
    n  = len(covers)
    js = f"""<script>
(function(){{
  var n={n},cur=0;
  function showSlide(i){{
    for(var j=0;j<n;j++){{
      var s=document.getElementById('slide_'+j),d=document.getElementById('dot_'+j);
      if(s)s.style.display=j===i?'block':'none';
      if(d){{d.style.background=j===i?'#C8502A':'#ddd';d.style.width=j===i?'14px':'8px';}}
    }}
    cur=i;
  }}
  window.showSlide=showSlide;
  if(n>1)setInterval(function(){{showSlide((cur+1)%n);}},3500);
}})();
</script>"""
    return slides + dots + js


# ─── COMMON_CSS ──────────────────────────────────────────────
COMMON_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,700;9..144,900&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
:root{--rust:#C8502A;--rust-dk:#A33E20;--rust-lt:#FFF0EB;--ink:#1C1917;--muted:#78716C;--border:#E8DDD5;}
html,body,[class*="css"]{font-family:'Plus Jakarta Sans',sans-serif;background:#fff;color:var(--ink);}
.stApp{background:#fff;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding-top:0!important;padding-left:0!important;padding-right:0!important;max-width:100%!important;}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:13px 40px;background:#fff;border-bottom:1px solid var(--border);box-shadow:0 2px 16px rgba(28,25,23,.05);position:sticky;top:0;z-index:999;}
.topbar-logo{font-family:'Fraunces',serif;font-size:1.4rem;font-weight:900;color:var(--ink);letter-spacing:-.5px;}
.topbar-logo span{color:var(--rust);}
.detail-info-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin-bottom:24px;}
.info-card{background:#fff;border:1.5px solid var(--border);border-radius:14px;padding:18px 20px;}
.info-label{font-size:.72rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.8px;margin-bottom:5px;}
.info-value{font-size:.92rem;color:var(--ink);font-weight:600;}
.info-value a{color:var(--rust);text-decoration:none;}
.best-aspects-wrap{background:var(--rust-lt);border:1px solid rgba(200,80,42,.2);border-radius:14px;padding:18px 20px;margin-bottom:24px;}
.best-aspect-chip{display:inline-flex;align-items:center;gap:5px;background:var(--rust);color:#fff;border-radius:50px;padding:5px 13px;font-size:.76rem;font-weight:600;margin:3px;}
.section-wrap{padding:32px 48px 44px;}
.cards-grid{display:flex;flex-wrap:wrap;gap:20px;padding:0;}
.kafe-card{width:220px;background:#fff;border-radius:16px;border:1.5px solid var(--border);overflow:hidden;position:relative;cursor:pointer;transition:transform .2s,box-shadow .2s;}
.kafe-card:hover{transform:translateY(-5px);box-shadow:0 18px 40px rgba(0,0,0,.1);}
.kafe-rank{position:absolute;top:8px;left:8px;background:rgba(0,0,0,.65);color:#fff;font-size:.68rem;font-weight:700;width:27px;height:27px;border-radius:50%;display:flex;align-items:center;justify-content:center;z-index:2;}
.rank-gold{background:#D4A017!important;}.rank-silver{background:#8C8C8C!important;}.rank-bronze{background:#A0522D!important;}
.kafe-img-wrap{width:100%;height:140px;overflow:hidden;background:#f5ede5;}
.kafe-img-wrap img{width:100%;height:140px;object-fit:cover;display:block;transition:transform .4s;}
.kafe-card:hover .kafe-img-wrap img{transform:scale(1.05);}
.kafe-img-placeholder{width:100%;height:140px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;color:#c8a898;font-size:2rem;background:#f5ede5;}
.kafe-img-placeholder small{font-size:.62rem;text-transform:uppercase;letter-spacing:.5px;}
.kafe-body{padding:12px 13px 14px;}
.kafe-name{font-family:'Fraunces',serif;font-size:.88rem;font-weight:700;color:var(--ink);margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.kafe-addr{font-size:.69rem;color:#999;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.kafe-jam{font-size:.69rem;color:var(--rust);font-weight:600;margin-bottom:8px;}
.kafe-stats{display:flex;align-items:center;gap:4px;flex-wrap:wrap;}
.stat-pill{font-size:.66rem;color:#555;background:#F7F3F0;padding:3px 7px;border-radius:50px;font-weight:500;}
.stat-sentimen{margin-left:auto;background:var(--rust-lt);color:var(--rust);font-weight:700;font-size:.66rem;padding:3px 8px;border-radius:50px;white-space:nowrap;}
</style>
"""
