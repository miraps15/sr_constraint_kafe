# error_boundary.py
# Dipanggil di awal SETIAP halaman untuk menangkap crash dan redirect ke home
import streamlit as st
import traceback
import gc

def clear_heavy_session_state():
    """Hapus key session_state yang berat untuk free memory."""
    heavy_keys = [
        "_cached_best_df", "_cached_top5", "_cached_best_df_1",
        "_cached_top5_1", "_all_slides_html_guest", "_all_slides_html_loggedin",
        "_absa_slides_cache", "analisis_result", "_pending_reviews",
        "_cached_saw_cat", "_cached_overall", "_cached_reviewer_pct",
        "precompute_done_1", "_cached_reviewer_pct",
    ]
    cleared = 0
    for key in heavy_keys:
        if key in st.session_state:
            del st.session_state[key]
            cleared += 1
    gc.collect()
    return cleared

def reset_navigation_state():
    """Reset semua state navigasi agar tidak stuck di halaman yang crash."""
    nav_keys = [
        "detail_kid", "detail_nama", "detail_source", "detail_vi_score",
        "detail_cond_chosen", "detail_cat_chosen", "detail_cond",
        "detail_alamat", "_nav_to_detail", "_nav_to_analisis",
        "_go_to_fav", "_go_back", "_prev_page", "compare_names",
        "pref_items", "pref_bobot", "pref_lokasi",
        "show_no_kafe_popup", "show_lokasi_only_popup",
        "show_google_popup", "show_daftar_popup",
        "analisis_processing", "analisis_error",
        "_absa_warmed", "_absa_warm_error",
    ]
    for key in nav_keys:
        if key in st.session_state:
            del st.session_state[key]

def check_memory_and_maybe_clear(threshold_mb: float = 400.0):
    """
    Cek estimasi memory usage. Jika di atas threshold,
    clear cache berat dan paksa GC.
    """
    try:
        import resource, platform
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        mem_mb = usage / 1024 if platform.system() != 'Darwin' else usage / (1024 * 1024)
        if mem_mb > threshold_mb:
            cleared = clear_heavy_session_state()
            st.cache_data.clear()
            gc.collect()
            return True, mem_mb
        return False, mem_mb
    except Exception:
        return False, 0.0
