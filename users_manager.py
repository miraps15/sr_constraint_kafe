# ============================================================
# Manajemen user via Google Sheets API
# Menggantikan akses file users.xlsx lokal di /content/drive
# ============================================================

import pandas as pd
import streamlit as st
from gsheets_client import (
    read_sheet_as_df,
    write_df_to_sheet,
    append_row_to_sheet,
    update_row_in_sheet,
)

_SHEET = "users"

# ── Kolom wajib di sheet users ────────────────────────────────
_REQUIRED_COLS = ["email", "username", "password",
                  "akun_google", "favorite_kafe", "wilayah kamu"]


# ─── LOAD ────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=60)
def load_users() -> pd.DataFrame:
    """
    Baca sheet 'users' dari Google Sheets.
    Di-cache 60 detik; panggil st.cache_data.clear() setelah write.
    """
    try:
        df = read_sheet_as_df(_SHEET)
        # Pastikan semua kolom ada
        for col in _REQUIRED_COLS:
            if col not in df.columns:
                df[col] = ""
        return df.fillna("")
    except Exception as e:
        st.warning(f"⚠️ Gagal membaca data user: {e}")
        return pd.DataFrame(columns=_REQUIRED_COLS)


def _invalidate_cache():
    """Hapus cache load_users agar data terbaru terbaca."""
    load_users.clear()


# ─── SAVE (timpa seluruh sheet) ───────────────────────────────
def save_users(df_users: pd.DataFrame) -> None:
    try:
        write_df_to_sheet(df_users, _SHEET)
        _invalidate_cache()
    except Exception as e:
        st.warning(f"⚠️ Gagal menyimpan data user: {e}")


# ─── UPSERT (tambah user baru) ────────────────────────────────
def upsert_user(email: str = "", username: str = "",
                password: str = "", akun_google: str = "",
                wilayah: str = "") -> tuple:
    """
    Tambah user baru.
    Returns (True, "OK") atau (False, pesan_error).
    """
    df_users = load_users()

    if username and (df_users["username"] == username).any():
        return False, "Username sudah digunakan."
    if email and (df_users["email"] == email).any():
        return False, "Email sudah terdaftar."

    new_row = {
        "email": email, "username": username, "password": password,
        "akun_google": akun_google, "favorite_kafe": "",
        "wilayah kamu": wilayah,
    }
    try:
        append_row_to_sheet(new_row, _SHEET)
        _invalidate_cache()
        return True, "OK"
    except Exception as e:
        return False, f"Gagal mendaftar: {e}"


# ─── LOGIN ───────────────────────────────────────────────────
def check_login(username: str, password: str) -> bool:
    df_users = load_users()
    mask = (df_users["username"] == username) & (df_users["password"] == password)
    return bool(mask.any())


# ─── GOOGLE ACCOUNTS ─────────────────────────────────────────
def get_google_accounts() -> list:
    df_users = load_users()
    if df_users.empty:
        return []
    accounts = []
    for _, row in df_users.iterrows():
        g = str(row.get("akun_google", "")).strip()
        if g and g not in ("", "nan") and g not in accounts:
            accounts.append(g)
    return accounts


def ensure_google_user(akun_google: str) -> str:
    """
    Pastikan akun Google terdaftar.
    Jika belum ada, buat entri baru.
    Kembalikan display_name (bagian sebelum @gmail.com).
    """
    df_users = load_users()
    if not df_users.empty and (df_users["akun_google"] == akun_google).any():
        display = akun_google.replace("@gmail.com", "")
        return display

    new_row = {
        "email": akun_google, "username": "", "password": "",
        "akun_google": akun_google, "favorite_kafe": "",
        "wilayah kamu": "",
    }
    try:
        append_row_to_sheet(new_row, _SHEET)
        _invalidate_cache()
    except Exception as e:
        st.warning(f"⚠️ Gagal menyimpan akun Google: {e}")

    return akun_google.replace("@gmail.com", "")


# ─── FAVORIT ─────────────────────────────────────────────────
def get_user_favorites(identifier: str, is_google: bool) -> list:
    df_users = load_users()
    if df_users.empty:
        return []
    try:
        mask  = df_users["akun_google"] == identifier if is_google \
                else df_users["username"] == identifier
        match = df_users[mask]
        if match.empty:
            return []
        favs = []
        for _, row in match.iterrows():
            fav_str = str(row.get("favorite_kafe", "")).strip()
            if fav_str and fav_str not in ("", "nan"):
                for f in fav_str.split("|"):
                    f = f.strip()
                    if f and f not in favs:
                        favs.append(f)
        return favs
    except Exception:
        return []


def toggle_favorite(identifier: str, is_google: bool, nama_kafe: str) -> bool:
    """
    Toggle favorit. Returns True jika sekarang difavoritkan, False jika dihapus.
    """
    current_favs = get_user_favorites(identifier, is_google)

    if nama_kafe in current_favs:
        current_favs.remove(nama_kafe)
        is_fav = False
    else:
        current_favs.append(nama_kafe)
        is_fav = True

    key_col = "akun_google" if is_google else "username"
    try:
        success = update_row_in_sheet(
            spreadsheet_name=_SHEET,
            key_col=key_col,
            key_val=identifier,
            updates={"favorite_kafe": "|".join(current_favs)},
        )
        if success:
            _invalidate_cache()
        return is_fav
    except Exception as e:
        st.warning(f"⚠️ Gagal update favorit: {e}")
        return not is_fav  # rollback
