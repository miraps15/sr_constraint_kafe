# ============================================================
# absa_engine.py — Modul inferensi ABSA untuk Streamlit Cloud
#
# PERBAIKAN KRITIS dari versi sebelumnya (kode baru):
#
# [FIX-1] BIO map integer key: i_to_b/b_to_i HARUS menggunakan
#         nilai dari bio_lbl_map LANGSUNG (tanpa int() casting ulang),
#         karena pada kode lama nilai bio_lbl_map bisa berupa int atau
#         string tergantung dari JSON. raw_preds dari model sudah int,
#         sehingga bio_idx_map {int(v): k} benar, TAPI i_to_b dan b_to_i
#         HARUS menggunakan int() casting KONSISTEN di kedua sisi.
#         Root cause: int() casting tidak konsisten menyebabkan semua
#         lookup i_to_b.get(pred) mengembalikan None → semua prediksi
#         I- tidak dikoreksi → span extraction gagal total.
#
# [FIX-2] Filter POS heuristik DIHAPUS (_is_non_aspect_word_heuristic):
#         Filter ini tidak ada di kode lama dan menyebabkan kata-kata
#         valid seperti "slow", "fast", "clean", "noisy" dibuang.
#         Filter POS/DEP hanya dilakukan jika spaCy tersedia dan
#         memberikan pos_tags/dep_tags yang akurat.
#
# [FIX-3] Adjacency fallback dikembalikan ke identity matrix (seperti
#         kode lama). Window adjacency memasukkan sinyal palsu ke GCN
#         yang mengubah distribusi prediksi model secara drastis.
#
# [FIX-4] Token filter ekstra DIHAPUS (filter `len(t) > 1 or t.isalpha()`
#         dan filter non-ASCII). Filter ini menyebabkan index misalignment
#         antara valid_tokens, adj, pos_tags, dep_tags, dan embedding.
#         Kode lama hanya filter punctuation murni (is_punct_token).
#
# [FIX-5] Translate: source='auto' dikembalikan (seperti kode lama).
#         Heuristik deteksi bahasa Indonesia diperbaiki agar lebih akurat
#         dan tidak memblokir review bahasa Indonesia yang sudah dikenali.
#
# [FIX-6] run_analysis_pipeline: _source_review ditambahkan ke setiap
#         aspek (konsisten dengan kode lama di app_kafe1.py).
#
# [FIX-7] Model loading: menggunakan pola @st.cache_resource (Streamlit
#         Cloud), TAPI juga mendukung global variable cache (Colab/lokal).
#         Di Colab, @st.cache_resource berfungsi normal.
#
# Kompatibilitas:
#   - Google Colab: model dari /content/drive (path lokal)
#   - Streamlit Cloud: model dari Google Drive (download via requests)
#   - Deteksi otomatis berdasarkan os.path.exists(COLAB_GLOVE_PATH)
# ============================================================

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import json
import os
import string
import tempfile
import requests
import pandas as pd
import re
from collections import defaultdict
import streamlit as st

# ── Lazy imports ─────────────────────────────────────────────
# ✅ GANTI DENGAN INI:
@st.cache_resource(show_spinner=False)
def _get_nlp_cached():
    try:
        import spacy
        try:
            nlp = spacy.load("en_core_web_sm")
            print("[absa_engine] spaCy en_core_web_sm loaded OK")
            return nlp
        except OSError:
            print("[absa_engine] Downloading spaCy en_core_web_sm...")
            from spacy.cli import download as spacy_download
            spacy_download("en_core_web_sm")
            nlp = spacy.load("en_core_web_sm")
            print("[absa_engine] spaCy downloaded & loaded OK")
            return nlp
    except Exception as e:
        print(f"[absa_engine] spaCy tidak tersedia: {e}")
        return None

def _get_nlp():
    return _get_nlp_cached()

# ════════════════════════════════════════════════════════════════
# DETEKSI ENVIRONMENT (Colab vs Streamlit Cloud)
# ════════════════════════════════════════════════════════════════
_BASE_DRIVE      = "/content/drive/MyDrive/Skripsi"
COLAB_GLOVE_PATH = f"{_BASE_DRIVE}/Glove/glove.6B.300d.txt"
COLAB_ASP_MODEL  = f"{_BASE_DRIVE}/Model/absa_model.pth"
COLAB_ASP_CFG    = f"{_BASE_DRIVE}/Model/absa_config.json"
COLAB_SENT_MODEL = f"{_BASE_DRIVE}/Model/absa_sentiment_model_v2.pth"
COLAB_SENT_CFG   = f"{_BASE_DRIVE}/Model/absa_sentiment_config_v2.json"
COLAB_KONVERSI   = f"{_BASE_DRIVE}/Konversi/df_konversi.xlsx"

_IS_COLAB = os.path.exists(COLAB_GLOVE_PATH)
print(f"[absa_engine] Environment: {'Google Colab' if _IS_COLAB else 'Streamlit Cloud'}")

# ════════════════════════════════════════════════════════════════
# GOOGLE DRIVE DOWNLOAD (hanya untuk Streamlit Cloud)
# ════════════════════════════════════════════════════════════════
_GDRIVE_IDS = {
    "glove"       : "1LuU5Y5RDooBWT4Olxl7JVpBbwMfxtI8_",
    "asp_model"   : "1nfbwYhaQBdihO_s60aS1TipIn6NIrIMN",
    "asp_config"  : "1FhPVMZ-0gVCCJFzihSg4fSNibkmfX23N",
    "sent_config" : "1P4ZmLs1UCkxlKBODwTxlJzse8y1u2-xP",
    "sent_model"  : "1jQSV8wmNujQj7pfFXpN18CcUCmMj8jt3",
}

_MIN_FILE_SIZES = {
    "glove"      : 50 * 1024 * 1024,
    "asp_model"  : 1 * 1024 * 1024,
    "asp_config" : 1 * 1024,
    "sent_config": 1 * 1024,
    "sent_model" : 1 * 1024 * 1024,
}

_CACHE_DIR = os.path.join(tempfile.gettempdir(), "absa_cache")
os.makedirs(_CACHE_DIR, exist_ok=True)

def _cached_path(name: str, ext: str) -> str:
    return os.path.join(_CACHE_DIR, f"{name}{ext}")

def _is_valid_cached_file(path: str, name: str) -> bool:
    if not os.path.exists(path):
        return False
    size = os.path.getsize(path)
    min_size = _MIN_FILE_SIZES.get(name, 100)
    if size < min_size:
        print(f"[absa_engine] Cache {name} terlalu kecil ({size} < {min_size}), re-download")
        os.remove(path)
        return False
    return True

