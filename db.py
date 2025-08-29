import os
import sqlite3
from typing import Tuple, Any, List, Optional

import pandas as pd
import numpy as np


DB_PATH_DEFAULT = os.path.join("data", "gastos.db")


def get_conn(db_path: str = DB_PATH_DEFAULT) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER,
            fecha TEXT,
            detalle TEXT,
            monto REAL,
            es_gasto INTEGER,
            es_transferencia_o_abono INTEGER,
            es_compartido_posible INTEGER,
            fraccion_mia_sugerida REAL,
            monto_mio_estimado REAL,
            categoria_sugerida TEXT,
            detalle_norm TEXT,
            -- nuevos campos para flujo actual
            monto_real REAL,
            categoria TEXT,
            nota_usuario TEXT,
            unique_key TEXT UNIQUE
        );
        """
    )
    conn.commit()

    # Migración: agregar columnas si la tabla ya existía sin ellas
    existing = {r[1] for r in conn.execute("PRAGMA table_info(movimientos)").fetchall()}
    for col, ddl in [
        ("monto_real", "ALTER TABLE movimientos ADD COLUMN monto_real REAL"),
        ("categoria", "ALTER TABLE movimientos ADD COLUMN categoria TEXT"),
        ("nota_usuario", "ALTER TABLE movimientos ADD COLUMN nota_usuario TEXT"),
    ]:
        if col not in existing:
            try:
                conn.execute(ddl)
            except Exception:
                pass
    conn.commit()

    # Lista de movimientos ignorados (no reingresar si se eliminaron manualmente)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS movimientos_ignorados (
            unique_key TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()

    # Tabla de categorías (opcional, para persistir lista)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS categorias (
            nombre TEXT UNIQUE
        );
        """
    )
    conn.commit()

    # Mapa de categorías por detalle normalizado (autoetiquetado futuro)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS categoria_map (
            detalle_norm TEXT PRIMARY KEY,
            categoria TEXT
        );
        """
    )
    conn.commit()

def get_categories(conn: sqlite3.Connection) -> List[str]:
    cur = conn.execute("SELECT nombre FROM categorias ORDER BY nombre")
    return [r[0] for r in cur.fetchall()]


def replace_categories(conn: sqlite3.Connection, cats: List[str]) -> None:
    # Replace entire list atomically
    cats = [c.strip() for c in cats if c and isinstance(c, str)]
    with conn:
        conn.execute("DELETE FROM categorias")
        if cats:
            conn.executemany("INSERT OR IGNORE INTO categorias(nombre) VALUES (?)", [(c,) for c in cats])


def update_categoria_map_from_df(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    sub = df[["detalle_norm", "categoria"]].dropna()
    if sub.empty:
        return 0
    sub = sub[(sub["categoria"].notna()) & (sub["categoria"].str.strip() != "")]
    if sub.empty:
        return 0
    rows = sub.drop_duplicates("detalle_norm").values.tolist()
    cur = conn.executemany(
        "INSERT INTO categoria_map(detalle_norm, categoria) VALUES(?, ?) "
        "ON CONFLICT(detalle_norm) DO UPDATE SET categoria=excluded.categoria",
        rows,
    )
    conn.commit()
    return cur.rowcount or 0


def map_categories_for_df(conn: sqlite3.Connection, df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "detalle_norm" not in df.columns:
        return df
    mp = pd.read_sql_query("SELECT detalle_norm, categoria FROM categoria_map", conn)
    if mp.empty:
        return df
    merged = df.merge(mp, on="detalle_norm", how="left", suffixes=(None, "_map"))
    # Completar solo si falta o está vacío
    if "categoria" not in merged.columns:
        merged["categoria"] = merged["categoria_map"]
    else:
        merged["categoria"] = np.where(
            merged["categoria"].isna() | (merged["categoria"].str.strip() == ""),
            merged["categoria_map"],
            merged["categoria"],
        )
    merged = merged.drop(columns=[c for c in ["categoria_map"] if c in merged.columns])
    return merged


def rename_category(conn: sqlite3.Connection, old_name: str, new_name: str) -> None:
    if not old_name or not new_name or old_name == new_name:
        return
    if old_name == "Sin categoría":
        return  # no renombrar base
    with conn:
        conn.execute("UPDATE categorias SET nombre=? WHERE nombre=?", (new_name, old_name))
        conn.execute("INSERT OR IGNORE INTO categorias(nombre) VALUES (?)", (new_name,))
        conn.execute("DELETE FROM categorias WHERE nombre=?", (old_name,))
        conn.execute("UPDATE movimientos SET categoria=? WHERE categoria=?", (new_name, old_name))
        conn.execute("UPDATE categoria_map SET categoria=? WHERE categoria=?", (new_name, old_name))


def _compute_unique_key_row(row: pd.Series) -> str:
    # Prefer explicit id if present; else hash of salient fields.
    if pd.notna(row.get("id", None)):
        return f"id:{int(row['id'])}"
    fecha = str(row.get("fecha", ""))
    monto = str(row.get("monto", ""))
    detalle_norm = str(row.get("detalle_norm", ""))
    return f"h:{hash((fecha, monto, detalle_norm))}"


def upsert_transactions(conn: sqlite3.Connection, df: pd.DataFrame) -> Tuple[int, int]:
    df = df.copy()
    if "unique_key" not in df.columns:
        df["unique_key"] = df.apply(_compute_unique_key_row, axis=1)

    # Excluir ignorados por historial (p. ej., eliminados previamente)
    try:
        ignored = pd.read_sql_query("SELECT unique_key FROM movimientos_ignorados", conn)["unique_key"].tolist()
    except Exception:
        ignored = []
    if ignored:
        df = df[~df["unique_key"].isin(set(ignored))]

    cols = [
        "id",
        "fecha",
        "detalle",
        "monto",
        "es_gasto",
        "es_transferencia_o_abono",
        "es_compartido_posible",
        "fraccion_mia_sugerida",
        "monto_mio_estimado",
        "categoria_sugerida",
        "detalle_norm",
        # nuevos
        "monto_real",
        "categoria",
        "nota_usuario",
        "unique_key",
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = None

    def to_py(v: Any):
        if v is None:
            return None
        if isinstance(v, pd.Timestamp):
            return v.date().isoformat()
        if isinstance(v, (np.generic,)):
            return v.item()
        return v

    def to_date_str(v: Any):
        if pd.isna(v) or v is None:
            return None
        try:
            return pd.to_datetime(v, errors="coerce").date().isoformat()
        except Exception:
            return str(v)

    def to_int_bool(v: Any):
        if pd.isna(v) or v is None:
            return None
        if isinstance(v, (bool, np.bool_)):
            return int(bool(v))
        try:
            return int(v)
        except Exception:
            return None

    def to_float(v: Any):
        if pd.isna(v) or v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    def default_monto_real(row: pd.Series) -> float:
        # Prefer existing fields if present
        if not pd.isna(row.get("monto_real", np.nan)):
            try:
                return float(row["monto_real"]) if pd.notna(row["monto_real"]) else None
            except Exception:
                pass
        if not pd.isna(row.get("monto_mio_estimado", np.nan)):
            try:
                return abs(float(row["monto_mio_estimado"]))
            except Exception:
                pass
        try:
            m = float(row.get("monto", 0))
        except Exception:
            m = 0.0
        return abs(m) if m < 0 else 0.0

    rows: List[tuple] = []
    for _, r in df[cols].iterrows():
        rows.append(
            (
                None if pd.isna(r["id"]) else int(r["id"]),
                to_date_str(r["fecha"]),
                None if pd.isna(r["detalle"]) else str(r["detalle"]),
                to_float(r["monto"]),
                to_int_bool(r["es_gasto"]),
                to_int_bool(r["es_transferencia_o_abono"]),
                to_int_bool(r["es_compartido_posible"]),
                to_float(r["fraccion_mia_sugerida"]),
                to_float(r["monto_mio_estimado"]),
                None if pd.isna(r["categoria_sugerida"]) else str(r["categoria_sugerida"]),
                None if pd.isna(r["detalle_norm"]) else str(r["detalle_norm"]),
                # nuevos
                to_float(default_monto_real(r)),
                None if pd.isna(r.get("categoria", None)) else str(r.get("categoria")),
                None if pd.isna(r.get("nota_usuario", None)) else str(r.get("nota_usuario")),
                str(r["unique_key"]),
            )
        )

    sql = (
        "INSERT OR IGNORE INTO movimientos (id, fecha, detalle, monto, es_gasto, es_transferencia_o_abono, "
        "es_compartido_posible, fraccion_mia_sugerida, monto_mio_estimado, categoria_sugerida, detalle_norm, "
        "monto_real, categoria, nota_usuario, unique_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    cur = conn.executemany(sql, rows)
    conn.commit()
    inserted = cur.rowcount if cur.rowcount is not None else 0

    # For rows that already existed, we can optionally perform an UPDATE to refresh editable fields.
    # Keep it simple: no overwrite on ingest except via explicit save from UI.
    ignored = len(rows) - inserted
    return inserted, ignored


def load_all(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM movimientos", conn)
    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        for c in ["es_gasto", "es_transferencia_o_abono", "es_compartido_posible"]:
            if c in df.columns:
                df[c] = df[c].apply(lambda x: bool(int(x)) if pd.notna(x) else False)
    return df


def apply_edits(conn: sqlite3.Connection, df_edits: pd.DataFrame) -> int:
    # Update only editable fields by id/unique_key.
    editable_cols = [
        # legacy fields
        "es_gasto",
        "es_transferencia_o_abono",
        "es_compartido_posible",
        "fraccion_mia_sugerida",
        "monto_mio_estimado",
        "categoria_sugerida",
        # new flow
        "monto_real",
        "categoria",
        "nota_usuario",
    ]

    updates = 0
    def to_int_bool(v: Any):
        if pd.isna(v) or v is None:
            return None
        if isinstance(v, (bool, np.bool_)):
            return int(bool(v))
        try:
            return int(v)
        except Exception:
            return None

    def to_float(v: Any):
        if pd.isna(v) or v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    for _, r in df_edits.iterrows():
        where_clause = ""
        params = []
        if pd.notna(r.get("id", None)):
            where_clause = "id = ?"
            params.append(int(r["id"]))
        elif pd.notna(r.get("unique_key", None)):
            where_clause = "unique_key = ?"
            params.append(str(r["unique_key"]))
        else:
            continue

        sets = []
        set_vals = []
        for c in editable_cols:
            if c in r.index:
                sets.append(f"{c} = ?")
                val = r[c]
                # Asegurar escalar
                if isinstance(val, pd.Series):
                    val = val.iloc[0] if not val.empty else None
                if isinstance(val, (np.generic,)):
                    val = val.item()
                if c in {"es_gasto", "es_transferencia_o_abono", "es_compartido_posible"}:
                    set_vals.append(to_int_bool(val))
                elif c in {"fraccion_mia_sugerida", "monto_mio_estimado", "monto_real"}:
                    set_vals.append(to_float(val))
                else:
                    try:
                        na = pd.isna(val)
                        if isinstance(na, (pd.Series, np.ndarray, list)):
                            na = False
                    except Exception:
                        na = False
                    set_vals.append(None if na else (None if val is None else str(val)))
        if not sets:
            continue

        sql = f"UPDATE movimientos SET {', '.join(sets)} WHERE {where_clause}"
        conn.execute(sql, (*set_vals, *params))
        updates += 1

    conn.commit()
    return updates


def delete_transactions(conn: sqlite3.Connection, *, unique_keys: Optional[List[str]] = None, ids: Optional[List[int]] = None) -> int:
    deleted = 0
    # Construir lista de keys para ignorar en futuras ingestas
    keys_to_ignore: List[str] = []
    if ids:
        qmarks = ",".join(["?"] * len(ids))
        rows = conn.execute(f"SELECT unique_key FROM movimientos WHERE id IN ({qmarks})", list(ids)).fetchall()
        keys_to_ignore += [r[0] for r in rows if r and r[0]]
        # También marca id:* por si suben un CSV futuro que no tenga la misma unique_key
        keys_to_ignore += [f"id:{int(i)}" for i in ids]
    if unique_keys:
        keys_to_ignore += list(unique_keys)

    if keys_to_ignore:
        conn.executemany(
            "INSERT OR IGNORE INTO movimientos_ignorados(unique_key) VALUES (?)",
            [(k,) for k in keys_to_ignore if k],
        )

    if unique_keys:
        qmarks = ",".join(["?"] * len(unique_keys))
        cur = conn.execute(f"DELETE FROM movimientos WHERE unique_key IN ({qmarks})", list(unique_keys))
        deleted += cur.rowcount or 0
    if ids:
        qmarks = ",".join(["?"] * len(ids))
        cur = conn.execute(f"DELETE FROM movimientos WHERE id IN ({qmarks})", list(ids))
        deleted += cur.rowcount or 0
    conn.commit()
    return deleted
