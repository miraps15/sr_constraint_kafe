# ============================================================
# Halaman debug untuk mendiagnosa mengapa aspek tidak terdeteksi
# HAPUS halaman ini setelah selesai debugging!
# ============================================================

import streamlit as st
import os
import sys
import tempfile

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

st.set_page_config(page_title="Debug ABSA", layout="wide")

# Amankan halaman ini
if not st.session_state.get("logged_in", False):
    st.error("Silakan login terlebih dahulu")
    st.stop()

st.title("🔧 Debug ABSA Engine")
st.warning("⚠️ Hapus halaman ini setelah debugging selesai!")

# ─── SECTION 1: ENVIRONMENT ───────────────────────────────────
with st.expander("1. Environment & Library Check", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Python version:**", sys.version)
        st.write("**Temp dir:**", tempfile.gettempdir())

        # PyTorch
        try:
            import torch
            st.success(f"✅ PyTorch: {torch.__version__}, CUDA: {torch.cuda.is_available()}")
        except ImportError as e:
            st.error(f"❌ PyTorch: {e}")

        # NumPy
        try:
            import numpy as np
            st.success(f"✅ NumPy: {np.__version__}")
        except ImportError as e:
            st.error(f"❌ NumPy: {e}")

    with col2:
        # spaCy
        try:
            import spacy
            st.success(f"✅ spaCy: {spacy.__version__}")
            try:
                nlp = spacy.load("en_core_web_sm")
                doc = nlp("the coffee was great and service was fast")
                tokens = [t.text for t in doc]
                pos    = [t.pos_ for t in doc]
                st.success(f"✅ en_core_web_sm loaded")
                st.write("Test tokens:", tokens)
                st.write("POS tags:", pos)
            except OSError:
                st.error("❌ en_core_web_sm TIDAK terinstall — jalankan: python -m spacy download en_core_web_sm")
        except ImportError:
            st.error("❌ spaCy tidak terinstall")

        # deep_translator
        try:
            from deep_translator import GoogleTranslator
            result = GoogleTranslator(source='id', target='en').translate("makanan enak banget")
            st.success(f"✅ deep_translator OK: 'makanan enak banget' → '{result}'")
        except Exception as e:
            st.warning(f"⚠️ deep_translator: {e}")

# ─── SECTION 2: CACHE FILES ───────────────────────────────────
with st.expander("2. Cache Files (Google Drive Downloads)", expanded=True):
    cache_dir = os.path.join(tempfile.gettempdir(), "absa_cache")
    st.write(f"**Cache dir:** `{cache_dir}`")

    if os.path.exists(cache_dir):
        files = os.listdir(cache_dir)
        if files:
            import pandas as pd
            rows = []
            for f in sorted(files):
                fp   = os.path.join(cache_dir, f)
                size = os.path.getsize(fp)
                rows.append({
                    "File"      : f,
                    "Size (MB)" : round(size / (1024 * 1024), 2),
                    "Status"    : "✅ OK" if size > 10000 else "❌ Terlalu kecil (mungkin HTML error)"
                })
            st.dataframe(pd.DataFrame(rows))
        else:
            st.warning("Cache dir kosong — belum ada file yang didownload")
    else:
        st.warning("Cache dir belum ada")

    if st.button("🗑️ Hapus Semua Cache (Force Re-download)"):
        if os.path.exists(cache_dir):
            import shutil
            shutil.rmtree(cache_dir)
            os.makedirs(cache_dir, exist_ok=True)
        st.cache_resource.clear()
        st.cache_data.clear()
        st.success("Cache dihapus! Refresh halaman untuk re-download")

    st.markdown("---")  # ← pemisah visual

    # ── Test Download GloVe ──────────────────────────────────
    if st.button("🔄 Test Download GloVe Sekarang"):
        from absa_engine import _GDRIVE_IDS, _cached_path
        import requests

        st.write(f"**GloVe File ID:** `{_GDRIVE_IDS['glove']}`")

        try:
            r = requests.get(
                f"https://drive.google.com/uc?export=download&id={_GDRIVE_IDS['glove']}",
                stream=True,
                timeout=30
            )
            content_type = r.headers.get("content-type", "")
            first_bytes  = next(r.iter_content(chunk_size=512), b"")

            st.write("**Status code:**", r.status_code)
            st.write("**Content-Type:**", content_type)
            st.write("**Cookies:**", dict(r.cookies))
            st.write("**Bytes pertama (raw):**", first_bytes[:200])

            if b"<!DOCTYPE" in first_bytes or b"<html" in first_bytes:
                st.error("❌ Google Drive mengembalikan HTML — file tidak publik atau perlu confirm token")
                st.code(first_bytes.decode("utf-8", errors="ignore"), language="html")

                # Cek apakah ada confirm token di cookies
                confirm = None
                for k, v in r.cookies.items():
                    if k.startswith("download_warning"):
                        confirm = v
                        break
                if confirm:
                    st.info(f"✅ Confirm token ditemukan di cookies: `{confirm}` — download seharusnya bisa dengan token ini")
                else:
                    st.warning("⚠️ Tidak ada confirm token di cookies — kemungkinan file di-restrict Google")

            elif first_bytes and first_bytes[:4].isascii():
                st.success("✅ Respons tampak seperti teks GloVe yang valid")
                st.write("**Sample 200 karakter pertama:**")
                st.code(first_bytes[:200].decode("utf-8", errors="ignore"))
            else:
                st.warning("⚠️ Format tidak dikenali — mungkin binary atau encoding lain")
                st.write("Hex:", first_bytes[:50].hex())

        except Exception as e:
            st.error(f"❌ Request gagal: {e}")
            import traceback
            st.code(traceback.format_exc())
            
# ─── SECTION 3: MODEL LOAD TEST ───────────────────────────────
with st.expander("3. Model Load Test", expanded=True):
    if st.button("🔄 Test Load Model (bisa butuh beberapa menit)"):
        with st.spinner("Loading..."):
            try:
                from absa_engine import load_aspect_model_engine, load_sent_model_engine, load_glove

                st.write("Testing GloVe...")
                glove, mean_vec = load_glove()
                st.write(f"GloVe vocab size: {len(glove):,}")
                if len(glove) < 100:
                    st.error("❌ GloVe terlalu kecil — kemungkinan gagal download atau pakai fallback random!")
                else:
                    st.success(f"✅ GloVe OK: {len(glove):,} words")

                # Test beberapa kata kunci
                test_words = ['food', 'coffee', 'service', 'good', 'bad', 'taste']
                found = [w for w in test_words if w in glove]
                st.write(f"Kata uji yang ada di GloVe: {found}")

                st.write("Testing Aspect Model...")
                asp_model, asp_cfg = load_aspect_model_engine()
                if asp_model is None:
                    st.error("❌ Aspect model GAGAL load!")
                else:
                    st.success("✅ Aspect model OK")
                    st.write("Config:", {k: v for k, v in asp_cfg.items()
                                         if k not in ('bio_label_map', 'pos_vocab')})
                    st.write("Categories:", asp_cfg.get('categories', []))
                    st.write("BIO labels (sample):", dict(list(asp_cfg.get('bio_label_map', {}).items())[:10]))

                st.write("Testing Sentiment Model...")
                sent_model, sent_cfg = load_sent_model_engine()
                if sent_model is None:
                    st.error("❌ Sentiment model GAGAL load!")
                else:
                    st.success("✅ Sentiment model OK")
                    st.write("Config:", {k: v for k, v in sent_cfg.items()
                                         if k not in ('pos_vocab',)})

            except Exception as e:
                st.error(f"Error: {e}")
                import traceback
                st.code(traceback.format_exc())

# ─── SECTION 4: SINGLE REVIEW TEST ───────────────────────────
with st.expander("4. Test Analisis Satu Review", expanded=True):
    test_review = st.text_area(
        "Masukkan review untuk ditest:",
        value="The coffee was excellent and the service was very friendly. However the wifi was slow.",
        height=100
    )
    test_translate = st.checkbox("Terjemahkan ke English dulu", value=False)

    if st.button("🔍 Analisis Review Ini"):
        with st.spinner("Menganalisis..."):
            try:
                from absa_engine import analyze_single_review, translate_to_english

                if test_translate:
                    text_en = translate_to_english(test_review)
                    st.write(f"**Setelah translate:** `{text_en}`")
                else:
                    text_en = test_review

                results = analyze_single_review(text_en)
                if results:
                    st.success(f"✅ {len(results)} aspek terdeteksi!")
                    import pandas as pd
                    st.dataframe(pd.DataFrame(results))
                else:
                    st.error("❌ Tidak ada aspek terdeteksi!")
                    st.info("""
                    Kemungkinan penyebab:
                    1. Model mengoutput semua 'O' label (model tidak bisa deteksi aspek di review ini)
                    2. Semua prediksi difilter oleh POS/DEP tag (terlalu agresif)
                    3. GloVe pakai fallback random (kata tidak ada di vocabulary)
                    4. Model tidak diload dengan benar

                    Cek console/logs untuk detail.
                    """)

            except Exception as e:
                st.error(f"Error: {e}")
                import traceback
                st.code(traceback.format_exc())

# ─── SECTION 5: FULL PIPELINE TEST ───────────────────────────
with st.expander("5. Test Pipeline Lengkap (dengan translate)", expanded=False):
    test_reviews_id = st.text_area(
        "Review bahasa Indonesia (satu per baris):",
        value="Kopinya enak banget, tapi pelayanannya lambat\nSuasana nyaman dan bersih, harga terjangkau\nWifi kenceng, tempatnya cozy buat kerja",
        height=120
    )

    if st.button("🚀 Jalankan Pipeline"):
        reviews_list = [r.strip() for r in test_reviews_id.split('\n') if r.strip()]
        with st.spinner(f"Memproses {len(reviews_list)} review..."):
            try:
                from absa_engine import run_analysis_pipeline
                result = run_analysis_pipeline(reviews_list, translate=True)

                raw = result.get('raw_aspects', [])
                df_conv = result.get('df_converted', None)

                st.write(f"**Total aspek terdeteksi:** {len(raw)}")
                if raw:
                    import pandas as pd
                    st.write("**Raw aspects:**")
                    st.dataframe(pd.DataFrame(raw))
                    if df_conv is not None and not df_conv.empty:
                        st.write("**Converted:**")
                        st.dataframe(df_conv)
                else:
                    st.error("❌ Tidak ada aspek! Cek console untuk detail log.")

            except Exception as e:
                st.error(f"Error: {e}")
                import traceback
                st.code(traceback.format_exc())