# ✅ GANTI DENGAN INI:
def _download_gdrive_file(file_id: str, dest_path: str, desc: str = "", name: str = "") -> bool:
    if _is_valid_cached_file(dest_path, name):
        print(f"[absa_engine] Cache valid: {desc}")
        return True

    print(f"[absa_engine] Downloading {desc} (id={file_id})...")
    try:
        session = requests.Session()

        # Step 1: Request awal
        url      = "https://drive.google.com/uc"
        params   = {"id": file_id, "export": "download"}
        response = session.get(url, params=params, stream=True, timeout=120)

        # Step 2: Cari confirm token (untuk file besar)
        # Google Drive mengembalikan form dengan token konfirmasi untuk file >100MB
        confirm_token = None

        # Cek dari cookies
        for key, value in response.cookies.items():
            if key.startswith("download_warning"):
                confirm_token = value
                break

        # Jika tidak ada di cookies, cari di body HTML
        if confirm_token is None:
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                # Baca sebagian body untuk cari token
                chunk = b""
                for c in response.iter_content(chunk_size=8192):
                    chunk += c
                    if len(chunk) > 65536:  # Baca max 64KB
                        break

                # Cari pola confirm= di HTML
                # Pola baru Google Drive (2024)
                match = re.search(
                    r'confirm=([0-9A-Za-z_\-]+)', chunk.decode("utf-8", errors="ignore")
                )
                if match:
                    confirm_token = match.group(1)
                else:
                    # Pola alternatif: uuid dalam URL download
                    match2 = re.search(
                        r'uuid=([0-9A-Za-z_\-]+)', chunk.decode("utf-8", errors="ignore")
                    )
                    if match2:
                        # Format baru: gunakan URL download dengan uuid
                        uuid_val  = match2.group(1)
                        url2      = f"https://drive.usercontent.google.com/download"
                        params2   = {
                            "id"      : file_id,
                            "export"  : "download",
                            "confirm" : "t",
                            "uuid"    : uuid_val,
                        }
                        response = session.get(url2, params=params2, stream=True, timeout=600)
                        confirm_token = "already_handled"

        # Step 3: Jika ada confirm token biasa (bukan uuid), request ulang
        if confirm_token and confirm_token != "already_handled":
            params2  = {"id": file_id, "export": "download", "confirm": confirm_token}
            response = session.get(url, params=params2, stream=True, timeout=600)

        # Step 4: Jika masih HTML setelah semua upaya → coba URL alternatif
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            print(f"[absa_engine] Respons masih HTML, coba URL alternatif...")
            alt_url  = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
            response = session.get(alt_url, stream=True, timeout=600)
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type and name not in ("asp_config", "sent_config"):
                print(f"[absa_engine] ✗ Download {desc} tetap mengembalikan HTML — akses ditolak atau file tidak publik")
                return False

        # Step 5: Tulis file
        total_written = 0
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    total_written += len(chunk)

        size_mb = total_written / (1024 * 1024)
        print(f"[absa_engine] Download selesai: {desc} ({size_mb:.2f} MB)")

        if not _is_valid_cached_file(dest_path, name):
            print(f"[absa_engine] ✗ File {desc} tidak valid setelah download ({total_written} bytes)")
            if os.path.exists(dest_path):
                os.remove(dest_path)
            return False

        return True

    except Exception as e:
        print(f"[absa_engine] ✗ Gagal download {desc}: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False

# ════════════════════════════════════════════════════════════════
# KONSTANTA
# ════════════════════════════════════════════════════════════════
PUNCT_SET  = set(string.punctuation)
UPOS_TAGS  = [
    'ADJ','ADP','ADV','AUX','CCONJ','DET','INTJ',
    'NOUN','NUM','PART','PRON','PROPN','PUNCT',
    'SCONJ','SYM','VERB','X','SPACE','UNK',
]
POS_VOCAB    = {tag: i for i, tag in enumerate(UPOS_TAGS)}
POS_UNK_IDX = POS_VOCAB['UNK']
POS_DIM      = len(UPOS_TAGS)

SENT_LABEL_MAP = {'positive': 0, 'negative': 1}
SENT_IDX_MAP   = {0: 'positive', 1: 'negative'}

NON_ASPECT_POS    = {'DET','CCONJ','PART','PRON','PUNCT','SPACE','SYM','ADP'}
WORK_ASPECT_WORDS = {'work','working','workspace','cowork','coworking'}
VERB_POS          = {'VERB','AUX'}
NON_ASPECT_DEP    = {
    'npadvmod','advmod','mark','aux','auxpass','expl',
    'det','cc','predet','quantmod','meta','punct','intj',
}
IMPORTANT_DEPS = {'compound','nsubj','amod','dobj','nmod','attr','pobj','conj','appos'}

# ════════════════════════════════════════════════════════════════
# HELPER
# ════════════════════════════════════════════════════════════════

def is_punct_token(tok: str) -> bool:
    return len(tok) > 0 and all(c in PUNCT_SET for c in tok)

def _is_non_aspect_pos(token_lower: str, pos_tag: str) -> bool:
    if pos_tag in NON_ASPECT_POS:
        return True
    if pos_tag in VERB_POS and token_lower not in WORK_ASPECT_WORDS:
        return True
    return False

def _is_non_aspect_dep(dep_tag: str) -> bool:
    return dep_tag.lower() in NON_ASPECT_DEP

def pos_tags_to_indices(pos_tags, pos_vocab, unk_idx, max_len):
    arr = np.zeros(max_len, dtype=np.int64)
    for i, tag in enumerate(pos_tags[:max_len]):
        arr[i] = pos_vocab.get(tag, unk_idx)
    return arr

# ════════════════════════════════════════════════════════════════
# ARSITEKTUR MODEL (identik dengan kode lama)
# ════════════════════════════════════════════════════════════════

class GatedGCNConv(nn.Module):
    def __init__(self, in_dim, out_dim):
        super().__init__()
        self.W_msg  = nn.Linear(in_dim, out_dim, bias=True)
        self.W_gate = nn.Linear(in_dim + out_dim, out_dim, bias=True)
        self.W_self = nn.Linear(in_dim, out_dim, bias=True)

    def forward(self, h, adj):
        msg  = torch.tanh(self.W_msg(torch.bmm(adj, h)))
        gate = torch.sigmoid(self.W_gate(torch.cat([h, msg], dim=-1)))
        return gate * msg + (1.0 - gate) * self.W_self(h)


class HighwayGate(nn.Module):
    def __init__(self, lstm_dim, gcn_dim, out_dim):
        super().__init__()
        self.W_T    = nn.Linear(lstm_dim + gcn_dim, out_dim, bias=True)
        self.W_lstm = nn.Linear(lstm_dim, out_dim, bias=False)
        self.W_gcn  = nn.Linear(gcn_dim, out_dim, bias=False)
        self.norm   = nn.LayerNorm(out_dim)
        nn.init.xavier_uniform_(self.W_T.weight)
        nn.init.constant_(self.W_T.bias, -1.0)

    def forward(self, h_lstm, h_gcn):
        T = torch.sigmoid(self.W_T(torch.cat([h_lstm, h_gcn], dim=-1)))
        return self.norm(T * self.W_gcn(h_gcn) + (1.0 - T) * self.W_lstm(h_lstm))


class ABSAModelAspect(nn.Module):
    def __init__(self, embed_dim, lstm_hidden, gcn_hidden, num_labels,
                 dropout=0.3, max_len=128, pos_vocab_size=19,
                 pos_embed_dim=32, label_smoothing=0.05,
                 label_to_catidx_tensor=None, num_cat_total=1):
        super().__init__()
        self.max_len    = max_len
        self.num_labels = num_labels
        self.num_cat    = num_cat_total
        if label_to_catidx_tensor is not None:
            self.register_buffer('label_to_cat', label_to_catidx_tensor)
        else:
            self.register_buffer('label_to_cat', torch.zeros(num_labels, dtype=torch.long))
        self.pos_embedding = nn.Embedding(pos_vocab_size, pos_embed_dim, padding_idx=0)
        bilstm_out = 2 * lstm_hidden
        self.bilstm = nn.LSTM(embed_dim + pos_embed_dim, lstm_hidden, num_layers=2,
                              batch_first=True, bidirectional=True, dropout=dropout)
        self.gcn1      = GatedGCNConv(bilstm_out, gcn_hidden)
        self.gcn2      = GatedGCNConv(gcn_hidden, gcn_hidden)
        self.fusion    = HighwayGate(bilstm_out, gcn_hidden, bilstm_out)
        self.dropout    = nn.Dropout(dropout)
        self.classifier = nn.Linear(bilstm_out, num_labels)
        self.criterion  = nn.CrossEntropyLoss(ignore_index=-1, label_smoothing=label_smoothing)

    def _encode(self, emb, pos_idx, adj):
        pos_emb   = self.pos_embedding(pos_idx)
        inp       = torch.cat([emb, pos_emb], dim=-1)
        h_lstm, _ = self.bilstm(inp)
        h_lstm    = self.dropout(h_lstm)
        h_gcn     = F.relu(self.gcn1(h_lstm, adj))
        h_gcn     = self.dropout(h_gcn)
        h_gcn     = F.relu(self.gcn2(h_gcn, adj))
        h_gcn     = self.dropout(h_gcn)
        return self.classifier(self.dropout(self.fusion(h_lstm, h_gcn)))

    @torch.no_grad()
    def predict(self, emb, pos_idx, adj, seq_lens):
        logits = self._encode(emb, pos_idx, adj)
        preds  = logits.argmax(dim=-1)
        return [preds[b, :int(seq_lens[b].item())].cpu().tolist()
                for b in range(preds.size(0))]


class SentimentModel(nn.Module):
    def __init__(self, embed_dim, lstm_hidden, gcn_hidden, num_labels,
                 dropout=0.3, max_len=128, pos_vocab_size=19,
                 pos_embed_dim=32, label_smoothing=0.05):
        super().__init__()
        self.max_len    = max_len
        self.num_labels = num_labels
        self.pos_embedding = nn.Embedding(pos_vocab_size, pos_embed_dim, padding_idx=0)
        bilstm_out = 2 * lstm_hidden
        self.bilstm = nn.LSTM(embed_dim + pos_embed_dim, lstm_hidden, num_layers=2,
                              batch_first=True, bidirectional=True, dropout=dropout)
        self.gcn1         = GatedGCNConv(bilstm_out, gcn_hidden)
        self.gcn2         = GatedGCNConv(gcn_hidden, gcn_hidden)
        self.fusion       = HighwayGate(bilstm_out, gcn_hidden, bilstm_out)
        self.context_gate = nn.Linear(bilstm_out * 2, bilstm_out, bias=True)
        self.dropout      = nn.Dropout(dropout)
        self.classifier   = nn.Linear(bilstm_out, num_labels)
        self.criterion    = nn.CrossEntropyLoss(label_smoothing=label_smoothing)

    def _encode(self, embeddings, pos_indices, adj, aspect_mask, seq_lens):
        pos_emb   = self.pos_embedding(pos_indices)
        inp       = torch.cat([embeddings, pos_emb], dim=-1)
        h_lstm, _ = self.bilstm(inp)
        h_lstm    = self.dropout(h_lstm)
        h_gcn     = F.relu(self.gcn1(h_lstm, adj))
        h_gcn     = self.dropout(h_gcn)
        h_gcn     = F.relu(self.gcn2(h_gcn, adj))
        h_gcn     = self.dropout(h_gcn)
        h_fused   = self.fusion(h_lstm, h_gcn)
        mask_sum   = aspect_mask.sum(dim=1, keepdim=True).clamp(min=1.0)
        aspect_rep = (h_fused * aspect_mask.unsqueeze(-1)).sum(dim=1) / mask_sum
        B, L, D = h_fused.shape
        seq_mask   = (torch.arange(L, device=h_fused.device).unsqueeze(0)
                      < seq_lens.unsqueeze(1)).float()
        global_rep = (h_fused * seq_mask.unsqueeze(-1)).sum(dim=1) / \
                     seq_mask.sum(dim=1, keepdim=True).clamp(min=1.0)
        gate      = torch.sigmoid(self.context_gate(
            torch.cat([aspect_rep, global_rep], dim=-1)))
        final_rep = gate * aspect_rep + (1.0 - gate) * global_rep
        return self.dropout(final_rep)

    @torch.no_grad()
    def predict(self, embeddings, pos_indices, adj, aspect_mask, seq_lens):
        rep    = self._encode(embeddings, pos_indices, adj, aspect_mask, seq_lens)
        logits = self.classifier(rep)
        probs  = torch.softmax(logits, dim=-1)
        preds  = logits.argmax(dim=-1)
        return preds.cpu().tolist(), probs.cpu().tolist()

# ════════════════════════════════════════════════════════════════
# LOAD GLOVE — mendukung Colab (lokal) dan Streamlit Cloud (download)
# ════════════════════════════════════════════════════════════════

# Cache global untuk Colab (tanpa @st.cache_resource agar tidak konflik)
_glove_cache = None

# ✅ GANTI: Hapus _glove_cache global, andalkan HANYA @st.cache_resource
@st.cache_resource(show_spinner=True)
def load_glove(dim: int = 300):
    embeddings = {}

    if _IS_COLAB:
        try:
            with open(COLAB_GLOVE_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    vals = line.rstrip().split(' ')
                    word = vals[0]
                    vec  = np.array(vals[1:], dtype=np.float32)
                    if len(vec) == dim:
                        embeddings[word] = vec
            print(f"[absa_engine] GloVe (Colab) loaded: {len(embeddings):,} vectors")
        except Exception as e:
            print(f"[absa_engine] Gagal load GloVe Colab: {e}")
    else:
        dest_path = _cached_path("glove", ".txt")
        # ✅ FIX: Paksa validasi ukuran file sebelum pakai cache
        if os.path.exists(dest_path):
            size = os.path.getsize(dest_path)
            if size < _MIN_FILE_SIZES["glove"]:
                print(f"[absa_engine] Cache GloVe invalid ({size} bytes), hapus dan re-download")
                os.remove(dest_path)
        
        ok = _download_gdrive_file(_GDRIVE_IDS["glove"], dest_path, "GloVe embeddings", "glove")
        if ok:
            try:
                with open(dest_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        vals = line.rstrip().split(' ')
                        word = vals[0]
                        vec  = np.array(vals[1:], dtype=np.float32)
                        if len(vec) == dim:
                            embeddings[word] = vec
                print(f"[absa_engine] GloVe (Cloud) loaded: {len(embeddings):,} vectors")
            except Exception as e:
                print(f"[absa_engine] Gagal parse GloVe Cloud: {e}")

    # ✅ GANTI DENGAN ini — fallback tapi dengan warning yang jelas:
    if not embeddings:
        print("[absa_engine] ⚠️ GloVe kosong — kemungkinan download gagal atau file korup")
        print("[absa_engine] Coba hapus cache di /tmp/absa_cache/ dan restart app")
        # Fallback minimal dengan kata-kata paling kritis
        # Ini TIDAK akurat tapi mencegah crash total
        _critical_words = [
            'food','coffee','service','place','staff','good','bad','delicious',
            'clean','comfortable','taste','wifi','parking','atmosphere','price',
            'menu','ambience','waiter','seat','location','music','toilet',
            'dessert','drink','beverage','snack','quality','portion','wait',
            'fast','slow','friendly','rude','cozy','noisy','quiet','crowded',
            'recommend','excellent','terrible','amazing','awful','nice','dirty',
            'hot','cold','fresh','stale','cheap','expensive','worth','value',
        ]
        np.random.seed(42)
        for w in _critical_words:
            np.random.seed(abs(hash(w)) % (2**31))
            embeddings[w] = np.random.randn(dim).astype(np.float32)
        print(f"[absa_engine] Fallback: {len(embeddings)} kata kritis dengan random embedding")
    
    mean_vec = np.mean(list(embeddings.values()), axis=0)
    return embeddings, mean_vec

# ════════════════════════════════════════════════════════════════
# LOAD MODEL — mendukung Colab (lokal) dan Streamlit Cloud (download)
# ════════════════════════════════════════════════════════════════

def _load_state_dict(path: str, device):
    """Load state dict dengan kompatibilitas PyTorch lama/baru."""
    try:
        major = int(torch.__version__.split('.')[0])
        if major >= 2:
            return torch.load(path, map_location=device, weights_only=True)
        else:
            return torch.load(path, map_location=device)
    except Exception:
        return torch.load(path, map_location=device)

def _load_json_file(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"[absa_engine] Gagal baca JSON {path}: {e}")
        return {}

def _get_json_cloud(file_id: str, name: str) -> dict:
    dest_path = _cached_path(name, ".json")
    ok = _download_gdrive_file(file_id, dest_path, name, name)
    if not ok:
        return {}
    return _load_json_file(dest_path)

def _get_pth_cloud(file_id: str, name: str, device):
    dest_path = _cached_path(name, ".pth")
    ok = _download_gdrive_file(file_id, dest_path, name, name)
    if not ok:
        return None
    return _load_state_dict(dest_path, device)


@st.cache_resource(show_spinner=False)
def load_aspect_model_engine():
    """
    Load aspect model + config.
    Return: (model, cfg) atau (None, None) jika gagal.
    """
    device = torch.device('cpu')

    # Load config
    if _IS_COLAB:
        cfg = _load_json_file(COLAB_ASP_CFG)
    else:
        cfg = _get_json_cloud(_GDRIVE_IDS["asp_config"], "absa_config")

    if not cfg:
        print("[absa_engine] Aspect config tidak tersedia")
        return None, None

    required_keys = ['num_labels','embedding_dim','lstm_hidden','gcn_hidden',
                     'dropout','max_len','bio_label_map']
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        print(f"[absa_engine] Config aspect kekurangan keys: {missing}")
        return None, None

    print(f"[absa_engine] Aspect config: num_labels={cfg['num_labels']}, "
          f"max_len={cfg['max_len']}, categories={cfg.get('categories', [])[:5]}")

    label_to_cat = torch.zeros(cfg['num_labels'], dtype=torch.long)
    try:
        m = ABSAModelAspect(
            embed_dim              = cfg['embedding_dim'],
            lstm_hidden            = cfg['lstm_hidden'],
            gcn_hidden             = cfg['gcn_hidden'],
            num_labels             = cfg['num_labels'],
            dropout                = cfg['dropout'],
            max_len                = cfg['max_len'],
            pos_vocab_size         = cfg.get('pos_dim', POS_DIM),
            pos_embed_dim          = cfg.get('pos_embed_dim', 32),
            label_to_catidx_tensor = label_to_cat,
            num_cat_total          = cfg.get('num_cat_total', 2),
        ).to(device)

        if _IS_COLAB:
            sd = _load_state_dict(COLAB_ASP_MODEL, device)
        else:
            sd = _get_pth_cloud(_GDRIVE_IDS["asp_model"], "absa_model", device)

        if sd is None:
            print("[absa_engine] State dict aspect gagal load")
            return None, None

        m.load_state_dict(sd, strict=True)
        m.eval()
        print("[absa_engine] Aspect model loaded OK ✓")
        return m, cfg
    except Exception as e:
        print(f"[absa_engine] Gagal inisialisasi aspect model: {e}")
        import traceback
        traceback.print_exc()
        return None, None


@st.cache_resource(show_spinner=False)
def load_sent_model_engine():
    """
    Load sentiment model + config.
    Return: (model, cfg) atau (None, None) jika gagal.
    """
    device = torch.device('cpu')

    if _IS_COLAB:
        cfg = _load_json_file(COLAB_SENT_CFG)
    else:
        cfg = _get_json_cloud(_GDRIVE_IDS["sent_config"], "absa_sentiment_config_v2")

    if not cfg:
        print("[absa_engine] Sentiment config tidak tersedia")
        return None, None

    required_keys = ['num_sent_labels','embedding_dim','lstm_hidden','gcn_hidden',
                     'dropout','max_len']
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        print(f"[absa_engine] Config sentiment kekurangan keys: {missing}")
        return None, None

    print(f"[absa_engine] Sentiment config: num_sent_labels={cfg['num_sent_labels']}, "
          f"max_len={cfg['max_len']}")

    try:
        m = SentimentModel(
            embed_dim      = cfg['embedding_dim'],
            lstm_hidden    = cfg['lstm_hidden'],
            gcn_hidden     = cfg['gcn_hidden'],
            num_labels     = cfg['num_sent_labels'],
            dropout        = cfg['dropout'],
            max_len        = cfg['max_len'],
            pos_vocab_size = cfg.get('pos_dim', POS_DIM),
            pos_embed_dim  = cfg.get('pos_embed_dim', 32),
        ).to(device)

        if _IS_COLAB:
            sd = _load_state_dict(COLAB_SENT_MODEL, device)
        else:
            sd = _get_pth_cloud(_GDRIVE_IDS["sent_model"], "absa_sentiment_model_v2", device)

        if sd is None:
            print("[absa_engine] State dict sentiment gagal load")
            return None, None

        m.load_state_dict(sd)
        m.eval()
        print("[absa_engine] Sentiment model loaded OK ✓")
        return m, cfg
    except Exception as e:
        print(f"[absa_engine] Gagal inisialisasi sentiment model: {e}")
        import traceback
        traceback.print_exc()
        return None, None


@st.cache_data(show_spinner=False, ttl=600)
def load_konversi_df() -> pd.DataFrame:
    """
    Load df_konversi.
    Colab    : baca dari file .xlsx lokal
    Streamlit: baca dari Google Sheets via gsheets_client
    """
    try:
        if _IS_COLAB:
            df = pd.read_excel(COLAB_KONVERSI)
        else:
            from gsheets_client import read_sheet_as_df
            df = read_sheet_as_df("df_konversi")
            if df.empty:
                raise ValueError("df_konversi sheet kosong")

        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
        required   = ['category', 'category_aspect_kafe', 'aspect_condition']
        missing    = [c for c in required if c not in df.columns]
        if missing:
            print(f"[absa_engine] df_konversi kolom tidak lengkap: {missing}")

        df['_cat_norm'] = (df['category'].astype(str)
                           .str.lower().str.strip()
                           .str.replace(r'[\s\-_/]+', '_', regex=True))

        if 'sentiment' in df.columns:
            df['_sent_norm'] = df['sentiment'].astype(str).str.lower().str.strip()
        else:
            df['_sent_norm'] = ''

        if 'skor_sentimen' in df.columns:
            df['skor_sentimen'] = pd.to_numeric(df['skor_sentimen'], errors='coerce').fillna(0)
        else:
            df['skor_sentimen'] = 0

        print(f"[absa_engine] df_konversi loaded: {len(df)} rows, "
              f"categories: {sorted(df['category'].unique().tolist())[:10]}")
        return df

    except Exception as e:
        print(f"[absa_engine] Gagal load df_konversi: {e}")
        return pd.DataFrame(
            columns=['category','category_aspect_kafe','aspect_condition',
                     '_cat_norm','_sent_norm','skor_sentimen']
        )

# ════════════════════════════════════════════════════════════════
# TRANSLATE
# [FIX-5] source='auto' (seperti kode lama) + heuristik ID yang akurat
# ════════════════════════════════════════════════════════════════

_ID_KEYWORDS = {
    'yang','dan','di','ke','dari','dengan','untuk','tidak','bisa','ada',
    'ini','itu','kafe','enak','bagus','jelek','makanan','minuman','tempat',
    'pelayanan','harga','sangat','banget','juga','sudah','baru','lagi',
    'suka','puas','nyaman','bersih','kotor','mahal','murah','cepat','lama',
    'ramah','kasar','biasa','oke','mantap','top','keren',
    'mau','meja','kursi','wifi','parkir','suasana','rasa',
    'porsi','menu','kopi','teh',
}

def translate_to_english(text: str) -> str:
    """
    Terjemahkan ke bahasa Inggris.
    [FIX-5] Menggunakan source='auto' seperti kode lama.
    Tidak pernah raise exception.
    """
    if not text or not text.strip():
        return text
    original = text.strip()

    # Heuristik: cek apakah teks mengandung kata-kata Indonesia
    words_lower = set(original.lower().split())
    has_id_words = bool(words_lower & _ID_KEYWORDS)

    # Jika semua karakter ASCII dan tidak ada kata Indonesia → kemungkinan sudah English
    alpha_chars = [c for c in original if c.isalpha()]
    if alpha_chars and all(ord(c) < 128 for c in alpha_chars) and not has_id_words:
        print(f"[absa_engine] Teks tampak sudah English, skip translate")
        return original

    print(f"[absa_engine] Mencoba translate: '{original[:50]}'")

    # Coba deep_translator dengan source='auto' (seperti kode lama)
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source='auto', target='en').translate(original)
        if result and result.strip() and result.strip() != original:
            print(f"[absa_engine] Translate OK (deep_translator): "
                  f"'{original[:40]}' → '{result[:40]}'")
            return result.strip()
    except Exception as e:
        print(f"[absa_engine] deep_translator gagal: {e}")

    # Coba googletrans dengan source='auto' (seperti kode lama)
    try:
        from googletrans import Translator
        tr     = Translator()
        result = tr.translate(original, dest='en')
        if result and result.text and result.text.strip() and result.text.strip() != original:
            print(f"[absa_engine] Translate OK (googletrans): "
                  f"'{original[:40]}' → '{result.text[:40]}'")
            return result.text.strip()
    except Exception as e:
        print(f"[absa_engine] googletrans gagal: {e}")

    print(f"[absa_engine] Semua translator gagal, pakai teks asli")
    return original

# ════════════════════════════════════════════════════════════════
# TOKENISASI — identik dengan kode lama
# [FIX-4] HANYA filter punctuation murni, TIDAK ada filter ekstra
#         (tidak ada len(t) > 1, tidak ada isalpha(), tidak ada ASCII filter)
# ════════════════════════════════════════════════════════════════

def _tokenize_text(text: str):
    """
    Tokenisasi teks. Coba spaCy dulu, fallback ke split sederhana.
    [FIX-4] Filter HANYA punctuation, tidak ada filter tambahan.
    Identik dengan kode lama.
    Returns: (list of token strings, doc or None)
    """
    nlp = _get_nlp()
    if nlp is not None:
        doc = nlp(text.lower())
        tokens = [tok.text for tok in doc if not is_punct_token(tok.text)]
        return tokens, doc
    else:
        raw_tokens = text.lower().split()
        tokens = []
        for t in raw_tokens:
            t_clean = t.strip(string.punctuation)
            if t_clean and not is_punct_token(t_clean):
                tokens.append(t_clean)
        return tokens, None

# ════════════════════════════════════════════════════════════════
# DEPENDENCY GRAPH — dari valid_tokens langsung (FIX BUG #3 kode lama)
# [FIX-3] Fallback = identity matrix (seperti kode lama),
#         BUKAN window adjacency
# ════════════════════════════════════════════════════════════════

def build_adj_from_tokens(valid_tokens: list, max_len: int = 128) -> np.ndarray:
    """
    Bangun adjacency matrix ternormalisasi dari valid_tokens.
    [FIX-3] Fallback ke identity matrix saat spaCy tidak tersedia.
    Identik dengan kode lama (Bug #3 fix dari kode lama).
    """
    nlp = _get_nlp()
    n   = min(len(valid_tokens), max_len)
    if n == 0:
        return np.eye(1, dtype=np.float32)

    adj = np.eye(n, dtype=np.float32)

    if nlp is None:
        # [FIX-3] Identity matrix saja — seperti kode lama
        D       = adj.sum(axis=1)
        D_isqrt = np.where(D > 0, D ** -0.5, 0.0)
        return ((D_isqrt[:, None] * adj) * D_isqrt[None, :]).astype(np.float32)

    # Bergabung kembali token agar spaCy parse dengan konteks sintaksis
    text_from_tokens = ' '.join(str(t) for t in valid_tokens[:n])
    doc = nlp(text_from_tokens)
    doc_tokens = [tok.text for tok in doc]

    if len(doc_tokens) == n:
        # Kasus ideal: jumlah token sama persis
        for tok in doc:
            if tok.i >= n:
                continue
            for child in tok.children:
                if child.i >= n:
                    continue
                w = 1.0 if child.dep_ in IMPORTANT_DEPS else 0.5
                adj[tok.i, child.i] = max(adj[tok.i, child.i], w)
                adj[child.i, tok.i] = max(adj[child.i, tok.i], w)
    else:
        # [FIX-3] Jumlah token berbeda → pakai identity (seperti kode lama)
        print(f"[absa_engine] Token mismatch: valid={n}, spaCy={len(doc_tokens)}, "
              f"pakai identity adj")

    # Normalisasi D^{-1/2} A D^{-1/2}
    D       = adj.sum(axis=1)
    D_isqrt = np.where(D > 0, D ** -0.5, 0.0)
    return ((D_isqrt[:, None] * adj) * D_isqrt[None, :]).astype(np.float32)


def get_pos_tags_local(tokens: list) -> list:
    """Ambil POS tags. Fallback ke 'NOUN' jika spaCy tidak ada."""
    nlp = _get_nlp()
    if nlp is None:
        return ['NOUN'] * len(tokens)
    text = ' '.join(str(t) for t in tokens)
    doc  = nlp(text)
    if len(doc) == len(tokens):
        return [tok.pos_ or 'UNK' for tok in doc]
    result = []
    for raw in tokens:
        sub = nlp(str(raw))
        result.append(sub[0].pos_ if sub and sub[0].pos_ else 'NOUN')
    return result


def get_dep_tags_local(tokens: list) -> list:
    """Ambil DEP tags. Fallback ke 'dep' jika spaCy tidak ada."""
    nlp = _get_nlp()
    if nlp is None:
        return ['dep'] * len(tokens)
    text = ' '.join(str(t) for t in tokens)
    doc  = nlp(text)
    if len(doc) == len(tokens):
        return [tok.dep_.lower() if tok.dep_ else 'dep' for tok in doc]
    result = []
    for raw in tokens:
        sub = nlp(str(raw))
        result.append(sub[0].dep_.lower() if sub and sub[0].dep_ else 'dep')
    return result

# ════════════════════════════════════════════════════════════════
# BIO CONSTRAINED DECODE
# [FIX-1] int() casting KONSISTEN — semua key i_to_b/b_to_i adalah int
# [FIX-2] Filter heuristik DIHAPUS — hanya filter POS/DEP dari spaCy
# ════════════════════════════════════════════════════════════════

def bio_constrained_decode_engine(pred_ids, bio_idx_map, i_to_b, b_to_i,
                                   tokens=None, pos_tags=None, dep_tags=None):
    """
    BIO constrained decode.
    [FIX-1] pred_ids adalah int, bio_idx_map key adalah int,
            i_to_b dan b_to_i key/value adalah int — SEMUA KONSISTEN.
    [FIX-2] Filter POS heuristik (_is_non_aspect_word_heuristic) DIHAPUS.
            Hanya filter POS/DEP dari spaCy yang akurat.
    Identik dengan kode lama dalam logika filter.
    """
    corrected   = list(pred_ids)
    cur_cat_idx = None

    # Pass 1: Koreksi I- tanpa B- sebelumnya dan kategori mismatch
    for i, pred in enumerate(corrected):
        lbl = bio_idx_map.get(pred, 'O')
        if lbl == 'O':
            cur_cat_idx = None
        elif lbl.startswith('B-'):
            cur_cat_idx = pred
        elif lbl.startswith('I-'):
            if cur_cat_idx is None:
                b_idx = i_to_b.get(pred)          # int → int
                corrected[i] = b_idx if b_idx is not None else 0
                cur_cat_idx  = corrected[i]
            else:
                actual_b = i_to_b.get(pred)        # int → int
                if actual_b != cur_cat_idx:
                    correct_i    = b_to_i.get(cur_cat_idx)  # int → int
                    corrected[i] = correct_i if correct_i is not None else 0
                cur_cat_idx = corrected[i]

    # Pass 2: Merge B-X B-X → B-X I-X
    for i in range(1, len(corrected)):
        lp = bio_idx_map.get(corrected[i-1], 'O')
        lc = bio_idx_map.get(corrected[i],   'O')
        if lp.startswith('B-') and lc.startswith('B-') and lp[2:] == lc[2:]:
            ci = b_to_i.get(corrected[i-1])     # int → int
            if ci is not None:
                corrected[i] = ci

    # Pass 3: Filter POS — HANYA jika spaCy tersedia (pos_tags dari spaCy)
    # [FIX-2] Tidak ada lagi heuristik _is_non_aspect_word_heuristic
    nlp_available = _get_nlp() is not None

    if nlp_available and pos_tags and tokens:
        for i in range(len(corrected)):
            lbl = bio_idx_map.get(corrected[i], 'O')
            if lbl == 'O' or 'SENT' in lbl:
                continue
            if not (lbl.startswith('B-') or lbl.startswith('I-')):
                continue
            pos_i = pos_tags[i] if i < len(pos_tags) else 'UNK'
            tok_i = str(tokens[i]).lower() if i < len(tokens) else ''
            if _is_non_aspect_pos(tok_i, pos_i):
                corrected[i] = 0

    # Pass 4: Filter DEP — hanya jika spaCy tersedia
    if nlp_available and dep_tags and tokens:
        for i in range(len(corrected)):
            lbl = bio_idx_map.get(corrected[i], 'O')
            if lbl == 'O' or 'SENT' in lbl:
                continue
            if not lbl.startswith('B-'):
                continue
            dep_i = dep_tags[i].lower() if i < len(dep_tags) else 'dep'
            if _is_non_aspect_dep(dep_i):
                corrected[i] = 0
                j = i + 1
                while j < len(corrected):
                    lbl_j = bio_idx_map.get(corrected[j], 'O')
                    if lbl_j.startswith('I-') and 'SENT' not in lbl_j:
                        b_idx = i_to_b.get(corrected[j])    # int → int
                        if b_idx is not None:
                            corrected[j] = b_idx
                        break
                    else:
                        break
                    j += 1

    return corrected


def extract_aspect_spans_engine(tokens, corrected_ids, bio_idx_map):
    """Ekstrak span aspek dari corrected_ids. Identik dengan kode lama."""
    aspects, cur_tokens, cur_cat, cur_start = [], [], None, -1
    for i, pred in enumerate(corrected_ids):
        lbl = bio_idx_map.get(pred, 'O')
        if lbl.startswith('B-') and 'SENT' not in lbl:
            if cur_tokens and cur_cat:
                aspects.append({'aspect': ' '.join(cur_tokens), 'category': cur_cat,
                                 'start': cur_start, 'end': i})
            cur_tokens = [tokens[i]] if i < len(tokens) else []
            cur_start  = i
            cur_cat    = lbl[2:]
        elif lbl.startswith('I-') and 'SENT' not in lbl and cur_start >= 0:
            if i < len(tokens):
                cur_tokens.append(tokens[i])
        else:
            if cur_tokens and cur_cat:
                aspects.append({'aspect': ' '.join(cur_tokens), 'category': cur_cat,
                                 'start': cur_start, 'end': i})
            cur_tokens, cur_cat, cur_start = [], None, -1
    if cur_tokens and cur_cat:
        aspects.append({'aspect': ' '.join(cur_tokens), 'category': cur_cat,
                        'start': cur_start, 'end': len(corrected_ids)})
    seen, out = set(), []
    for a in aspects:
        k = (a['aspect'].lower().strip(), a['category'])
        if k not in seen:
            seen.add(k)
            out.append(a)
    return out

# ════════════════════════════════════════════════════════════════
# KONVERSI ASPEK → FORMAT KAFE
# Identik dengan kode lama — multiple strategy matching
# ════════════════════════════════════════════════════════════════

def _normalize_cat(cat_str: str) -> str:
    return (str(cat_str).lower().strip()
            .replace('-', '_').replace(' ', '_').replace('/', '_'))


def convert_aspects_to_kafe_format(aspects_with_sentiment: list) -> pd.DataFrame:
    """
    Input : list of dict {aspect, category, sentiment, confidence}
    Output: pd.DataFrame format kafe

    Strategi matching (urutan prioritas, identik kode lama):
    1. Exact match setelah normalisasi
    2. Partial: category model ada dalam category konversi
    3. Partial: category konversi ada dalam category model
    4. Fallback: pakai category mentah
    """
    if not aspects_with_sentiment:
        return pd.DataFrame(columns=['aspect','category','category_aspect_kafe',
                                     'category_aspect_term','aspect_condition',
                                     'sentimen','skor_sentimen','confidence'])

    df_konv = load_konversi_df()
    rows    = []

    for asp in aspects_with_sentiment:
        cat  = str(asp.get("category", "")).strip()
        sent = str(asp.get("sentiment", "positive")).strip().lower()
        conf = float(asp.get("confidence", 0))

        cat_norm     = _normalize_cat(cat)
        sent_norm    = sent
        skor_default = 1.0 if sent_norm == 'positive' else 0.0

        if df_konv.empty or '_cat_norm' not in df_konv.columns:
            rows.append({
                'aspect': asp.get('aspect', ''), 'category': cat,
                'category_aspect_kafe': cat, 'category_aspect_term': cat,
                'aspect_condition': cat, 'sentimen': sent_norm,
                'skor_sentimen': skor_default, 'confidence': conf,
            })
            continue

        # Strategi 1: exact match
        match = df_konv[df_konv['_cat_norm'] == cat_norm]

        # Strategi 2: partial — cat_norm ada dalam nilai konversi
        if match.empty:
            match = df_konv[df_konv['_cat_norm'].str.contains(
                cat_norm, na=False, regex=False)]

        # Strategi 3: partial — nilai konversi ada dalam cat_norm
        if match.empty:
            match = df_konv[df_konv['_cat_norm'].apply(
                lambda x: bool(x) and x in cat_norm)]

        if match.empty:
            rows.append({
                'aspect': asp.get('aspect', ''), 'category': cat,
                'category_aspect_kafe': cat, 'category_aspect_term': cat,
                'aspect_condition': cat, 'sentimen': sent_norm,
                'skor_sentimen': skor_default, 'confidence': conf,
            })
            continue

        # Filter berdasarkan sentiment jika kolom ada
        if '_sent_norm' in match.columns:
            match_sent = match[match['_sent_norm'] == sent_norm]
            if not match_sent.empty:
                match = match_sent

        row_k    = match.iloc[0]
        cat_kafe = str(row_k.get('category_aspect_kafe', cat))
        asp_cond = str(row_k.get('aspect_condition', cat))
        cat_term = str(row_k.get('category', cat))
        # Selalu gunakan prediksi model, bukan dari df_konversi
        # positive → 1, negative → 0
        skor = 1.0 if sent_norm == 'positive' else 0.0
        
        rows.append({
            'aspect': asp.get('aspect', ''), 'category': cat,
            'category_aspect_kafe': cat_kafe, 'category_aspect_term': cat_term,
            'aspect_condition': asp_cond, 'sentimen': sent_norm,
            'skor_sentimen': skor, 'confidence': conf,
        })

    return pd.DataFrame(rows)

# ════════════════════════════════════════════════════════════════
# INFERENCE SATU REVIEW — PERBAIKAN UTAMA
# [FIX-1] BIO map int() casting konsisten
# [FIX-2] Filter heuristik dihapus
# [FIX-3] Adj dari valid_tokens langsung (sama dengan kode lama Bug#3 fix)
# [FIX-4] Token filter hanya punctuation
# ════════════════════════════════════════════════════════════════

def analyze_single_review(review_text: str, device=None) -> list:
    """
    Analisis satu review (sudah dalam bahasa Inggris).
    Return: list of dict [{aspect, category, sentiment, confidence}, ...]

    Alur tokenisasi BENAR (sama dengan kode lama Bug#3 fix):
      1. Tokenisasi TUNGGAL → valid_tokens (filter punctuation saja)
      2. Build adj dari valid_tokens yang SAMA
      3. POS dan DEP dari valid_tokens yang SAMA
      4. Embedding dari valid_tokens yang SAMA
      5. Semua array menggunakan indeks yang konsisten
    """
    if device is None:
        device = torch.device('cpu')

    glove, mean_vec = load_glove()

    asp_model, asp_cfg = load_aspect_model_engine()
    if asp_model is None:
        print("[absa_engine] ✗ Aspect model tidak tersedia")
        return []

    sent_model_obj, sent_cfg = load_sent_model_engine()
    if sent_model_obj is None:
        print("[absa_engine] ✗ Sentiment model tidak tersedia")
        return []

    # ── [FIX-1] BIO maps — int() casting KONSISTEN di semua key/value ──
    bio_lbl_map = asp_cfg.get('bio_label_map', {})
    if not bio_lbl_map:
        print("[absa_engine] ✗ bio_label_map kosong!")
        return []

    # bio_idx_map: int(label_id) → label_string
    bio_idx_map = {int(v): k for k, v in bio_lbl_map.items()}

    # [FIX-1] i_to_b dan b_to_i: SEMUA key dan value harus int
    # raw_preds dari model.predict() sudah int
    # bio_lbl_map values bisa string "0","1",... → int() WAJIB
    i_to_b, b_to_i = {}, {}
    for cat_name in asp_cfg.get('categories', []):
        b_key = f'B-{cat_name}'
        i_key = f'I-{cat_name}'
        if b_key in bio_lbl_map and i_key in bio_lbl_map:
            b_idx = int(bio_lbl_map[b_key])
            i_idx = int(bio_lbl_map[i_key])
            i_to_b[i_idx] = b_idx    # int key → int value
            b_to_i[b_idx] = i_idx    # int key → int value

    if 'B-SENT' in bio_lbl_map and 'I-SENT' in bio_lbl_map:
        b_sent = int(bio_lbl_map['B-SENT'])
        i_sent = int(bio_lbl_map['I-SENT'])
        i_to_b[i_sent] = b_sent
        b_to_i[b_sent] = i_sent

    asp_max_len  = asp_cfg.get('max_len', 128)
    sent_max_len = sent_cfg.get('max_len', 128)
    embed_dim    = asp_cfg.get('embedding_dim', 300)

    # ── LANGKAH 1: Tokenisasi TUNGGAL [FIX-4] ────────────────────
    text = review_text.strip()
    # [FIX-4] Gunakan _tokenize_text yang hanya filter punctuation
    valid_tokens, _ = _tokenize_text(text)

    n_valid = len(valid_tokens)
    if n_valid == 0:
        print(f"[absa_engine] Teks kosong setelah tokenisasi: '{text[:60]}'")
        return []

    print(f"[absa_engine] Analisis ({n_valid} tokens): {valid_tokens[:10]}...")

    # ── LANGKAH 2: Build adj dari valid_tokens [FIX-3] ──────────
    asp_sl = min(n_valid, asp_max_len)
    adj_norm = build_adj_from_tokens(valid_tokens[:asp_sl], max_len=asp_sl)

    adj_full_padded = np.zeros((asp_max_len, asp_max_len), dtype=np.float32)
    adj_full_padded[:asp_sl, :asp_sl] = adj_norm[:asp_sl, :asp_sl]

    # ── LANGKAH 3: POS dan DEP dari valid_tokens yang SAMA ───────
    pos_tags = get_pos_tags_local(valid_tokens[:asp_sl])
    dep_tags = get_dep_tags_local(valid_tokens[:asp_sl])

    # ── LANGKAH 4: Embedding dari valid_tokens yang SAMA ─────────
    asp_pos_vocab = asp_cfg.get('pos_vocab', POS_VOCAB)
    asp_pos_pu    = asp_pos_vocab.get('UNK', POS_UNK_IDX)

    asp_emb = np.zeros((asp_max_len, embed_dim), dtype=np.float32)
    found_in_glove = 0
    for i in range(asp_sl):
        tok = valid_tokens[i].lower()
        if tok in glove:
            asp_emb[i] = glove[tok]
            found_in_glove += 1
        else:
            asp_emb[i] = mean_vec

    print(f"[absa_engine] GloVe coverage: {found_in_glove}/{asp_sl} tokens")

    asp_pi = pos_tags_to_indices(pos_tags, asp_pos_vocab, asp_pos_pu, asp_max_len)

    # ── LANGKAH 5: Aspect model predict ──────────────────────────
    asp_et = torch.tensor(asp_emb,         dtype=torch.float32).unsqueeze(0).to(device)
    asp_pt = torch.tensor(asp_pi,          dtype=torch.long).unsqueeze(0).to(device)
    asp_at = torch.tensor(adj_full_padded, dtype=torch.float32).unsqueeze(0).to(device)
    asp_st = torch.tensor([asp_sl],        dtype=torch.long).to(device)

    with torch.no_grad():
        raw_preds = asp_model.predict(asp_et, asp_pt, asp_at, asp_st)[0][:asp_sl]

    # Debug log
    from collections import Counter
    pred_counter = Counter(raw_preds)
    print(f"[absa_engine] Raw predictions (label_idx: count): {dict(pred_counter)}")
    non_O = [(bio_idx_map.get(p, 'O'), valid_tokens[i])
             for i, p in enumerate(raw_preds) if bio_idx_map.get(p, 'O') != 'O']
    print(f"[absa_engine] Non-O predictions: {non_O}")

    # ── LANGKAH 6: BIO constrained decode [FIX-1][FIX-2] ────────
    # raw_preds sudah int, bio_idx_map key int, i_to_b/b_to_i key int
    corrected = bio_constrained_decode_engine(
        raw_preds, bio_idx_map, i_to_b, b_to_i,
        tokens   = valid_tokens[:asp_sl],
        pos_tags = pos_tags[:asp_sl],
        dep_tags = dep_tags[:asp_sl],
    )

    non_O_after = [(bio_idx_map.get(p, 'O'), valid_tokens[i])
                   for i, p in enumerate(corrected)
                   if bio_idx_map.get(p, 'O') != 'O']
    print(f"[absa_engine] Non-O setelah BIO decode: {non_O_after}")

    # ── LANGKAH 7: Extract spans ──────────────────────────────────
    aspects_raw = extract_aspect_spans_engine(valid_tokens[:asp_sl], corrected, bio_idx_map)
    print(f"[absa_engine] Aspek diekstrak: {aspects_raw}")

    if not aspects_raw:
        print("[absa_engine] Tidak ada aspek terdeteksi untuk review ini")
        return []

    # ── LANGKAH 8: Sentiment model ───────────────────────────────
    sent_sl        = min(n_valid, sent_max_len)
    sent_pos_vocab = sent_cfg.get('pos_vocab', POS_VOCAB)
    sent_pos_pu    = sent_pos_vocab.get('UNK', POS_UNK_IDX)

    if sent_max_len == asp_max_len:
        sent_adj_padded = adj_full_padded
    else:
        _sn = min(n_valid, sent_max_len)
        _adj_n = build_adj_from_tokens(valid_tokens[:_sn], max_len=_sn)
        sent_adj_padded = np.zeros((sent_max_len, sent_max_len), dtype=np.float32)
        sent_adj_padded[:_sn, :_sn] = _adj_n[:_sn, :_sn]

    sent_emb = np.zeros((sent_max_len, embed_dim), dtype=np.float32)
    for i in range(sent_sl):
        tok = valid_tokens[i].lower()
        sent_emb[i] = glove.get(tok, mean_vec)

    sent_pi = pos_tags_to_indices(
        get_pos_tags_local(valid_tokens[:sent_sl]),
        sent_pos_vocab, sent_pos_pu, sent_max_len
    )

    emb_t = torch.tensor(sent_emb,        dtype=torch.float32).unsqueeze(0).to(device)
    pos_t = torch.tensor(sent_pi,         dtype=torch.long).unsqueeze(0).to(device)
    adj_t = torch.tensor(sent_adj_padded, dtype=torch.float32).unsqueeze(0).to(device)
    sl_t  = torch.tensor([sent_sl],       dtype=torch.long).to(device)

    results = []
    for asp in aspects_raw:
        asp_mask = np.zeros(sent_max_len, dtype=np.float32)
        for p in range(asp['start'], min(asp['end'], sent_max_len)):
            asp_mask[p] = 1.0
        if asp_mask.sum() == 0 and asp['start'] < sent_max_len:
            asp_mask[asp['start']] = 1.0

        mask_t = torch.tensor(asp_mask, dtype=torch.float32).unsqueeze(0).to(device)
        with torch.no_grad():
            preds, probs = sent_model_obj.predict(emb_t, pos_t, adj_t, mask_t, sl_t)

        pred_label = preds[0]
        confidence = round(probs[0][pred_label] * 100, 1)
        results.append({
            'aspect'    : asp['aspect'],
            'category'  : asp['category'],
            'sentiment' : SENT_IDX_MAP[pred_label],
            'confidence': confidence,
        })

    print(f"[absa_engine] Final results: {results}")
    return results

# ════════════════════════════════════════════════════════════════
# PIPELINE UTAMA
# [FIX-6] _source_review ditambahkan ke setiap aspek (seperti kode lama)
# ════════════════════════════════════════════════════════════════

def run_analysis_pipeline(reviews: list, translate: bool = True) -> dict:
    """
    Input : list of str (review teks)
    Output: dict {raw_aspects: list, df_converted: pd.DataFrame}

    [FIX-6] _source_review ditambahkan ke setiap aspek sebelum extend,
            identik dengan kode lama.
    """
    device      = torch.device('cpu')
    all_aspects = []

    # Pre-check model
    print(f"[absa_engine] Memulai pipeline untuk {len(reviews)} review...")
    asp_model, asp_cfg = load_aspect_model_engine()
    sent_model_obj, sent_cfg = load_sent_model_engine()
    glove, mean_vec = load_glove()

    if asp_model is None:
        print("[absa_engine] ✗ Aspect model gagal — pipeline berhenti")
        return {"raw_aspects": [], "df_converted": pd.DataFrame()}

    if sent_model_obj is None:
        print("[absa_engine] ✗ Sentiment model gagal — pipeline berhenti")
        return {"raw_aspects": [], "df_converted": pd.DataFrame()}

    print(f"[absa_engine] Model OK. GloVe vocab: {len(glove):,} words")

    for idx, rev in enumerate(reviews):
        text = rev.strip()
        if not text:
            continue

        print(f"\n[absa_engine] === Review {idx+1}/{len(reviews)} ===")
        print(f"[absa_engine] Original: '{text[:80]}'")

        if translate:
            text_en = translate_to_english(text)
            print(f"[absa_engine] Translated: '{text_en[:80]}'")
        else:
            text_en = text

        try:
            asp_list = analyze_single_review(text_en, device=device)
        except Exception as e:
            print(f"[absa_engine] ✗ Error review {idx+1}: {e}")
            import traceback
            traceback.print_exc()
            asp_list = []

        # [FIX-6] Tambahkan _source_review (teks asli, bukan terjemahan)
        for asp in asp_list:
            asp['_source_review'] = text  # identik dengan kode lama

        all_aspects.extend(asp_list)
        print(f"[absa_engine] Review {idx+1}: {len(asp_list)} aspek terdeteksi")

    print(f"\n[absa_engine] === SELESAI: {len(all_aspects)} aspek "
          f"dari {len(reviews)} review ===")

    df_conv = convert_aspects_to_kafe_format(all_aspects)

    return {
        "raw_aspects" : all_aspects,
        "df_converted": df_conv,
    }
