# Home.py — Entry point ultra-ringan, TIDAK ada komputasi berat
import streamlit as st

st.set_page_config(
    page_title="KafeSby",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Bersihkan semua state berbahaya saat pertama load
_keys_to_clear = [
    "_all_slides_html_guest", "_all_slides_html_loggedin",
    "_cached_best_df", "_cached_top5",
    "_cached_best_df_1", "_cached_top5_1",
    "analisis_processing", "_nav_to_analisis",
    "_absa_warmed", "precompute_done_1",
    "detail_kid", "detail_nama", "_nav_to_detail",
    "_go_back", "analisis_result", "_pending_reviews",
]
for _k in _keys_to_clear:
    if _k in st.session_state:
        del st.session_state[_k]

# Langsung redirect ke app_kafe.py
st.switch_page("app_kafe.py")
