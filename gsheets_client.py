# ============================================================
# Modul terpusat untuk autentikasi Google Sheets API
# menggunakan service account dari st.secrets (Streamlit Cloud)
# ============================================================

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

# Scope yang dibutuhkan untuk Sheets + Drive (read/write)
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ID spreadsheet — diambil dari st.secrets
_SPREADSHEET_IDS = {
    "df_inference_kafe": "1HkCEV_TIf6EzbPXrSkMgdlOoUpTc3f4zBnOtAMx5lJU",
    "users":             "1uh-S7R86SC82_PRfNUQQkDxi-Z0qf5W913_M2Hi5z9c",
    "df_konversi":       "1GIRFmlE2bg50deNZHVvSNrO-Wr-51Q5G0rUN3T7HyEU",
}


@st.cache_resource(show_spinner=False)
def _get_gspread_client() -> gspread.Client:
    """
    Buat gspread client dari service account credentials di st.secrets.
    Di-cache sebagai resource agar koneksi tidak dibuat ulang setiap rerun.
    """
    creds_dict = dict(st.secrets["gcp_service_account"])
    # Perbaiki newline pada private_key jika perlu
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(creds_dict, scopes=_SCOPES)
    return gspread.authorize(creds)


def get_spreadsheet_id(name: str) -> str:
    """
    Ambil spreadsheet ID berdasarkan nama.
    Prioritas: st.secrets["spreadsheet"] → fallback ke _SPREADSHEET_IDS.
    """
    try:
        sid = st.secrets["spreadsheet"].get(f"{name}_id", "")
        if sid:
            return sid
    except Exception:
        pass
    return _SPREADSHEET_IDS.get(name, "")


def read_sheet_as_df(spreadsheet_name: str,
                     worksheet_index: int = 0,
                     worksheet_name: str = None) -> pd.DataFrame:
    """
    Baca satu worksheet dari Google Spreadsheet dan kembalikan sebagai DataFrame.

    Parameters
    ----------
    spreadsheet_name : str
        Nama spreadsheet, harus ada di _SPREADSHEET_IDS / st.secrets.
    worksheet_index : int
        Indeks worksheet (default 0 = sheet pertama).
    worksheet_name : str
        Nama worksheet; jika diisi, lebih prioritas dari worksheet_index.

    Returns
    -------
    pd.DataFrame
    """
    client  = _get_gspread_client()
    sid     = get_spreadsheet_id(spreadsheet_name)
    sh      = client.open_by_key(sid)
    ws      = sh.worksheet(worksheet_name) if worksheet_name else sh.get_worksheet(worksheet_index)
    records = ws.get_all_records(numericise_ignore=["all"])
    return pd.DataFrame(records)


def write_df_to_sheet(df: pd.DataFrame,
                      spreadsheet_name: str,
                      worksheet_index: int = 0,
                      worksheet_name: str = None) -> None:
    """
    Tulis DataFrame ke worksheet (timpa seluruh isi sheet).

    Parameters
    ----------
    df : pd.DataFrame
        Data yang akan ditulis.
    spreadsheet_name : str
        Nama spreadsheet target.
    worksheet_index : int
        Indeks worksheet (default 0).
    worksheet_name : str
        Nama worksheet; jika diisi lebih prioritas.
    """
    client = _get_gspread_client()
    sid    = get_spreadsheet_id(spreadsheet_name)
    sh     = client.open_by_key(sid)
    ws     = sh.worksheet(worksheet_name) if worksheet_name else sh.get_worksheet(worksheet_index)
    # Konversi semua nilai ke string agar aman ditulis ke Sheets
    df_out = df.fillna("").astype(str)
    ws.clear()
    ws.update([df_out.columns.tolist()] + df_out.values.tolist())


def append_row_to_sheet(row_dict: dict,
                        spreadsheet_name: str,
                        worksheet_index: int = 0,
                        worksheet_name: str = None) -> None:
    """
    Tambahkan satu baris baru ke akhir worksheet.

    Parameters
    ----------
    row_dict : dict
        Data baris baru {kolom: nilai}.
    spreadsheet_name : str
        Nama spreadsheet target.
    worksheet_index / worksheet_name : opsional.
    """
    client = _get_gspread_client()
    sid    = get_spreadsheet_id(spreadsheet_name)
    sh     = client.open_by_key(sid)
    ws     = sh.worksheet(worksheet_name) if worksheet_name else sh.get_worksheet(worksheet_index)
    header = ws.row_values(1)
    new_row = [str(row_dict.get(col, "")) for col in header]
    ws.append_row(new_row, value_input_option="USER_ENTERED")


def update_row_in_sheet(spreadsheet_name: str,
                        key_col: str,
                        key_val: str,
                        updates: dict,
                        worksheet_index: int = 0,
                        worksheet_name: str = None) -> bool:
    """
    Update satu baris di worksheet berdasarkan nilai kolom kunci.

    Parameters
    ----------
    spreadsheet_name : str
    key_col : str
        Nama kolom yang digunakan sebagai kunci pencarian.
    key_val : str
        Nilai yang dicari di kolom key_col.
    updates : dict
        Kolom dan nilai baru yang akan di-update.

    Returns
    -------
    bool — True jika berhasil, False jika baris tidak ditemukan.
    """
    client  = _get_gspread_client()
    sid     = get_spreadsheet_id(spreadsheet_name)
    sh      = client.open_by_key(sid)
    ws      = sh.worksheet(worksheet_name) if worksheet_name else sh.get_worksheet(worksheet_index)
    data    = ws.get_all_values()
    if not data:
        return False
    header  = data[0]
    try:
        key_idx = header.index(key_col)
    except ValueError:
        return False
    for row_idx, row in enumerate(data[1:], start=2):
        if len(row) > key_idx and str(row[key_idx]).strip() == str(key_val).strip():
            for col_name, new_val in updates.items():
                if col_name in header:
                    col_idx = header.index(col_name) + 1  # gspread 1-based
                    ws.update_cell(row_idx, col_idx, str(new_val))
            return True
    return False
