import io
import os
import re
import unicodedata
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import json
import math
import hashlib
from datetime import datetime, timedelta
from sqlalchemy import text

from db import (
    get_conn,
    init_db,
    upsert_transactions,
    load_all,
    apply_edits,
    delete_transactions,
    get_categories,
    replace_categories,
    update_categoria_map_from_df,
    map_categories_for_df,
    rename_category,
    compute_unique_keys_for_df,
)

st.set_page_config(page_title="Dashboard de Facto$", layout="wide")

st.title("Dashboard de Facto$")

# --- Modo móvil (flag por URL y CSS responsive) ---
_qp = st.query_params
MOBILE = str(_qp.get("mobile", "0")).lower() in ("1", "true", "yes")

# Autodetección móvil: si no viene el parámetro, lo agregamos si la pantalla es chica
if not MOBILE:
    st.markdown(
        """
        <script>
        (function(){
          try{
            var params = new URLSearchParams(window.location.search);
            if(!params.has('mobile')){
              var isSmall = Math.min(window.screen.width, window.screen.height) <= 480 || /iPhone|Android/i.test(navigator.userAgent);
              if(isSmall){
                params.set('mobile','1');
                var base = window.location.origin + window.location.pathname;
                var hash = window.location.hash || '';
                window.location.replace(base + '?' + params.toString() + hash);
              }
            }
          }catch(e){}
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )

# CSS responsive básico para pantallas pequeñas
st.markdown(
    """
    <style>
    @media (max-width: 480px){
      h1{ font-size: 1.8rem !important; }
      h2{ font-size: 1.25rem !important; }
      h3{ font-size: 1.05rem !important; }
      [data-testid=\"stSidebar\"]{ width: 78vw !important; }
      .block-container{ padding-left: 0.6rem !important; padding-right: 0.6rem !important; }
      div[data-testid=\"stMetric\"]{ padding: 8px 10px; }
      .vega-embed, canvas{ max-width: 100% !important; height: auto !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Variables de tema y activación (fijamos el estilo claro por defecto)
_theme = "Claro"
st.markdown(
    f"""
<style>
html[data-theme=\"Claro\"] {{
  --facto-primary:#0ea5e9;
  --facto-bg:#f7fafc;
  --facto-surface:#ffffff;
  --facto-card:#ffffff;
  --facto-border:#e5e7eb;
  --facto-text:#0f172a;
  --facto-muted:#6b7280;
}}
html[data-theme=\"Oscuro\"] {{
  --facto-primary:#22c55e;
  --facto-bg:#0b1220;
  --facto-surface:#0f172a;
  --facto-card:#111827;
  --facto-border:#1f2937;
  --facto-text:#e5e7eb;
  --facto-muted:#9ca3af;
}}
</style>
<script>
  (function(){{ try{{ document.documentElement.setAttribute('data-theme', '{_theme}'); }}catch(e){{}} }})();
</script>
    """,
    unsafe_allow_html=True,
)

# Estilos ligeros (color primario en sidebar)
st.markdown(
    """
<style>
:root{
  --facto-primary:#22c55e;
  --facto-bg:#0b1220;
  --facto-surface:#0f172a;
  --facto-card:#111827;
  --facto-border:#1f2937;
  --facto-text:#e5e7eb;
  --facto-muted:#9ca3af;
}

/* App background */
[data-testid="stAppViewContainer"] > .main{
  background-color: var(--facto-bg) !important;
}

/* Headings look & spacing */
h1, h2, h3{
  color: var(--facto-text) !important;
  letter-spacing: .3px;
}
h1{ font-weight: 800; }
h2{ margin-top: 1.25rem; font-weight: 700; }
h3{ margin-top: 1rem; font-weight: 700; }

/* Section dividers a bit subtler */
hr{
  border-color: var(--facto-border) !important;
  opacity:.6;
}

/* Sidebar styling */
section[data-testid="stSidebar"] > div{
  background-color: var(--facto-surface) !important;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span{
  color: var(--facto-text) !important;
}
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] textarea,
section[data-testid="stSidebar"] div[role="combobox"],
section[data-testid="stSidebar"] select{
  background-color: var(--facto-card) !important;
  color: var(--facto-text) !important;
  border: 1px solid var(--facto-border) !important;
}
[data-testid="stSidebar"] .stButton > button{
  background-color: var(--facto-primary) !important;
  color: #ffffff !important;
  border: 1px solid var(--facto-primary) !important;
  font-weight: 700;
}
[data-testid="stSidebar"] .stButton > button:hover{
  filter: brightness(1.05);
}
[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"]{
  background-color: var(--facto-primary) !important;
  color:#0b1220 !important;
}
section[data-testid="stSidebar"] [data-baseweb="slider"] > div{
  background: #1f2937 !important;
}

/* Buttons (global) */
.stButton > button{
  background-color: var(--facto-primary) !important;
  color: #ffffff !important;
  border: 1px solid var(--facto-primary) !important;
  font-weight: 700;
  border-radius: 10px;
  transition: transform .06s ease, filter .15s ease;
}
.stButton > button:hover{ filter: brightness(1.06); }
.stButton > button:active{ transform: translateY(1px); }

/* Metrics -> turn them into subtle cards */
div[data-testid="stMetric"]{
  background: linear-gradient(180deg, rgba(34,197,94,.12), rgba(34,197,94,.0));
  border: 1px solid var(--facto-border);
  border-radius: 12px;
  padding: 12px 14px;
}
div[data-testid="stMetric"] > label{
  color: var(--facto-muted) !important;
  font-weight: 600;
}
div[data-testid="stMetric"] [data-testid="stMetricDelta"]{
  font-weight: 700;
}

/* Data editor / tables */
[data-testid="stDataFrame"]{
  border: 1px solid var(--facto-border);
  border-radius: 12px;
  overflow: hidden;
}
[data-testid="stDataFrame"] .stTable, 
[data-testid="stDataFrame"] .stDataFrame{
  background-color: var(--facto-card) !important;
}
[data-testid="stDataFrame"] th{
  background-color: #0e1626 !important;
  color: var(--facto-text) !important;
  font-weight: 700 !important;
  border-bottom: 1px solid var(--facto-border) !important;
}
[data-testid="stDataFrame"] td{
  border-color: var(--facto-border) !important;
}

/* Expanders */
details[data-testid="stExpander"]{
  border: 1px solid var(--facto-border) !important;
  border-radius: 12px !important;
  background-color: var(--facto-card) !important;
}
details[data-testid="stExpander"] summary{
  color: var(--facto-text) !important;
  font-weight: 700 !important;
}

/* Messages (success/info/warn) harmonized */
.stAlert{
  border-radius: 12px;
  border: 1px solid var(--facto-border);
}

/* Vega/Altair canvas spacing (subtle drop shadow) */
.js-plotly-plot, .vega-embed{
  filter: drop-shadow(0 6px 14px rgba(0,0,0,.12));
}

/* Inputs focus ring */
input:focus, textarea:focus, select:focus{
  outline: none !important;
  box-shadow: 0 0 0 2px rgba(14,165,233,.35) !important;
  border-color: var(--facto-primary) !important;
}
</style>
    """,
    unsafe_allow_html=True,
)

# Requisitos mínimos (id y detalle_norm se derivan si faltan)
REQUIRED_COLS = {"fecha", "detalle", "monto"}

DEFAULT_CATEGORIES = [
    "Sin categoría",
    "Alimentación",
    "Tabaco",
    "Transporte",
    "Vivienda",
    "Servicios",
    "Salud",
    "Educación",
    "Compras",
    "Ocio",
    "Viajes",
    "Bancos/Comisiones",
    "Mascotas",
    "Hogar",
    "Suscripciones",
    "Impuestos",
    "Ahorro/Inversión",
    "Transferencias",
    "Ingresos",
    "Otros",
]

# Nombres de meses en español
MONTH_NAMES = {
    "01": "Enero", "02": "Febrero", "03": "Marzo", "04": "Abril",
    "05": "Mayo", "06": "Junio", "07": "Julio", "08": "Agosto",
    "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre"
}

def _parse_fecha_column(series, date_format: str = "YYYY-MM-DD"):
    """Parsea fechas según formato: YYYY-MM-DD (año-mes-día) o YYYY-DD-MM (año-día-mes)."""
    if series is None or (hasattr(series, "empty") and series.empty):
        return pd.Series(dtype="datetime64[ns]")
    formats_ymd = ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y"]
    formats_ydm = ["%Y-%d-%m", "%Y/%d/%m"]  # año, día, mes (ej: 2026-08-02 = 2 agosto)
    if date_format == "YYYY-DD-MM":
        fmts = formats_ydm + formats_ymd
    else:
        fmts = formats_ymd + formats_ydm
    result = []
    for v in series:
        if pd.isna(v) or (isinstance(v, str) and v.strip() == "") or v is None:
            result.append(pd.NaT)
            continue
        s = str(v).strip()
        parsed = pd.NaT
        for fmt in fmts:
            try:
                parsed = pd.to_datetime(s, format=fmt, errors="raise")
                break
            except Exception:
                pass
        if pd.isna(parsed):
            parsed = pd.to_datetime(s, dayfirst=True, errors="coerce")
        result.append(parsed)
    return pd.Series(result, index=series.index, dtype="datetime64[ns]")


def _detect_encoding(raw_bytes: bytes) -> str:
    """Detect encoding for CSV (supports Latin-1, UTF-8, Windows-1252)."""
    try:
        import chardet
        result = chardet.detect(raw_bytes)
        enc = (result.get("encoding") or "utf-8").lower()
        if enc in ("utf-8", "utf-8-sig", "ascii", "iso-8859-1", "latin-1", "windows-1252", "cp1252"):
            return enc
    except Exception:
        pass
    return "utf-8"


@st.cache_data(show_spinner=False)
def load_df(file, date_format: str = "YYYY-MM-DD"):
    # Leer contenido (bancos usan Latin-1, UTF-8, CP1252)
    raw = file.read() if hasattr(file, "read") else file
    if isinstance(raw, str):
        raw = raw.encode("utf-8", errors="replace")
    enc = _detect_encoding(raw)
    buf = io.BytesIO(raw)
    try:
        df = pd.read_csv(buf, sep=None, engine="python", encoding=enc)
    except Exception:
        buf.seek(0)
        try:
            df = pd.read_csv(buf, sep=None, engine="python", encoding="utf-8", on_bad_lines="skip")
        except Exception:
            buf.seek(0)
            df = pd.read_csv(buf)
    # Limpiar nombres de columnas (eliminar espacios, BOM y caracteres especiales)
    df.columns = df.columns.str.strip().str.lower()
    df.columns = df.columns.str.replace('\ufeff', '', regex=False)
    # Aliases: compatibilidad con prep.py y formatos de banco
    col_aliases = {
        "glosa": "detalle", "descripcion": "detalle", "concepto": "detalle", "comercio": "detalle",
        "cargo": "monto", "debe": "monto", "debito": "monto", "importe": "monto",
        "fecha movimiento": "fecha", "date": "fecha", "fecha_mov": "fecha",
        "fraccion_mia": "fraccion_mia_sugerida", "monto_mio": "monto_mio_estimado",
    }
    rename_map = {}
    for old, new in col_aliases.items():
        if old in df.columns and new not in df.columns:
            rename_map[old] = new
    df = df.rename(columns=rename_map)
    # Si aún falta 'detalle', buscar por substring
    if "detalle" not in df.columns:
        for c in df.columns:
            if any(k in c for k in ("detalle", "glosa", "descripcion", "concepto")):
                df = df.rename(columns={c: "detalle"})
                break
    if "monto" not in df.columns:
        for c in df.columns:
            if any(k in c for k in ("monto", "importe", "cargo", "abono")):
                df = df.rename(columns={c: "monto"})
                break

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        st.error(f"Faltan columnas requeridas: {sorted(missing)}")
        st.stop()
    
    # Fechas flexibles según formato seleccionado
    _fecha_raw = df.get("fecha")
    df["fecha"] = _parse_fecha_column(_fecha_raw, date_format)
    
    def _clean_amount(x):
        if pd.isna(x):
            return np.nan
        s = str(x).strip()
        if not s:
            return np.nan
        s = s.replace("$", "").replace("CLP", "").replace(" ", "").replace("\u00a0", "")
        if s.count(",") >= 1 and s.count(".") == 0:
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
        try:
            return float(s)
        except Exception:
            return pd.to_numeric(s, errors="coerce")
    
    for c in ["monto", "fraccion_mia_sugerida", "monto_mio_estimado", "monto_real", "fraccion_mia", "monto_mio"]:
        if c in df.columns:
            df[c] = df[c].apply(_clean_amount)

    # Monto de cartola inmutable (valor absoluto del monto original)
    if "monto" in df.columns:
        df["monto_cartola"] = pd.to_numeric(df["monto"], errors="coerce").abs()
    else:
        df["monto_cartola"] = np.nan
    
    if "id" not in df.columns:
        df["id"] = range(1, len(df) + 1)
    
    if "detalle_norm" not in df.columns:
        def _norm(s):
            if pd.isna(s):
                return ""
            s = str(s).strip()
            s = unicodedata.normalize("NFKD", s)
            s = "".join(ch for ch in s if not unicodedata.combining(ch))
            s = s.replace("\n", " ").replace("\t", " ")
            s = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s)
            return " ".join(s.upper().split())
        df["detalle_norm"] = df["detalle"].apply(_norm)
    
    for sc in ["detalle", "detalle_norm", "categoria", "nota_usuario"]:
        if sc in df.columns:
            df[sc] = df[sc].astype(str).replace({"nan": "", "None": ""}).fillna("")
    
    # unique_key: NO generarlo aquí. Se calcula con compute_unique_keys_for_df() antes del tombstone
    # y upsert para garantizar consistencia con la BD (hashlib determinístico, no Python hash())
    return df

def build_suggestions_df(df, conn):
    """Construir DataFrame de sugerencias de categoría (optimizado, consultas en lote)."""
    # Filas sin categoría o "Sin categoría"
    mask = (df["categoria"].isna()) | (df["categoria"] == "") | (df["categoria"] == "Sin categoría")
    sug_df = df[mask].copy()
    if sug_df.empty:
        return pd.DataFrame()

    # Asegurar columna detalle_norm consistente
    sug_df = sug_df.copy()
    if "detalle_norm" not in sug_df.columns:
        def _norm(s):
            if pd.isna(s):
                return ""
            s = str(s).strip()
            s = unicodedata.normalize("NFKD", s)
            s = "".join(ch for ch in s if not unicodedata.combining(ch))
            s = s.replace("\n", " ").replace("\t", " ")
            s = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s)
            return " ".join(s.upper().split())
        sug_df["detalle_norm"] = sug_df["detalle"].apply(_norm)

    # 1) Resolver mapa exacto para TODOS los detalle_norm únicos en una sola consulta
    dn_list = sorted(set(sug_df["detalle_norm"].dropna().astype(str)))
    if not dn_list:
        return pd.DataFrame()

    exact_map = {}
    try:
        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            with engine.connect() as cx:
                params = {f"dn{i}": v for i, v in enumerate(dn_list)}
                placeholders = ", ".join([f":dn{i}" for i in range(len(dn_list))])
                q = text(f"SELECT detalle_norm, categoria FROM categoria_map WHERE detalle_norm IN ({placeholders})")
                rows = cx.execute(q, params).fetchall()
                exact_map = {r[0]: r[1] for r in rows}
        else:
            placeholders = ",".join(["?"] * len(dn_list))
            q = f"SELECT detalle_norm, categoria FROM categoria_map WHERE detalle_norm IN ({placeholders})"
            rows = conn.execute(q, dn_list).fetchall()
            exact_map = {r[0]: r[1] for r in rows}
    except Exception:
        exact_map = {}

    # Pre-arreglo de resultados (los del mapa exacto se resuelven directo)
    results = []
    pending_dns = []
    for _, row in sug_df.iterrows():
        dn = str(row.get("detalle_norm") or "")
        if not dn:
            continue
        if dn in exact_map and pd.notna(exact_map[dn]) and str(exact_map[dn]).strip() != "":
            results.append({
                "unique_key": row.get("unique_key", ""),
                "detalle": row.get("detalle", ""),
                "detalle_norm": dn,
                "sugerida": exact_map[dn],
                "fuente": "Mapa exacto",
                "confianza": 1.0,
                "aceptar": False,
                "manual": "",
            })
        else:
            pending_dns.append(dn)

    pending_dns = sorted(set([dn for dn in pending_dns if dn]))

    # 2) Para los pendiente: calcular categoría dominante por detalle_norm en lote
    dom_map = {}
    if pending_dns:
        try:
            if isinstance(conn, dict) and conn.get("pg"):
                engine = conn["engine"]
                with engine.connect() as cx:
                    params = {f"dn{i}": v for i, v in enumerate(pending_dns)}
                    placeholders = ", ".join([f":dn{i}" for i in range(len(pending_dns))])
                    q = text(f"""
                        SELECT detalle_norm, categoria, cnt, total,
                               CASE WHEN total > 0 THEN (cnt * 100.0) / total ELSE 0 END AS pct
                        FROM (
                            SELECT detalle_norm, categoria, COUNT(*) AS cnt,
                                   SUM(COUNT(*)) OVER (PARTITION BY detalle_norm) AS total,
                                   ROW_NUMBER() OVER (PARTITION BY detalle_norm ORDER BY COUNT(*) DESC) AS rn
                            FROM movimientos
                            WHERE detalle_norm IN ({placeholders})
                              AND categoria IS NOT NULL
                              AND categoria != 'Sin categoría'
                            GROUP BY detalle_norm, categoria
                        ) s
                        WHERE rn = 1
                    """)
                    rows = cx.execute(q, params).fetchall()
                    for r in rows:
                        dn, cat, cnt, total, pct = r
                        if pct is None:
                            pct = 0.0
                        dom_map[dn] = (cat, float(pct))
            else:
                # SQLite: equivalente sin window functions usando CTEs y join
                placeholders = ",".join(["?"] * len(pending_dns))
                q = f"""
                    WITH filt AS (
                        SELECT detalle_norm, categoria
                        FROM movimientos
                        WHERE detalle_norm IN ({placeholders})
                          AND categoria IS NOT NULL
                          AND categoria != 'Sin categoría'
                    ),
                    stats AS (
                        SELECT detalle_norm, categoria, COUNT(*) AS cnt
                        FROM filt
                        GROUP BY detalle_norm, categoria
                    ),
                    total AS (
                        SELECT detalle_norm, SUM(cnt) AS total
                        FROM stats
                        GROUP BY detalle_norm
                    ),
                    ranked AS (
                        SELECT s.detalle_norm, s.categoria, s.cnt, t.total
                        FROM stats s JOIN total t USING(detalle_norm)
                    )
                    SELECT r1.detalle_norm,
                           r1.categoria,
                           r1.cnt,
                           r1.total,
                           (r1.cnt * 100.0) / NULLIF(r1.total, 0) AS pct
                    FROM ranked r1
                    JOIN (
                        SELECT detalle_norm, MAX(cnt) AS max_cnt FROM ranked GROUP BY detalle_norm
                    ) m
                    ON r1.detalle_norm = m.detalle_norm AND r1.cnt = m.max_cnt
                """
                rows = conn.execute(q, pending_dns).fetchall()
                # Si hay empates, se devuelven múltiples filas; elegimos la primera por orden de aparición
                seen = set()
                for r in rows:
                    dn, cat, cnt, total, pct = r
                    if dn in seen:
                        continue
                    seen.add(dn)
                    if pct is None:
                        pct = 0.0
                    dom_map[dn] = (cat, float(pct))
        except Exception:
            dom_map = {}

    # Armar resultados finales
    for _, row in sug_df.iterrows():
        dn = str(row.get("detalle_norm") or "")
        if not dn:
            continue
        if any(r.get("detalle_norm") == dn and r.get("unique_key") == row.get("unique_key", "") for r in results):
            continue
        cat_pct = dom_map.get(dn)
        if cat_pct:
            cat, pct = cat_pct
            if pd.notna(cat) and str(cat).strip() != "" and float(pct) >= 70.0:
                results.append({
                    "unique_key": row.get("unique_key", ""),
                    "detalle": row.get("detalle", ""),
                    "detalle_norm": dn,
                    "sugerida": cat,
                    "fuente": "Historial dominante",
                    "confianza": 0.8,
                    "aceptar": False,
                    "manual": "",
                })
                continue
        # 3) Sin sugerencia
        results.append({
            "unique_key": row.get("unique_key", ""),
            "detalle": row.get("detalle", ""),
            "detalle_norm": dn,
            "sugerida": "Sin categoría",
            "fuente": "Sin sugerencia",
            "confianza": 0.0,
            "aceptar": False,
            "manual": "",
        })

    return pd.DataFrame(results)


# Inicializar DB
conn = get_conn()
init_db(conn)

# === Garantizar tabla de tombstones para evitar "resurrecciones" ===
try:
    if isinstance(conn, dict) and conn.get("pg"):
        engine = conn["engine"]
        with engine.begin() as cx:
            cx.execute(text(
                """
                CREATE TABLE IF NOT EXISTS movimientos_borrados (
                    unique_key TEXT PRIMARY KEY,
                    deleted_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            ))
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS movimientos_borrados (
                unique_key TEXT PRIMARY KEY,
                deleted_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
except Exception as _tb_e:
    st.caption(f"(No se pudo garantizar tabla de tombstones: {_tb_e})")

# Cargar/sembrar categorías
categories = get_categories(conn)
if not categories:
    replace_categories(conn, DEFAULT_CATEGORIES)
    categories = DEFAULT_CATEGORIES[:]

uploaded = None
with st.sidebar:
    with st.expander("📂 Cargar movimientos", expanded=False):
        date_format = st.selectbox(
            "Formato de fecha en tu CSV",
            options=["YYYY-MM-DD", "YYYY-DD-MM"],
            format_func=lambda x: "Año-Mes-Día (2026-02-08 = 8 feb)" if x == "YYYY-MM-DD" else "Año-Día-Mes (2026-08-02 = 2 ago)",
            key="csv_date_format",
        )
        st.caption("Si tus fechas están como año-día-mes, elige la segunda opción.")
        uploaded = st.file_uploader(
            "Sube tu CSV (fecha, detalle, monto — o columnas equivalentes: glosa, cargo, etc.)",
            type=["csv"],
            help="Acepta CSV con columnas: fecha/detalle/monto, o glosa/descripcion/cargo/importe. Detección automática de encoding y delimitador.",
        )

if uploaded is not None:
    df_in = load_df(uploaded, date_format=date_format)

    # Forzar todo como Gasto (convierte montos a negativo) — SIEMPRE ACTIVO
    # usar monto_cartola como base inmutable; solo firmamos el signo visible
    if "monto_cartola" in df_in.columns:
        df_in["monto"] = -pd.to_numeric(df_in["monto_cartola"], errors="coerce").abs()
    else:
        df_in["monto"] = -pd.to_numeric(df_in.get("monto", 0), errors="coerce").abs()
    df_in["tipo"] = "Gasto"
    df_in["es_gasto"] = True
    df_in["es_transferencia_o_abono"] = False

    # Normalizar flags booleanos a True/False (evita DataError de Postgres por 0/1)
    for _col in ["es_gasto", "es_transferencia_o_abono", "es_compartido_posible"]:
        if _col in df_in.columns:
            s = df_in[_col].astype(str).str.strip().str.lower()
            df_in[_col] = s.isin(["1", "true", "t", "yes", "y", "si", "sí"])
        else:
            # defaults razonables (siempre gasto por diseño)
            if _col == "es_gasto":
                df_in[_col] = True
            else:
                df_in[_col] = False

    # Autocompletar categoría desde el mapa aprendido
    df_in = map_categories_for_df(conn, df_in)
    # Normalizar NUEVAMENTE los flags a booleanos reales (por si el mapeo de categorías cambió tipos)
    truthy = {"1", "true", "t", "yes", "y", "si", "sí", "s", "verdadero"}
    def _to_bool(v):
        if isinstance(v, (bool, np.bool_)):
            return bool(v)
        return str(v).strip().lower() in truthy
    for _col in ["es_gasto", "es_transferencia_o_abono", "es_compartido_posible"]:
        if _col in df_in.columns:
            df_in[_col] = df_in[_col].map(_to_bool)
        else:
            df_in[_col] = False
    # Asegurar dtype object->bool puro (evita 0/1)
    df_in["es_gasto"] = df_in["es_gasto"].astype(bool)
    df_in["es_transferencia_o_abono"] = df_in["es_transferencia_o_abono"].astype(bool)
    df_in["es_compartido_posible"] = df_in["es_compartido_posible"].astype(bool)

    # --- unique_key canónico (mismo algoritmo que la BD) para tombstone y upsert ---
    df_in = compute_unique_keys_for_df(df_in)

    # --- Filtrar transacciones previamente borradas (tombstones) ---
    try:
        tomb_uks = set()
        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            with engine.connect() as cx:
                tdf = pd.read_sql_query(text("SELECT unique_key FROM movimientos_borrados"), cx)
        else:
            tdf = pd.read_sql_query("SELECT unique_key FROM movimientos_borrados", conn)
        if tdf is not None and not tdf.empty:
            tomb_uks = set(tdf["unique_key"].astype(str).tolist())
        before_len = len(df_in)
        if "unique_key" in df_in.columns and tomb_uks:
            df_in = df_in[~df_in["unique_key"].astype(str).isin(tomb_uks)].copy()
            skipped = before_len - len(df_in)
            if skipped > 0:
                st.info(f"⛔ {skipped} fila(s) del CSV fueron omitidas porque sus unique_key están marcadas como borradas.")
    except Exception as _tbe:
        st.caption(f"(No se pudo aplicar filtro de tombstones: {_tbe})")

    inserted, ignored = upsert_transactions(conn, df_in)
    st.success(f"Ingeridos: {inserted} nuevas filas, ignoradas por duplicado: {ignored}")


# Cargar histórico desde DB
df = load_all(conn)
# Depurar duplicados por unique_key (quedarse con el más reciente por fecha)
try:
    if "unique_key" in df.columns:
        # ordenar por fecha asc para que el keep='last' deje el más nuevo
        df = df.sort_values(by=["fecha"], ascending=True)
        dup_count = int(df.duplicated(subset=["unique_key"], keep="last").sum())
        if dup_count > 0:
            df = df.drop_duplicates(subset=["unique_key"], keep="last").reset_index(drop=True)
            st.caption(f"🔁 Depurado: se eliminaron {dup_count} duplicados por unique_key al cargar la BD.")
except Exception as _dedupe_e:
    st.caption(f"(No se pudo depurar duplicados: {_dedupe_e})")

if df.empty:
    st.info(
        "Sube un CSV estandarizado para comenzar. Primero procesa tu archivo original con el notebook de preparación."
    )
    st.stop()

# Filtros en sidebar
with st.sidebar:
    st.header("Filtros")
    q = st.text_input("Buscar en detalle", "", key="search_q")
    # Filtro por mes (además del rango de fechas)
    df_months = df.copy()
    df_months["mes"] = df_months["fecha"].dt.to_period("M").astype(str)
    months = sorted([m for m in df_months["mes"].dropna().unique().tolist()])
    # Mes actual como predeterminado si existe en los datos
    cur_month = pd.Timestamp.today().strftime("%Y-%m")
    default_idx = (months.index(cur_month) + 1) if (cur_month in months) else 0
    sel_mes = st.selectbox("Mes", options=["Todos"] + months, index=default_idx, key="month_filter")
    st.caption("Si eliges un **Mes**, solo la vista principal se filtra a ese mes. La comparación mensual usa el set completo (o el rango de fechas si lo defines abajo).")
    min_fecha, max_fecha = df["fecha"].min(), df["fecha"].max()
    if pd.isna(min_fecha) or pd.isna(max_fecha):
        rango = None
    else:
        rango = st.date_input(
            "Rango de fechas",
            (min_fecha.date(), max_fecha.date()),
            key="date_range"
        )
    st.divider()
    with st.expander("Gestionar categorías"):
        st.caption("Puedes eliminar o agregar categorías. Se guardan en la base.")
        st.write("Actuales:")
        st.code("\n".join(categories), language=None)
        to_remove = st.multiselect("Eliminar", options=categories, default=[])
        new_cat = st.text_input("Agregar nueva categoría", value="")
        if st.button("Aplicar cambios de categorías"):
            new_list = [c for c in categories if c not in set(to_remove)]
            if new_cat.strip():
                new_list.append(new_cat.strip())
            # asegurar 'Sin categoría' siempre presente
            if "Sin categoría" not in new_list:
                new_list.insert(0, "Sin categoría")
            # dedupe manteniendo orden
            seen = set()
            deduped = []
            for c in new_list:
                if c not in seen:
                    deduped.append(c)
                    seen.add(c)
            replace_categories(conn, deduped)
            st.success("Categorías actualizadas")
            categories = deduped
        st.markdown("---")
        st.caption("Renombrar categoría (propaga a movimientos y reglas)")
        colr1, colr2 = st.columns([1,1])
        with colr1:
            old_name = st.selectbox("Categoría a renombrar", options=[c for c in categories if c != "Sin categoría"], key="rename_old")
        with colr2:
            new_name = st.text_input("Nuevo nombre", value="", key="rename_new")
        if st.button("Renombrar") and new_name.strip():
            rename_category(conn, old_name, new_name.strip())
            categories = get_categories(conn)
            st.success(f"'{old_name}' → '{new_name.strip()}' actualizado")
            # Refrescar para recargar df desde la base y aplicar nombre nuevo en la tabla
            st.rerun()
# --- Leer valores de filtros desde session_state para uso global ---
q = st.session_state.get("search_q", "")
sel_mes = st.session_state.get("month_filter", "Todos")
rango = st.session_state.get("date_range", rango)


# Preparar bases de trabajo
dfv = df.copy()               # vista principal/editable
df_base_compare = df.copy()   # base para comparación (no aplica filtro por mes)

# Asegurar tipo numérico en monto para evitar NaNs o strings
if "monto" in dfv.columns:
    dfv["monto"] = pd.to_numeric(dfv["monto"], errors="coerce").fillna(0)
if "monto" in df_base_compare.columns:
    df_base_compare["monto"] = pd.to_numeric(df_base_compare["monto"], errors="coerce").fillna(0)

# Determinar tipo con prioridad (solo interpretativo; no filtramos por tipo en UI)
if "tipo" in dfv.columns:
    dfv["tipo_calc"] = dfv["tipo"].astype(str)
    df_base_compare["tipo_calc"] = df_base_compare["tipo"].astype(str)
elif "es_gasto" in dfv.columns:
    tmp = dfv["es_gasto"].astype(str).str.lower()
    dfv["tipo_calc"] = np.where(tmp.isin(["1","true","t","si","sí","y"]), "Gasto", "Abono")
    tmp2 = df_base_compare["es_gasto"].astype(str).str.lower()
    df_base_compare["tipo_calc"] = np.where(tmp2.isin(["1","true","t","si","sí","y"]), "Gasto", "Abono")
elif "es_transferencia_o_abono" in dfv.columns:
    tmp = dfv["es_transferencia_o_abono"].astype(str).str.lower()
    dfv["tipo_calc"] = np.where(tmp.isin(["1","true","t","si","sí","y"]), "Abono", "Gasto")
    tmp2 = df_base_compare["es_transferencia_o_abono"].astype(str).str.lower()
    df_base_compare["tipo_calc"] = np.where(tmp2.isin(["1","true","t","si","sí","y"]), "Abono", "Gasto")
else:
    dfv["tipo_calc"] = np.where(dfv["monto"] < 0, "Gasto", np.where(dfv["monto"] > 0, "Abono", "Cero"))
    df_base_compare["tipo_calc"] = np.where(df_base_compare["monto"] < 0, "Gasto", np.where(df_base_compare["monto"] > 0, "Abono", "Cero"))
    # Fallback para CSV enriquecido re-importado (montos positivos, sin columna 'tipo')
    if not (dfv["tipo_calc"] == "Gasto").any() and (dfv["monto"] >= 0).all():
        dfv["tipo_calc"] = "Gasto"
    if not (df_base_compare["tipo_calc"] == "Gasto").any() and (df_base_compare["monto"] >= 0).all():
        df_base_compare["tipo_calc"] = "Gasto"

# Texto libre
if q:
    dfv = dfv[dfv["detalle_norm"].str.contains(q, case=False, na=False)]
    df_base_compare = df_base_compare[df_base_compare["detalle_norm"].str.contains(q, case=False, na=False)]

df_analysis = df_base_compare.copy()

# Rango de fechas (afecta SOLO la vista principal; la comparación mensual usa toda la base)
if isinstance(rango, tuple) and len(rango) == 2:
    start_r, end_r = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    dfv = dfv[(dfv["fecha"] >= start_r) & (dfv["fecha"] <= end_r)]
    df_analysis = df_analysis[(df_analysis["fecha"] >= start_r) & (df_analysis["fecha"] <= end_r)]
elif rango:
    dfv = dfv[dfv["fecha"].dt.date == rango]
    df_analysis = df_analysis[df_analysis["fecha"].dt.date == rango]

# Filtro por mes (solo para la VISTA principal; NO afecta comparación)
if sel_mes and sel_mes != "Todos":
    y, m = sel_mes.split("-")
    start = pd.to_datetime(f"{y}-{m}-01")
    end = start + pd.offsets.MonthEnd(1)
    dfv = dfv[(dfv["fecha"] >= start) & (dfv["fecha"] <= end)]

# Tipo final y monto para mostrar (sin filtro por tipo)
dfv["tipo"] = dfv["tipo_calc"]
dfv["monto_cartola"] = dfv["monto"].abs()

# Filtro por categoría (para acompañar interacción del gráfico)
cat_options = sorted([c for c in categories if c])
sel_cats = st.sidebar.multiselect("Categorías", options=["Todas"] + cat_options, default=["Todas"])
if sel_cats and "Todas" not in sel_cats:
    dfv = dfv[dfv["categoria"].isin(sel_cats)]
    df_base_compare = df_base_compare[df_base_compare["categoria"].isin(sel_cats)]
    df_analysis = df_analysis[df_analysis["categoria"].isin(sel_cats)]

# Construir df para gráficos, aplicando borradores de edición (sin necesidad de guardar)
draft_key = "draft_table_v1"
df_plot = dfv.copy()
df_plot["monto_real_plot"] = df_plot.get("monto_real")
df_plot.loc[df_plot["monto_real_plot"].isna(), "monto_real_plot"] = df_plot["monto"].abs()
if draft_key in st.session_state and "unique_key" in df_plot.columns:
    draft = st.session_state[draft_key]
    if isinstance(draft, pd.DataFrame) and len(draft) > 0 and "unique_key" in draft.columns:
        base = df_plot.set_index("unique_key")
        dset = draft.set_index("unique_key")
        inter = base.index.intersection(dset.index)
        for col in ["monto", "categoria", "nota_usuario"]:
            if col in base.columns and col in dset.columns:
                base.loc[inter, col] = dset.loc[inter, col]
        df_plot = base.reset_index()
        df_plot["monto_real_plot"] = df_plot["monto"]

# Paleta y mapeo de color consistente por categoría
palette = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc949", "#af7aa1", "#ff9da7", "#9c755f", "#bab0ab",
]
supermercado_color = "#22c55e"  # color fijo de la marca para Supermercado
# Orden preferido: Supermercado primero si existe
preferred = ["Supermercado"] + [c for c in cat_options if c != "Supermercado"]
domain = preferred
# Construir rango asegurando que Supermercado use su color fijo y el resto la paleta
colors_by_category = {}
colors_by_category["Supermercado"] = supermercado_color
# rellenar restantes con la paleta en orden
pal_iter = iter(palette)
for c in domain:
    if c == "Supermercado":
        continue
    # evitar reutilizar el mismo color verde
    nxt = next(pal_iter, None)
    if nxt is None:
        pal_iter = iter(palette)
        nxt = next(pal_iter)
    # si por casualidad el color coincide con supermercado_color, salta al siguiente
    if nxt.lower() == supermercado_color.lower():
        nxt = next(pal_iter, "#4e79a7")
    colors_by_category[c] = nxt
range_colors = [colors_by_category[c] for c in domain]

 
# --- Chips de filtros activos ---
chips = []
if sel_mes and sel_mes != "Todos":
    chips.append(("Mes", sel_mes, "clear_mes"))
if "filtered_category" in st.session_state and st.session_state["filtered_category"]:
    chips.append(("Categoría", st.session_state["filtered_category"], "clear_cat"))
if q:
    chips.append(("Búsqueda", q, "clear_q"))
if isinstance(rango, tuple) and len(rango) == 2:
    chips.append(("Rango", f"{rango[0]} → {rango[1]}", "clear_range"))

if chips:
    st.markdown("#### Filtros activos")
    cols = st.columns(len(chips))
    for i, (lbl, val, keybtn) in enumerate(chips):
        with cols[i]:
            if st.button(f"{lbl}: {val} ✕", key=keybtn):
                if keybtn == "clear_mes":
                    st.session_state["month_filter"] = "Todos"
                elif keybtn == "clear_cat":
                    st.session_state.pop("filtered_category", None)
                elif keybtn == "clear_q":
                    st.session_state["search_q"] = ""
                elif keybtn == "clear_range":
                    st.session_state["date_range"] = None
                st.rerun()
    st.markdown("---")

st.markdown("### Insights principales")
# Cálculos base para métricas
amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
_total_series = pd.to_numeric(df_plot[amt_col], errors="coerce").abs().fillna(0)
total_real = float(_total_series.sum())

# Ventana temporal visible (para promedios)
if not df_plot.empty:
    min_d, max_d = pd.to_datetime(df_plot["fecha"]).min(), pd.to_datetime(df_plot["fecha"]).max()
    # Días efectivos (al menos 1 para evitar división por 0)
    days = max(1, int((max_d.normalize() - min_d.normalize()).days) + 1) if pd.notna(min_d) and pd.notna(max_d) else 1
    prom_diario = total_real / days
    # Promedio mensual: sumar por mes visible y promediar
    df_plot_m = df_plot.copy()
    df_plot_m["mes"] = df_plot_m["fecha"].dt.to_period("M").astype(str)
    monthly_totals = df_plot_m.groupby("mes")[amt_col].apply(lambda s: pd.to_numeric(s, errors="coerce").abs().sum()).reset_index(name="monto")
    prom_mensual = float(monthly_totals["monto"].mean()) if not monthly_totals.empty else total_real
else:
    prom_diario = 0.0
    prom_mensual = 0.0

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Gasto real (visible)", f"${total_real:,.0f}")
with col2:
    st.metric("Promedio diario", f"${prom_diario:,.0f}")
with col3:
    st.metric("Promedio mensual", f"${prom_mensual:,.0f}")

# Bloque de insights rápidos
st.markdown("---")
st.markdown("#### 🧠 Insights rápidos")
try:
    _maux = df_analysis.copy()
    if not _maux.empty:
        _maux["mes"] = _maux["fecha"].dt.to_period("M").astype(str)
    amt_candidates = ["monto", "monto_real", "monto_real_plot"]
    _amtc = next((c for c in amt_candidates if c in _maux.columns), None)
    if _amtc is None:
        raise ValueError("No hay columna de monto para análisis mensual")
    _series = _maux.assign(_a=np.abs(pd.to_numeric(_maux[_amtc], errors="coerce").fillna(0))).groupby("mes")["_a"].sum().sort_index()
    delta_text = "n/a"
    if len(_series) >= 2:
        last = _series.iloc[-1]
        prev = _series.iloc[-2]
        if prev > 0:
            pct = (last - prev) / prev * 100.0
            delta_text = ("+" if pct >= 0 else "") + f"{pct:.1f}% vs mes anterior"
        else:
            delta_text = "nuevo mes sin base"
    # Comercio más relevante del mes actual
    df_mes_ins = _maux.copy()
    if not df_mes_ins.empty:
        df_mes_ins["mes"] = df_mes_ins["fecha"].dt.to_period("M").astype(str)
        last_m = sorted([m for m in df_mes_ins["mes"].dropna().unique()])[-1]
        curm = df_mes_ins[df_mes_ins["mes"] == last_m]
        by_place = curm.assign(_a=np.abs(pd.to_numeric(curm[_amtc], errors="coerce").fillna(0))).groupby("detalle_norm")["_a"].sum().sort_values(ascending=False)
        top_place = by_place.index[0] if len(by_place) else "-"
        top_place_val = float(by_place.iloc[0]) if len(by_place) else 0.0
    else:
        top_place, top_place_val = "-", 0.0
    c_i1, c_i2 = st.columns(2)
    with c_i1:
        st.metric("Variación mensual", delta_text)
    with c_i2:
        st.metric("Top lugar del mes", top_place, help=f"Total: ${top_place_val:,.0f}")
except Exception:
    pass

# Categoría más relevante se muestra debajo para evitar saturación
if not df_plot.empty:
    cat_agg_metric = df_plot.assign(_amt=np.abs(pd.to_numeric(df_plot[amt_col], errors="coerce").fillna(0))).groupby("categoria")["_amt"].sum().sort_values(ascending=False)
    if len(cat_agg_metric) > 0:
        st.caption(f"Categoría más relevante: **{cat_agg_metric.index[0]}**")

# Donut por categoría (centrado, compacto, con total al centro)
if not df_plot.empty:
    amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
    cat_agg = (
        df_plot.assign(_amt=np.abs(pd.to_numeric(df_plot[amt_col], errors="coerce").fillna(0)))
        .groupby("categoria", dropna=False)["_amt"].sum().reset_index()
        .rename(columns={"_amt": "total"})
        .sort_values("total", ascending=False)
    )

    st.markdown("### Distribución de Gastos por Categoría")

# Donut más compacto y con borde más grueso
    chart_donut = (
        alt.Chart(cat_agg)
        .mark_arc(
            innerRadius=(70 if MOBILE else 80),
            outerRadius=(120 if MOBILE else 140),
            cornerRadius=3,
            padAngle=0.005,
            stroke="#0b1220",
            strokeWidth=1
        )
        .encode(
            theta=alt.Theta("total:Q", stack=True),
            color=alt.Color(
                "categoria:N",
                scale=alt.Scale(domain=domain, range=range_colors),
                legend=None
            ),
            tooltip=[
                alt.Tooltip("categoria:N", title="Categoría"),
                alt.Tooltip("total:Q", format=",.0f", title="Total")
            ],
        )
        .properties(width=(340 if MOBILE else 420), height=(300 if MOBILE else 360))
    )

    # Texto centrado con el total
    total_sum = float(cat_agg["total"].sum()) if not cat_agg.empty else 0.0
    center_text_df = pd.DataFrame({"x": [170 if MOBILE else 210], "y": [150 if MOBILE else 180], "txt": [f"${total_sum:,.0f}"]})
    center_text = (
        alt.Chart(center_text_df)
        .mark_text(fontSize=22, fontWeight="bold", color="#e5e7eb")
        .encode(x=alt.X("x:Q", axis=None), y=alt.Y("y:Q", axis=None), text="txt:N")
    )

    chart_layered = (
        alt.layer(chart_donut, center_text)
        .configure_view(stroke=None)
        .configure_axis(grid=False)
    )

    # Centrar el donut en la página
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.altair_chart(chart_layered, use_container_width=False, theme="streamlit")

    # Selector simple de categoría para filtrado (se mantiene)
    st.markdown("---")
    col_filter1, col_filter2, col_filter3 = st.columns([1, 2, 1])
    with col_filter2:
        st.markdown("**🔍 Filtro por Categoría**")
        selected_category = st.selectbox(
            "Seleccionar categoría para filtrar:",
            options=["Todas las categorías"] + cat_agg["categoria"].tolist(),
            key="category_filter"
        )
        if selected_category != "Todas las categorías":
            if st.button("✅ Aplicar filtro", key="apply_filter"):
                st.session_state["filtered_category"] = selected_category
                st.rerun()

# === Insights analíticos adicionales ===
col_tl = st.container()

# Helper para obtener el DataFrame del "mes actual" (o el último disponible)
def _df_mes_actual(_df, _sel_mes):
    if _df.empty:
        return _df
    if _sel_mes and _sel_mes != "Todos":
        y, m = _sel_mes.split("-")
        _start = pd.to_datetime(f"{y}-{m}-01")
        _end = _start + pd.offsets.MonthEnd(1)
        return _df[(_df["fecha"] >= _start) & (_df["fecha"] <= _end)].copy()
    # Sin selección: tomar el último mes presente en los datos visibles
    tmp = _df.copy()
    tmp["mes"] = tmp["fecha"].dt.to_period("M").astype(str)
    if tmp["mes"].empty:
        return _df
    last_month = sorted(tmp["mes"].dropna().unique().tolist())[-1]
    y, m = last_month.split("-")
    _start = pd.to_datetime(f"{y}-{m}-01")
    _end = _start + pd.offsets.MonthEnd(1)
    return _df[(tmp["fecha"] >= _start) & (tmp["fecha"] <= _end)].copy()

with col_tl:
    st.markdown("**🏪 Top 5 lugares del mes**")
    df_mes = _df_mes_actual(dfv, sel_mes)
    if not df_mes.empty:
        # Agregar por comercio (detalle_norm) y, como respaldo, por categoría
        amt_col2 = "monto" if "monto" in df_mes.columns else "monto_real_plot"
        by_merchant = (
            df_mes.assign(_amt=np.abs(pd.to_numeric(df_mes[amt_col2], errors="coerce").fillna(0)))
                  .groupby("detalle_norm")["_amt"].sum().reset_index()
                  .rename(columns={"_amt": "total"})
                  .sort_values("total", ascending=False)
        )
        top5 = by_merchant.head(5)
        if top5.empty:
            st.caption("(Sin datos suficientes en el mes actual)")
        else:
            st.table(top5.rename(columns={"detalle_norm": "Lugar", "total": "Total"}))
    else:
        st.caption("(Sin datos para este mes)")

# Aplicar filtro de categoría si está seleccionado
if "filtered_category" in st.session_state and st.session_state["filtered_category"]:
    selected_cat = st.session_state["filtered_category"]
    dfv = dfv[dfv["categoria"] == selected_cat].copy()
    df_plot = df_plot[df_plot["categoria"] == selected_cat].copy()
    
    # Mostrar banner de filtro activo
    st.info(f"🔍 **Filtro activo**: Mostrando solo transacciones de '{selected_cat}'")
    
    # Botón para limpiar filtro
    if st.button("❌ Limpiar filtro", key="clear_filter"):
        del st.session_state["filtered_category"]
        st.rerun()
    
    st.markdown("---")


# === Nueva disposición de gráficos ===
# Fila A: izquierda (ancho) = Frecuencia por categoría (barras horizontales)
#         derecha = Gastos por Día de la Semana (línea)
col_left, col_right = st.columns([3, 2])

with col_left:
    if not df_plot.empty:
        amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
        freq = (
            df_plot.groupby("categoria").size().reset_index(name="veces")
                  .sort_values("veces", ascending=True)  # ascendente para horizontal
        )
        if MOBILE and len(freq) > 12:
            freq = freq.tail(12)
        # Escala/ticks enteros para eje numérico (eje X ahora)
        max_val = freq["veces"].max()
        max_veces = 1 if pd.isna(max_val) or max_val is None else int(max_val)
        tick_step = 1 if max_veces <= 5 else max(1, max_veces // 5)
        x_enc_freq = alt.X(
            "veces:Q",
            title="Cantidad de Transacciones",
            scale=alt.Scale(domain=[0, max_veces], nice=False, zero=True),
            axis=alt.Axis(
                format="d",
                tickCount=min(6, max_veces),
                tickMinStep=1,
                values=list(range(0, max_veces + 1, tick_step))
            )
        )
        chart_freq = (
            alt.Chart(freq)
            .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4, stroke="#ffffff", strokeWidth=1)
            .encode(
                y=alt.Y("categoria:N", sort="x", title="Categoría"),
                x=x_enc_freq,
                color=alt.Color("categoria:N", legend=None, scale=alt.Scale(domain=domain, range=range_colors)),
                tooltip=[
                    alt.Tooltip("categoria:N", title="Categoría"),
                    alt.Tooltip("veces:Q", title="Cantidad", format="d")
                ],
            )
            .properties(
                height=(max(200, 18 * max(5, len(freq))) if MOBILE else max(240, 20 * max(5, len(freq)))),
                title={
                    "text": "Frecuencia por Categoría",
                    "fontSize": 14,
                    "fontWeight": "bold",
                    "color": "#133c60"
                }
            )
            .configure_view(stroke=None)
            .configure_axis(grid=False)
        )
        st.altair_chart(chart_freq, use_container_width=True)

with col_right:
    if not df_plot.empty:
        dia_map = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
        df_plot["dow"] = df_plot["fecha"].dt.dayofweek.map(dia_map)
        df_plot["dow_idx"] = df_plot["fecha"].dt.dayofweek
        amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
        dow_agg = df_plot.assign(_amt=np.abs(df_plot[amt_col].astype(float))).groupby(["dow", "dow_idx"])['_amt'].sum().reset_index()
        dow_agg.rename(columns={"_amt": "total"}, inplace=True)
        chart_dow = (
            alt.Chart(dow_agg)
            .mark_line(point={"size": (40 if MOBILE else 60)}, stroke="#4e79a7", strokeWidth=(2 if MOBILE else 3))
            .encode(
                x=alt.X("dow:N", sort=["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"], title="Día de la Semana"),
                y=alt.Y("total:Q", title="Total de Gastos", axis=alt.Axis(format=",.0f")),
                tooltip=[alt.Tooltip("dow:N", title="Día"), alt.Tooltip("total:Q", format=",.0f", title="Total")],
            )
            .properties(height=(240 if MOBILE else 300), title={"text": "Gastos por Día de la Semana", "fontSize": 14, "fontWeight": "bold", "color": "#133c60"})
            .configure_view(stroke=None)
            .configure_axis(grid=False)
        )
        st.altair_chart(chart_dow, use_container_width=True)

# Fila B (completa): Ticket promedio por categoría (barras horizontales)
st.markdown("---")
if not df_plot.empty:
    amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
    avg = (
        df_plot.assign(_amt=df_plot[amt_col].abs())
              .groupby("categoria")['_amt'].mean().reset_index()
              .rename(columns={'_amt': 'ticket_prom'})
              .sort_values("ticket_prom", ascending=True)
    )
    if MOBILE and len(avg) > 12:
        avg = avg.tail(12)

    # Valores seguros para eje X (evita NaN/Inf y pasos 0)
    max_raw = 0.0 if avg.empty else avg["ticket_prom"].max()
    try:
        max_ticket = float(max_raw)
    except Exception:
        max_ticket = 0.0
    if not np.isfinite(max_ticket) or max_ticket <= 0:
        max_ticket = 1.0

    # Escalonamiento robusto: usar pasos ENTEROS y nunca 0
    step_base = max_ticket / 5.0
    if step_base >= 5000:
        step_i = int(max(1000, round(step_base, -3)))
    else:
        step_i = int(max(100, round(step_base, -2)))
    if not np.isfinite(step_i) or step_i <= 0:
        step_i = 1

    # Construir ticks con range() entero para evitar errores de np.arange
    max_i = int(math.ceil(max_ticket))
    vals = list(range(0, max_i + step_i, step_i))

    x_enc_avg = alt.X(
        "ticket_prom:Q",
        title="Ticket Promedio",
        axis=alt.Axis(format=",.0f", values=vals),
        scale=alt.Scale(domain=[0, max_i], nice=False, zero=True)
    )

    chart_avg = (
        alt.Chart(avg)
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4, stroke="#ffffff", strokeWidth=1)
        .encode(
            y=alt.Y("categoria:N", sort="x", title="Categoría"),
            x=x_enc_avg,
            color=alt.Color("categoria:N", legend=None, scale=alt.Scale(domain=domain, range=range_colors)),
            tooltip=[
                alt.Tooltip("categoria:N", title="Categoría"),
                alt.Tooltip("ticket_prom:Q", format=",.0f", title="Ticket Promedio")
            ],
        )
        .properties(
            height=(max(220, 20 * max(5, len(avg))) if MOBILE else max(260, 22 * max(5, len(avg)))),
            title={"text": "Ticket Promedio por Categoría", "fontSize": 14, "fontWeight": "bold", "color": "#133c60"}
        )
        .configure_view(stroke=None)
        .configure_axis(grid=False)
    )
    st.altair_chart(chart_avg, use_container_width=True)

# Comparación mes seleccionado vs anterior
if sel_mes and sel_mes != "Todos" and not df_base_compare.empty:
    st.markdown("### Comparación mes seleccionado vs anterior")
    try:
        y, m = sel_mes.split("-")
        current_start = pd.to_datetime(f"{y}-{m}-01")
        current_end = current_start + pd.offsets.MonthEnd(1)
        
        # Mes anterior
        prev_start = current_start - pd.offsets.MonthBegin(1)
        prev_end = current_start - pd.offsets.Day(1)
        
        # Datos del mes actual (usando df_base_compare)
        current_data = df_base_compare[(df_base_compare["fecha"] >= current_start) & (df_base_compare["fecha"] <= current_end)].copy()
        current_data["mes"] = "Actual"
        
        # Datos del mes anterior (usando df_base_compare)
        prev_data = df_base_compare[(df_base_compare["fecha"] >= prev_start) & (df_base_compare["fecha"] <= prev_end)].copy()
        prev_data["mes"] = "Anterior"
        
        # Combinar y agregar por categoría y mes
        comparison_data = pd.concat([current_data, prev_data])
        amt_col = "monto" if "monto" in comparison_data.columns else "monto_real_plot"
        
        comparison_agg = (
            comparison_data.assign(_amt=np.abs(pd.to_numeric(comparison_data[amt_col], errors="coerce").fillna(0)))
            .groupby(["categoria", "mes"])["_amt"].sum().reset_index()
            .rename(columns={"_amt": "total"})
        )
        
        if not comparison_agg.empty:
            # Ordenar categorías por el total del mes "Actual" (fallback al total global)
            cat_order = (
                comparison_agg[comparison_agg["mes"] == "Actual"]
                .sort_values("total", ascending=False)["categoria"].tolist()
            )
            if not cat_order:
                cat_order = (
                    comparison_agg.groupby("categoria")["total"].sum()
                    .sort_values(ascending=False).index.tolist()
                )

            bars = (
                alt.Chart(comparison_agg)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "categoria:N",
                        title="Categoría",
                        sort=cat_order,
                        scale=alt.Scale(paddingInner=0.15, paddingOuter=0.05)
                    ),
                    xOffset=alt.XOffset("mes:N", scale=alt.Scale(domain=["Anterior", "Actual"])),
                    y=alt.Y("total:Q", title="Total", axis=alt.Axis(format=",.0f")),
                    color=alt.Color(
                        "mes:N",
                        title="Mes",
                        scale=alt.Scale(domain=["Anterior", "Actual"]),
                        legend=alt.Legend(orient="top")
                    ),
                    tooltip=[
                        alt.Tooltip("categoria:N", title="Categoría"),
                        alt.Tooltip("mes:N", title="Mes"),
                        alt.Tooltip("total:Q", format=",.0f", title="Total"),
                    ],
                )
            )

            labels = (
                alt.Chart(comparison_agg)
                .mark_text(dy=-6)
                .encode(
                    x=alt.X(
                        "categoria:N",
                        sort=cat_order,
                        scale=alt.Scale(paddingInner=0.15, paddingOuter=0.05)
                    ),
                    xOffset=alt.XOffset("mes:N", scale=alt.Scale(domain=["Anterior", "Actual"])),
                    y=alt.Y("total:Q"),
                    text=alt.Text("total:Q", format=",.0f"),
                    color=alt.value("#e5e7eb")
                )
            )

            chart_comparison = (
                alt.layer(bars, labels)
                .properties(height=280)
                .configure_view(stroke=None)
                .configure_axis(grid=False, labelAngle=-15)
            )
            st.altair_chart(chart_comparison, use_container_width=True)
    except Exception as e:
        st.warning(f"No se pudo generar la comparación: {e}")


# Sugerencias de categoría
title_sug = "### Sugerencias de categoría"
if MOBILE:
    with st.expander("Sugerencias de categoría (toca para ver)"):
        st.markdown(title_sug)
        # el resto de la sección continúa igual
else:
    st.markdown(title_sug)
# Guard flag para auto-aplicación de sugerencias de alta confianza
if "auto_apply_suggestions_done" not in st.session_state:
    st.session_state["auto_apply_suggestions_done"] = False
suggestions_df = build_suggestions_df(dfv, conn)

# Auto-aplicar sugerencias de alta confianza (>= 0.9) una sola vez por sesión
if (not st.session_state["auto_apply_suggestions_done"]) and (not suggestions_df.empty):
    high_conf = suggestions_df[suggestions_df["confianza"] >= 0.9].copy()
    if not high_conf.empty:
        edits_df = pd.DataFrame()
        for _, row in high_conf.iterrows():
            original_row = dfv[dfv["unique_key"] == row["unique_key"]]
            if not original_row.empty:
                edit_row = original_row.iloc[0].copy()
                edit_row["categoria"] = row["sugerida"]
                edits_df = pd.concat([edits_df, pd.DataFrame([edit_row])], ignore_index=True)
        if not edits_df.empty:
            updated = apply_edits(conn, edits_df)
            try:
                learned = update_categoria_map_from_df(conn, edits_df)
                if learned:
                    st.caption(f"Aprendidas {learned} reglas nuevas por 'detalle_norm'.")
            except Exception:
                pass
            st.success(f"Aplicadas automáticamente {updated} sugerencias de categoría (confianza ≥ 0.9).")
            st.session_state["auto_apply_suggestions_done"] = True
            st.rerun()

if not suggestions_df.empty:
    st.caption(f"Se encontraron {len(suggestions_df)} transacciones sin categoría. Revisa las sugerencias:")
    
    # UI de revisión de sugerencias
    with st.form("suggestions_form"):
        # Crear columnas para cada sugerencia
        for idx, row in suggestions_df.iterrows():
            col1, col2, col3, col4 = st.columns([3, 2, 1, 2])
            with col1:
                st.write(f"**{row['detalle']}**")
                st.caption(f"Normalizado: {row['detalle_norm']}")
            with col2:
                st.write(f"Sugerida: **{row['sugerida']}**")
                st.caption(f"Fuente: {row['fuente']} (confianza: {row['confianza']:.1f})")
            with col3:
                accept = st.checkbox("Aceptar", key=f"accept_{idx}")
                suggestions_df.loc[idx, "aceptar"] = accept
            with col4:
                manual_cat = st.selectbox("Manual", options=categories, key=f"manual_{idx}")
                if manual_cat != "Sin categoría":
                    suggestions_df.loc[idx, "manual"] = manual_cat
        
        apply_selected = st.form_submit_button("Aplicar seleccionadas")
        if apply_selected:
            to_apply = suggestions_df.copy()
            
            # Filtrar solo las aceptadas
            accepted = to_apply[to_apply["aceptar"] == True].copy()
            
            if not accepted.empty:
                # Crear DataFrame para aplicar cambios
                edits_df = pd.DataFrame()
                for _, row in accepted.iterrows():
                    # Buscar la fila original en dfv
                    original_row = dfv[dfv["unique_key"] == row["unique_key"]]
                    if not original_row.empty:
                        edit_row = original_row.iloc[0].copy()
                        # Usar categoría manual si se especificó, sino la sugerida
                        edit_row["categoria"] = row["manual"] if row["manual"] else row["sugerida"]
                        edits_df = pd.concat([edits_df, pd.DataFrame([edit_row])], ignore_index=True)
                
                if not edits_df.empty:
                    # Aplicar cambios
                    updated = apply_edits(conn, edits_df)
                    try:
                        learned = update_categoria_map_from_df(conn, edits_df)
                        if learned:
                            st.info(f"Aprendidas {learned} reglas de categoría por 'detalle_norm'. Se aplicarán en futuras cargas.")
                    except Exception:
                        pass
                    st.success(f"Aplicadas {updated} sugerencias de categoría.")
                    st.rerun()

st.markdown("### Tabla editable")

# Mostrar estadísticas de la tabla filtrada
if not dfv.empty:
    total_transactions = len(dfv)
    total_amount = dfv["monto"].abs().sum()
    avg_amount = dfv["monto"].abs().mean()
    
    # Métricas de la tabla
    col_stats1, col_stats2, col_stats3 = st.columns(3)
    with col_stats1:
        st.metric("📊 Transacciones", f"{total_transactions:,}")
    with col_stats2:
        st.metric("💰 Total", f"${total_amount:,.0f}")
    with col_stats3:
        st.metric("📈 Promedio", f"${avg_amount:,.0f}")
    
    st.markdown("---")

MANUAL_ROW_KEY = "__manual__"
display_cols = [
    "fecha",
    "detalle",
    "monto",  # editable real
    "categoria",
    "nota_usuario",
    "unique_key",  # para detectar eliminaciones
]
existing_cols = [c for c in display_cols if c in dfv.columns or c == "monto"]

# Preparar vista editable:
df_view = dfv.copy()
df_view["monto_bruto_abs"] = df_view["monto"].abs()
if "monto_real" in df_view.columns:
    mask_mr = pd.to_numeric(df_view["monto_real"], errors="coerce").fillna(0) > 0
    df_view["monto"] = np.where(mask_mr, pd.to_numeric(df_view["monto_real"], errors="coerce").abs(), df_view["monto_bruto_abs"])
else:
    df_view["monto"] = df_view["monto_bruto_abs"]

if "categoria" not in df_view.columns:
    df_view["categoria"] = "Sin categoría"
else:
    df_view["categoria"] = df_view["categoria"].fillna("Sin categoría")
    # Si hay categorías que ya no están en la lista activa, reasignar a 'Sin categoría'
    df_view["categoria"] = df_view["categoria"].where(df_view["categoria"].isin(categories), "Sin categoría")

if "nota_usuario" not in df_view.columns:
    df_view["nota_usuario"] = ""
else:
    df_view["nota_usuario"] = df_view["nota_usuario"].fillna("")

df_table_cols = [c for c in existing_cols if c in df_view.columns]
df_table = df_view[df_table_cols].copy()

# Mantener cambios no guardados entre reruns (por gestión de categorías, etc.)
draft_key = "draft_table_v1"
if draft_key in st.session_state:
    draft = st.session_state[draft_key]
    if isinstance(draft, pd.DataFrame) and len(draft) > 0 and "unique_key" in draft.columns:
        base = df_table.set_index("unique_key")
        dset = draft.set_index("unique_key")
        # Alinear a borrados visibles
        base = base.loc[base.index.intersection(dset.index)]
        for col in ["monto", "categoria", "nota_usuario"]:
            if col in base.columns and col in dset.columns:
                base[col] = dset[col].reindex(base.index)
        df_table = base.reset_index()

# Controles de ordenamiento (click-en-header aún no es fiable en st.data_editor)
sort_candidates = ["fecha", "monto", "categoria", "detalle"]
sort_cols = [c for c in sort_candidates if c in df_table.columns]

if sort_cols:
    col_sort1, col_sort2 = st.columns([2, 1])
    with col_sort1:
        sort_by = st.selectbox(
            "Ordenar por",
            options=sort_cols,
            index=0,
            help="Ordena la tabla antes de editar"
        )
    with col_sort2:
        sort_desc = st.toggle("Descendente", value=True)

    # Aplicar orden de manera estable (para que no 'salten' filas al editar)
    if sort_by == "fecha":
        # asegurar tipo datetime para orden correcto
        _tmp = pd.to_datetime(df_table["fecha"], errors="coerce")
        df_table = df_table.assign(_f=_tmp).sort_values(by="_f", ascending=not sort_desc, kind="mergesort").drop(columns="_f")
    elif sort_by == "monto":
        # ordenar usando valor numérico seguro
        _m = pd.to_numeric(df_table["monto"], errors="coerce")
        df_table = df_table.assign(_m=_m).sort_values(by="_m", ascending=not sort_desc, kind="mergesort").drop(columns="_m")
    else:
        df_table = df_table.sort_values(by=sort_by, ascending=not sort_desc, kind="mergesort")

manual_row_template = {
    "fecha": pd.Timestamp.today().normalize(),
    "detalle": "",
    "monto": 0.0,
    "categoria": "Sin categoría",
    "nota_usuario": "",
    "unique_key": MANUAL_ROW_KEY,
}
df_table_display = pd.concat(
    [pd.DataFrame([manual_row_template]), df_table],
    ignore_index=True
)
df_table_display["accion"] = ""
ui_cols = ["accion"] + [c for c in df_table_display.columns if c != "accion"]
df_table_display = df_table_display[ui_cols]

def register_tombstones(conn, unique_keys):
    clean = [uk for uk in (unique_keys or []) if isinstance(uk, str) and uk.strip()]
    if not clean:
        return
    try:
        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            with engine.begin() as cx:
                for uk in clean:
                    cx.execute(
                        text("INSERT INTO movimientos_borrados (unique_key) VALUES (:uk) ON CONFLICT (unique_key) DO NOTHING"),
                        {"uk": uk},
                    )
        else:
            for uk in clean:
                try:
                    conn.execute("INSERT OR IGNORE INTO movimientos_borrados (unique_key) VALUES (?)", (uk,))
                except Exception:
                    pass
            conn.commit()
    except Exception as tomb_e:
        st.caption(f"(No se pudieron registrar tombstones: {tomb_e})")

def delete_and_track(conn, unique_keys):
    clean = [uk for uk in (unique_keys or []) if isinstance(uk, str) and uk.strip()]
    if not clean:
        return 0
    deleted = 0
    try:
        deleted = delete_transactions(conn, unique_keys=clean)
    except Exception as del_e:
        st.error(f"No se pudo eliminar: {del_e}")
        return 0
    if deleted > 0:
        register_tombstones(conn, clean)
    return deleted

def normalize_detalle_for_manual(text_value: str) -> str:
    s = (text_value or "").strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("\n", " ").replace("\t", " ")
    s = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s)
    return " ".join(s.upper().split())

# Formulario de edición mejorado
st.markdown("**✏️ Edita las transacciones y guarda los cambios**")
st.caption("La primera fila queda reservada para agregar un gasto manual rápido. Completa ahí y guarda para insertarlo.")

editable = st.data_editor(
    df_table_display,
    num_rows="dynamic",  # permite borrar filas en la propia tabla
    use_container_width=True,
    key="tabla_gastos",
    column_config={
        "accion": st.column_config.SelectboxColumn(
            label="",
            options=["", "🗑️"],
            help="Elige 🗑️ para pedir la eliminación inmediata de la fila",
            width="small",
        ),
        "fecha": st.column_config.DatetimeColumn(
            format="YYYY-MM-DD",
            help="Fecha de la transacción"
        ),
        "detalle": st.column_config.TextColumn(
            help="Descripción del movimiento"
        ),
        "monto": st.column_config.NumberColumn(
            format="%.0f", 
            min_value=0.0,
            help="Monto de la transacción (editable)"
        ),
        "categoria": st.column_config.SelectboxColumn(
            options=categories, 
            default="Sin categoría",
            help="Selecciona la categoría"
        ),
        "nota_usuario": st.column_config.TextColumn(
            help="Agrega notas personales"
        ),
        "unique_key": st.column_config.TextColumn(
            disabled=True,
            help="Identificador único (no editable)"
        ),
    },
    hide_index=True,
)

col_s, col_d, col_info = st.columns([1, 1, 2])
with col_s:
    save_clicked = st.button(
        "💾 Guardar cambios",
        help="Guarda todos los cambios en la base de datos",
        use_container_width=True,
    )
with col_d:
    download_preview = editable.copy().drop(columns=["accion"], errors="ignore")
    if "unique_key" in download_preview.columns:
        download_preview = download_preview[download_preview["unique_key"] != MANUAL_ROW_KEY]
    st.download_button(
        "📥 Descargar CSV",
        data=download_preview.to_csv(index=False).encode("utf-8"),
        file_name="movimientos_enriquecidos.csv",
        mime="text/csv",
        use_container_width=True,
    )
with col_info:
    if save_clicked:
        st.info("🔄 Procesando cambios...")

# Detectar solicitudes de eliminación inmediata
delete_requests = pd.DataFrame()
try:
    if "accion" in editable.columns:
        delete_requests = editable[
            (editable["accion"] == "🗑️")
            & editable["unique_key"].notna()
            & (editable["unique_key"] != MANUAL_ROW_KEY)
        ]
except Exception:
    delete_requests = pd.DataFrame()

if not delete_requests.empty:
    candidate = delete_requests.iloc[0]
    st.session_state["pending_delete"] = {
        "unique_key": str(candidate.get("unique_key", "")),
        "detalle": candidate.get("detalle", ""),
        "fecha": candidate.get("fecha"),
        "monto": candidate.get("monto"),
    }
    editable.loc[editable["unique_key"] == candidate.get("unique_key"), "accion"] = ""

pending_delete = st.session_state.get("pending_delete")
if pending_delete:
    fecha_txt = ""
    try:
        fecha_txt = pd.to_datetime(pending_delete.get("fecha")).strftime("%Y-%m-%d")
    except Exception:
        fecha_txt = str(pending_delete.get("fecha") or "")
    resumen = f"{fecha_txt} · {pending_delete.get('detalle','')}"
    st.warning(f"¿Eliminar definitivamente **{resumen}**?")
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("Sí, borrar", type="primary"):
            deleted = delete_and_track(conn, [pending_delete.get("unique_key")])
            if deleted:
                st.success("Movimiento eliminado.")
            st.session_state["pending_delete"] = None
            st.rerun()
    with col_no:
        if st.button("Cancelar"):
            st.session_state["pending_delete"] = None
            st.rerun()
    
if save_clicked:
    editable_clean = editable.copy()
    editable_clean = editable_clean.drop(columns=["accion"], errors="ignore")
    manual_mask = (
        editable_clean["unique_key"].isin([None, "", MANUAL_ROW_KEY])
        if "unique_key" in editable_clean.columns
        else pd.Series(False, index=editable_clean.index)
    )
    manual_rows = editable_clean[manual_mask].copy() if "unique_key" in editable_clean.columns else pd.DataFrame()
    editable_existing = editable_clean[~manual_mask].copy() if "unique_key" in editable_clean.columns else editable_clean.copy()

    before_keys = set(df_table.get("unique_key", pd.Series(dtype=str)).dropna().astype(str))
    after_keys = set(editable_existing.get("unique_key", pd.Series(dtype=str)).dropna().astype(str))
    to_delete_keys = sorted(before_keys - after_keys)

    edits = editable_existing.dropna(subset=["unique_key"]).copy()
    edits.rename(columns={"monto": "monto_real"}, inplace=True)

    updated = apply_edits(conn, edits) if not edits.empty else 0
    try:
        learned = update_categoria_map_from_df(conn, edits) if not edits.empty else 0
        if learned:
            st.info(f"Aprendidas {learned} reglas de categoría por 'detalle_norm'.")
    except Exception:
        pass

    deleted = delete_and_track(conn, to_delete_keys)

    inserted = 0
    manual_errors = []

    def _insert_manual_from_row(row):
        detalle_man = (row.get("detalle") or "").strip()
        monto_man = float(row.get("monto") or 0)
        if not detalle_man or monto_man <= 0:
            return False, "Completa 'Detalle' y un monto mayor a 0 en la fila manual."
        fecha_man = row.get("fecha") or pd.Timestamp.today()
        try:
            fstr = pd.to_datetime(fecha_man).strftime("%Y-%m-%d")
        except Exception:
            fstr = pd.Timestamp.today().strftime("%Y-%m-%d")
        detalle_norm_man = normalize_detalle_for_manual(detalle_man)
        key_material = f"{fstr}|{float(monto_man):.2f}|{detalle_norm_man}"
        uk = "m:" + hashlib.sha1(key_material.encode("utf-8")).hexdigest()[:16]
        row_db = {
            "unique_key": uk,
            "fecha": fstr,
            "detalle": detalle_man,
            "detalle_norm": detalle_norm_man,
            "monto": float(monto_man),
            "monto_real": float(monto_man),
            "categoria": row.get("categoria") or "Sin categoría",
            "nota_usuario": row.get("nota_usuario") or "",
            "es_gasto": True,
            "es_transferencia_o_abono": False,
        }
        inserted_ok = False
        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            with engine.begin() as cx:
                cx.execute(
                    text(
                        """
                        INSERT INTO movimientos (unique_key, fecha, detalle, detalle_norm, monto, categoria, nota_usuario, monto_real, es_gasto, es_transferencia_o_abono)
                        VALUES (:unique_key, :fecha, :detalle, :detalle_norm, :monto, :categoria, :nota_usuario, :monto_real, :es_gasto, :es_transferencia_o_abono)
                        ON CONFLICT (unique_key) DO NOTHING
                        """
                    ),
                    row_db,
                )
                got = cx.execute(text("SELECT 1 FROM movimientos WHERE unique_key = :uk"), {"uk": uk}).fetchone()
                inserted_ok = bool(got)
        else:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO movimientos
                        (unique_key, fecha, detalle, detalle_norm, monto, categoria, nota_usuario, monto_real, es_gasto, es_transferencia_o_abono)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_db["unique_key"],
                        row_db["fecha"],
                        row_db["detalle"],
                        row_db["detalle_norm"],
                        row_db["monto"],
                        row_db["categoria"],
                        row_db["nota_usuario"],
                        row_db["monto_real"],
                        int(bool(row_db["es_gasto"])),
                        int(bool(row_db["es_transferencia_o_abono"])),
                    ),
                )
                conn.commit()
                inserted_ok = True
            except Exception as e:
                return False, f"Error SQLite: {e}"
        return inserted_ok, ""

    if not manual_rows.empty:
        for _, mrow in manual_rows.iterrows():
            ok, err = _insert_manual_from_row(mrow)
            if ok:
                inserted += 1
            elif err:
                manual_errors.append(err)

    messages = []
    if updated:
        messages.append(f"Actualizadas {updated} fila(s).")
    if deleted:
        messages.append(f"Eliminadas {deleted} fila(s).")
    if inserted:
        messages.append(f"Agregados {inserted} gasto(s) manual(es).")
    if manual_errors:
        for msg in manual_errors:
            st.warning(msg)
    if messages:
        st.success(" ".join(messages))
    else:
        st.info("No hubo cambios para guardar.")

    st.rerun()

# Eliminación ahora se maneja directamente quitando filas en la tabla o usando la columna de acciones

st.markdown("### Más análisis")
df_month2 = df_analysis.copy()
if not df_month2.empty:
    df_month2["mes"] = df_month2["fecha"].dt.to_period("M").astype(str)
    amt_col = "monto" if "monto" in df_month2.columns else "monto_real"
    mensual2 = (
        df_month2.assign(_amt=np.abs(pd.to_numeric(df_month2[amt_col], errors="coerce").fillna(0)))
        .groupby("mes")["_amt"]
        .sum()
        .reset_index()
        .rename(columns={"_amt": "monto"})
        .sort_values("mes")
    )
    chart_mensual = (
        alt.Chart(mensual2)
        .mark_line(
            point={"size": 60},
            stroke="#133c60",
            strokeWidth=3,
        )
        .encode(
            x=alt.X("mes:N", title="Mes"),
            y=alt.Y("monto:Q", title="Total de Gastos", axis=alt.Axis(format=",.0f")),
            tooltip=[
                alt.Tooltip("mes:N", title="Mes"),
                alt.Tooltip("monto:Q", format=",.0f", title="Total")
            ]
        )
        .properties(
            height=250,
            title={
                "text": "Tendencia de Gastos Mensuales",
                "fontSize": 16,
                "fontWeight": "bold",
                "color": "#133c60"
            }
        )
        .configure_view(stroke=None)
        .configure_axis(grid=False)
    )
    st.altair_chart(chart_mensual, use_container_width=True)
else:
    st.info("Carga algunos movimientos para ver la tendencia mensual.")

# === Proyección de gastos del mes (por categoría) ===
st.markdown("### Proyección de gastos del mes")
try:
    # Base sin filtros de UI para calcular promedios mensuales históricos
    base_hist = df_base_compare.copy()
    if not base_hist.empty:
        base_hist["mes"] = base_hist["fecha"].dt.to_period("M").astype(str)
        # Agregado mensual por categoría
        amt_c = "monto" if "monto" in base_hist.columns else "monto_real_plot"
        base_hist_amt = base_hist.assign(_amt=np.abs(pd.to_numeric(base_hist[amt_c], errors="coerce").fillna(0)))
        monthly_by_cat = (
            base_hist_amt.groupby(["categoria", "mes"])['_amt']
            .sum().reset_index().rename(columns={'_amt': 'total_mes'})
        )

        # Reglas para incluir categorías
        # 1) Al menos 2 meses históricos
        # 2) Si la categoría está presente en TODOS los últimos K meses (K=3), se incluye SIEMPRE
        # 3) Si no cumple (2), entonces exigir variabilidad razonable (cv <= 1.0) y media >= 3.000
        stats = monthly_by_cat.groupby("categoria")["total_mes"].agg(["count", "mean", "std"]).reset_index()
        stats.rename(columns={"count": "num_meses", "mean": "prom_mensual", "std": "desv"}, inplace=True)

        # Determinar presencia por categoría en los últimos K meses
        months_sorted = sorted(monthly_by_cat["mes"].unique())
        k = 3 if len(months_sorted) >= 3 else len(months_sorted)
        last_k = set(months_sorted[-k:]) if k > 0 else set()
        cat_to_months = monthly_by_cat.groupby("categoria")["mes"].apply(lambda s: set(s.tolist())).to_dict()
        stats["presente_ultimos_k"] = stats["categoria"].apply(lambda c: last_k.issubset(cat_to_months.get(c, set())) if last_k else False)

        # Coeficiente de variación (cv)
        stats["cv"] = stats.apply(lambda r: (r["desv"] / r["prom_mensual"]) if r["prom_mensual"] > 0 else np.inf, axis=1)

        # Construir conjunto válido
        base_mask = stats["num_meses"] >= 2
        stable_mask = stats["presente_ultimos_k"]
        conservative_mask = (stats["prom_mensual"] >= 3000) & (stats["cv"] <= 1.0)
        valid = stats[base_mask & (stable_mask | conservative_mask)].copy()

        # Excluir categorías claramente ocasionales por nombre (heurística simple)
        blacklist_words = {"viaje", "lima", "vacaciones"}
        def is_blacklisted(cat: str) -> bool:
            s = str(cat or "").lower()
            return any(w in s for w in blacklist_words)
        valid = valid[~valid["categoria"].apply(is_blacklisted)]

        # Proyección total por categoría = promedio mensual histórico
        proj = valid[["categoria", "prom_mensual"]].sort_values("prom_mensual", ascending=False)

        # Acumulado del mes actual por categoría (visible o rango seleccionado)
        cur = dfv.copy()
        cur_amt_col = "monto" if "monto" in cur.columns else "monto_real_plot"
        cur_agg = (
            cur.assign(_amt=np.abs(pd.to_numeric(cur[cur_amt_col], errors="coerce").fillna(0)))
               .groupby("categoria")['_amt']
               .sum().reset_index().rename(columns={'_amt': 'actual_mes'})
        )

        # Merge proyección vs actual y calcular restante sugerido
        proj_view = proj.merge(cur_agg, on="categoria", how="left").fillna({"actual_mes": 0.0})
        proj_view["restante_estimado"] = (proj_view["prom_mensual"] - proj_view["actual_mes"]).clip(lower=0)

        # Totales
        total_proj = float(proj_view["prom_mensual"].sum())
        total_actual = float(proj_view["actual_mes"].sum())
        total_restante = float(proj_view["restante_estimado"].sum())

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Proyección mensual (categorías estables)", f"${total_proj:,.0f}")
        with c2:
            st.metric("Acumulado mes actual (esas categorías)", f"${total_actual:,.0f}")
        with c3:
            st.metric("Restante estimado del mes", f"${total_restante:,.0f}")

        # Tabla detallada
        st.dataframe(
            proj_view.rename(columns={
                "categoria": "Categoría",
                "prom_mensual": "Promedio mensual",
                "actual_mes": "Actual mes",
                "restante_estimado": "Restante estimado",
            }),
            use_container_width=True,
        )
    else:
        st.info("Aún no hay suficientes datos para proyectar.")
except Exception as _proj_e:
    st.warning(f"No se pudo calcular la proyección: {_proj_e}")

# Botón "Reparar montos" para sincronizar monto = abs(monto_real) para "Gasto"
st.markdown("### Herramientas de mantenimiento")
if st.button("Reparar montos"):
    try:
        # Buscar discrepancias entre monto y monto_real para gastos
        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            with engine.begin() as cx:
                result = cx.execute(text("""
                    UPDATE movimientos 
                    SET monto = ABS(monto_real) 
                    WHERE monto_real IS NOT NULL 
                    AND monto_real > 0 
                    AND (monto IS NULL OR monto = 0 OR ABS(monto) != monto_real)
                """))
                updated_count = result.rowcount
        else:
            cur = conn.execute("""
                UPDATE movimientos 
                SET monto = ABS(monto_real) 
                WHERE monto_real IS NOT NULL 
                AND monto_real > 0 
                AND (monto IS NULL OR monto = 0 OR ABS(monto) != monto_real)
            """)
            updated_count = cur.rowcount
            conn.commit()
        
        st.success(f"Reparados {updated_count} montos discrepantes.")
        st.rerun()
    except Exception as e:
        st.error(f"Error al reparar montos: {e}")

with st.expander("Movimientos ignorados"):
    try:
        def _fetch_ignored_pg(engine):
            # Discover available columns
            with engine.connect() as cx:
                cols = [r[0] for r in cx.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='movimientos_ignorados'")).fetchall()]
            sel_cols = [c for c in ["id","unique_key","payload","created_at"] if c in cols]
            if not sel_cols:
                return pd.DataFrame()
            q = f"SELECT {', '.join(sel_cols)} FROM movimientos_ignorados ORDER BY {('created_at' if 'created_at' in sel_cols else sel_cols[0])} DESC"
            with engine.connect() as cx:
                return pd.read_sql_query(text(q), cx)

        def _fetch_ignored_sqlite(conn):
            cols = pd.read_sql_query("PRAGMA table_info(movimientos_ignorados)", conn)["name"].tolist()
            sel_cols = [c for c in ["id","unique_key","payload","created_at"] if c in cols]
            if not sel_cols:
                return pd.DataFrame()
            order_col = "created_at" if "created_at" in sel_cols else sel_cols[0]
            q = f"SELECT {', '.join(sel_cols)} FROM movimientos_ignorados ORDER BY {order_col} DESC"
            return pd.read_sql_query(q, conn)

        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            ignored_df = _fetch_ignored_pg(engine)
        else:
            ignored_df = _fetch_ignored_sqlite(conn)

        if not ignored_df.empty:
            # Normalize missing columns for UI
            for c in ["id","unique_key","payload","created_at"]:
                if c not in ignored_df.columns:
                    ignored_df[c] = None

            # Parsear payload para mostrar nombre (detalle) y monto en la grilla
            def _parse_payload_to_cols(_df: pd.DataFrame) -> pd.DataFrame:
                if _df is None or _df.empty:
                    return _df
                nombres, montos = [], []
                for _, r in _df.iterrows():
                    raw = r.get("payload")
                    try:
                        obj = json.loads(raw) if raw else {}
                    except Exception:
                        obj = {}
                    # nombre: preferir 'detalle', luego 'detalle_norm'
                    nombre = obj.get("detalle") or obj.get("detalle_norm") or ""
                    # monto: preferir monto_real > 0, luego 'monto'
                    m = obj.get("monto_real")
                    if m in (None, "", 0):
                        m = obj.get("monto")
                    try:
                        # tolerar coma decimal
                        m = float(str(m).replace(",", ".")) if m is not None else None
                    except Exception:
                        m = None
                    nombres.append(nombre)
                    montos.append(m)
                _df["nombre"] = nombres
                _df["monto"] = montos
                return _df

            # Enriquecer ignored_df con nombre y monto
            ignored_df = _parse_payload_to_cols(ignored_df)

            st.write(f"Total de movimientos ignorados: {len(ignored_df)}")
            st.dataframe(
                ignored_df[[c for c in ["id", "created_at", "nombre", "monto", "unique_key"] if c in ignored_df.columns]],
                use_container_width=True,
                height=280
            )

            sel_ids = st.multiselect("Selecciona IDs para reincorporar", [int(x) for x in ignored_df["id"].dropna().astype(int).tolist()])
            col_restore, col_restore_all, col_clear = st.columns(3)

            def _restore_rows(subdf):
                restored = 0
                if isinstance(conn, dict) and conn.get("pg"):
                    engine = conn["engine"]
                    with engine.begin() as cx:
                        for _, rr in subdf.iterrows():
                            uk = rr.get("unique_key")
                            payload = rr.get("payload")
                            if not payload:
                                continue
                            row = json.loads(payload)
                            cx.execute(text("DELETE FROM movimientos WHERE unique_key = :uk"), {"uk": uk})
                            cx.execute(text(
                                """
                                INSERT INTO movimientos (unique_key, fecha, detalle, detalle_norm, monto, categoria, nota_usuario, monto_real, es_gasto, es_transferencia_o_abono)
                                VALUES (:unique_key, :fecha, :detalle, :detalle_norm, :monto, :categoria, :nota_usuario, :monto_real, :es_gasto, :es_transferencia_o_abono)
                                """
                            ), row)
                            if "id" in rr and pd.notna(rr["id"]):
                                cx.execute(text("DELETE FROM movimientos_ignorados WHERE id = :id"), {"id": int(rr["id"])})
                        restored += 1
                else:
                    for _, rr in subdf.iterrows():
                        uk = rr.get("unique_key")
                        payload = rr.get("payload")
                        if not payload:
                            continue
                        row = json.loads(payload)
                        conn.execute("DELETE FROM movimientos WHERE unique_key = ?", (uk,))
                        conn.execute(
                            """
                            INSERT INTO movimientos (unique_key, fecha, detalle, detalle_norm, monto, categoria, nota_usuario, monto_real, es_gasto, es_transferencia_o_abono)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                row.get("unique_key"), row.get("fecha"), row.get("detalle"), row.get("detalle_norm"),
                                row.get("monto"), row.get("categoria"), row.get("nota_usuario"), row.get("monto_real"),
                                row.get("es_gasto"), row.get("es_transferencia_o_abono"),
                            ),
                        )
                        if "id" in rr and pd.notna(rr["id"]):
                            conn.execute("DELETE FROM movimientos_ignorados WHERE id = ?", (int(rr["id"]),))
                        conn.commit()
                        restored += 1
                return restored

            with col_restore:
                if st.button("Reincorporar seleccionados") and sel_ids:
                    sub = ignored_df[ignored_df["id"].astype("Int64").isin(sel_ids)]
                    restored = _restore_rows(sub)
                    st.success(f"Reincorporados {restored} movimientos.")
                    st.rerun()

            with col_restore_all:
                if st.button("Reincorporar TODOS"):
                    restored = _restore_rows(ignored_df)
                    st.success(f"Reincorporados {restored} movimientos.")
                    st.rerun()

            with col_clear:
                if st.button("Vaciar lista de ignorados"):
                    try:
                        if isinstance(conn, dict) and conn.get("pg"):
                            engine = conn["engine"]
                            with engine.begin() as cx:
                                cx.execute(text("DELETE FROM movimientos_ignorados"))
                        else:
                            conn.execute("DELETE FROM movimientos_ignorados")
                            conn.commit()
                        st.success("Lista de ignorados vaciada.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al limpiar ignorados: {e}")
        else:
            st.info("No hay movimientos ignorados.")
    except Exception as e:
        st.warning(f"No se pudo cargar movimientos ignorados: {e}")

# === Diagnóstico rápido de la Base de Datos ===
with st.expander("🔎 Diagnóstico de Base de Datos"):
    try:
        # Identificar backend
        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            backend = "Postgres"
            try:
                from sqlalchemy.engine import Engine
                url_str = engine.url.render_as_string(hide_password=True)
            except Exception:
                url_str = "(no disponible)"
            st.write(f"**Backend:** {backend}")
            st.code(url_str, language=None)

            # Conteos clave
            with engine.connect() as cx:
                n_mov = cx.execute(text("SELECT COUNT(*) FROM movimientos")).scalar()
                n_ign = cx.execute(text("SELECT COUNT(*) FROM movimientos_ignorados")).scalar() if cx.execute(text("SELECT to_regclass('public.movimientos_ignorados')")).scalar() == 'movimientos_ignorados' else 0
                # Columnas presentes
                cols = [r[0] for r in cx.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='movimientos' ORDER BY ordinal_position")).fetchall()]
        else:
            backend = "SQLite"
            st.write(f"**Backend:** {backend}")
            # Ruta del archivo SQLite
            try:
                db_path = getattr(conn, 'database', None) or getattr(conn, 'db', None) or "(ruta no disponible)"
            except Exception:
                db_path = "(ruta no disponible)"
            st.code(str(db_path), language=None)

            # Conteos clave
            n_mov = pd.read_sql_query("SELECT COUNT(*) as c FROM movimientos", conn)["c"].iloc[0]
            try:
                n_ign = pd.read_sql_query("SELECT COUNT(*) as c FROM movimientos_ignorados", conn)["c"].iloc[0]
            except Exception:
                n_ign = 0
            # Columnas presentes
            cols = pd.read_sql_query("PRAGMA table_info(movimientos)", conn)["name"].tolist()

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Filas en movimientos", f"{n_mov:,}")
        with col_b:
            st.metric("Filas ignoradas", f"{n_ign:,}")
        with col_c:
            st.metric("Columnas en movimientos", f"{len(cols)}")
        st.caption("Columnas detectadas en 'movimientos':")
        st.code(", ".join(cols), language=None)

        st.markdown("---")
        st.caption("Muestra 5 filas (para confirmar contenido actual):")
        try:
            if backend == "Postgres":
                with engine.connect() as cx:
                    sample_df = pd.read_sql_query(text("SELECT * FROM movimientos ORDER BY fecha DESC LIMIT 5"), cx)
            else:
                sample_df = pd.read_sql_query("SELECT * FROM movimientos ORDER BY fecha DESC LIMIT 5", conn)
            st.dataframe(sample_df, use_container_width=True)
        except Exception as e:
            st.info(f"No se pudo leer muestra: {e}")

        st.markdown("---")
        st.caption("Acciones destructivas (úsalas solo si quieres empezar de cero)")
        colx, coly = st.columns(2)
        with colx:
            if st.button("🧹 Vaciar movimientos (DELETE)"):
                try:
                    if backend == "Postgres":
                        with engine.begin() as cx:
                            cx.execute(text("DELETE FROM movimientos"))
                    else:
                        conn.execute("DELETE FROM movimientos")
                        conn.commit()
                    st.success("Tabla 'movimientos' vaciada. Sube tu CSV nuevamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo vaciar movimientos: {e}")
        with coly:
            if st.button("🧹 Vaciar ignorados (DELETE)"):
                try:
                    if backend == "Postgres":
                        with engine.begin() as cx:
                            cx.execute(text("DELETE FROM movimientos_ignorados"))
                    else:
                        conn.execute("DELETE FROM movimientos_ignorados")
                        conn.commit()
                    st.success("Tabla 'movimientos_ignorados' vaciada.")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo vaciar ignorados: {e}")

    except Exception as e:
        st.error(f"Diagnóstico falló: {e}")

# === Exportar base completa (backup) ===
st.markdown("### Exportar base de datos (backup)")
try:
    # Leer TODA la tabla movimientos sin filtros de UI
    if isinstance(conn, dict) and conn.get("pg"):
        engine = conn["engine"]
        with engine.connect() as cx:
            df_all = pd.read_sql_query(text("SELECT * FROM movimientos ORDER BY fecha"), cx)
    else:
        df_all = pd.read_sql_query("SELECT * FROM movimientos ORDER BY fecha", conn)

    if df_all is not None and not df_all.empty:
        csv_bytes = df_all.to_csv(index=False).encode("utf-8")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            "⬇️ Exportar BD completa (CSV)",
            data=csv_bytes,
            file_name=f"movimientos_backup_{ts}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("La tabla 'movimientos' está vacía.")
except Exception as e:
    st.error(f"No se pudo exportar la base: {e}")
