import os
import sqlite3
from typing import Tuple, Any, List, Optional, Dict

import pandas as pd
import numpy as np
try:
    from sqlalchemy import create_engine, text
except Exception:  # sqlalchemy is optional locally
    create_engine = None  # type: ignore
    text = None  # type: ignore


DB_PATH_DEFAULT = os.path.join("data", "gastos.db")


def _pg_url() -> Optional[str]:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return None
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _is_pg_enabled() -> bool:
    return _pg_url() is not None and create_engine is not None


def get_conn(db_path: str = DB_PATH_DEFAULT):
    url = _pg_url()
    if url and create_engine is not None:
        engine = create_engine(url, pool_pre_ping=True)
        return {"engine": engine, "pg": True}
    # Fallback: SQLite local
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(conn) -> None:
    # Postgres path
    if isinstance(conn, dict) and conn.get("pg") and text is not None:
        engine = conn["engine"]
        with engine.begin() as e:
            e.execute(text(
                """
                CREATE TABLE IF NOT EXISTS movimientos (
                    id INTEGER,
                    fecha TIMESTAMP,
                    detalle TEXT,
                    monto DOUBLE PRECISION,
                    es_gasto BOOLEAN,
                    es_transferencia_o_abono BOOLEAN,
                    es_compartido_posible BOOLEAN,
                    fraccion_mia_sugerida DOUBLE PRECISION,
                    monto_mio_estimado DOUBLE PRECISION,
                    categoria_sugerida TEXT,
                    detalle_norm TEXT,
                    monto_real DOUBLE PRECISION,
                    categoria TEXT,
                    nota_usuario TEXT,
                    unique_key TEXT UNIQUE
                );
                """
            ))
            # tablas auxiliares
            e.execute(text("CREATE TABLE IF NOT EXISTS categorias (nombre TEXT UNIQUE);"))
            e.execute(text("CREATE TABLE IF NOT EXISTS categoria_map (detalle_norm TEXT PRIMARY KEY, categoria TEXT);"))
            e.execute(text(
                """
                CREATE TABLE IF NOT EXISTS movimientos_ignorados (
                    id SERIAL PRIMARY KEY,
                    unique_key TEXT UNIQUE,
                    payload TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            ))
        return

    # SQLite path
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

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS movimientos_ignorados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_key TEXT UNIQUE,
            payload TEXT,
            created_at TEXT DEFAULT (DATETIME('now'))
        );
        """
    )
    conn.commit()

    conn.execute("CREATE TABLE IF NOT EXISTS categorias (nombre TEXT UNIQUE);")
    conn.execute("CREATE TABLE IF NOT EXISTS categoria_map (detalle_norm TEXT PRIMARY KEY, categoria TEXT);")
    conn.commit()

def get_categories(conn) -> List[str]:
    if isinstance(conn, dict) and conn.get("pg") and text is not None:
        engine = conn["engine"]
        with engine.begin() as e:
            rows = e.execute(text("SELECT nombre FROM categorias ORDER BY nombre")).fetchall()
        return [r[0] for r in rows]
    cur = conn.execute("SELECT nombre FROM categorias ORDER BY nombre")
    return [r[0] for r in cur.fetchall()]


def replace_categories(conn, cats: List[str]) -> None:
    # Replace entire list atomically
    cats = [c.strip() for c in cats if c and isinstance(c, str)]
    if isinstance(conn, dict) and conn.get("pg") and text is not None:
        engine = conn["engine"]
        with engine.begin() as e:
            e.execute(text("DELETE FROM categorias"))
            if cats:
                e.execute(text("INSERT INTO categorias(nombre) VALUES (:n) ON CONFLICT DO NOTHING"), [{"n": c} for c in cats])
        return
    with conn:
        conn.execute("DELETE FROM categorias")
        if cats:
            conn.executemany("INSERT OR IGNORE INTO categorias(nombre) VALUES (?)", [(c,) for c in cats])


def update_categoria_map_from_df(conn, df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    sub = df[["detalle_norm", "categoria"]].dropna()
    if sub.empty:
        return 0
    sub = sub[(sub["categoria"].notna()) & (sub["categoria"].str.strip() != "")]
    if sub.empty:
        return 0
    rows_df = sub.drop_duplicates("detalle_norm")
    if isinstance(conn, dict) and conn.get("pg") and text is not None:
        engine = conn["engine"]
        with engine.begin() as e:
            res = e.execute(
                text(
                    "INSERT INTO categoria_map(detalle_norm, categoria) VALUES(:detalle_norm, :categoria) "
                    "ON CONFLICT(detalle_norm) DO UPDATE SET categoria=EXCLUDED.categoria"
                ),
                rows_df.to_dict(orient="records"),
            )
            return res.rowcount or 0
    cur = conn.executemany(
        "INSERT INTO categoria_map(detalle_norm, categoria) VALUES(?, ?) ON CONFLICT(detalle_norm) DO UPDATE SET categoria=excluded.categoria",
        rows_df.values.tolist(),
    )
    conn.commit()
    return cur.rowcount or 0


def map_categories_for_df(conn, df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "detalle_norm" not in df.columns:
        return df
    if isinstance(conn, dict) and conn.get("pg"):
        engine = conn["engine"]
        mp = pd.read_sql_query("SELECT detalle_norm, categoria FROM categoria_map", engine)
    else:
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


def rename_category(conn, old_name: str, new_name: str) -> None:
    if not old_name or not new_name or old_name == new_name:
        return
    if old_name == "Sin categoría":
        return  # no renombrar base
    
    if isinstance(conn, dict) and conn.get("pg") and text is not None:
        engine = conn["engine"]
        with engine.begin() as e:
            e.execute(text("UPDATE categorias SET nombre=:new WHERE nombre=:old"), {"new": new_name, "old": old_name})
            e.execute(text("INSERT INTO categorias(nombre) VALUES (:n) ON CONFLICT DO NOTHING"), {"n": new_name})
            e.execute(text("DELETE FROM categorias WHERE nombre=:old"), {"old": old_name})
            e.execute(text("UPDATE movimientos SET categoria=:new WHERE categoria=:old"), {"new": new_name, "old": old_name})
            e.execute(text("UPDATE categoria_map SET categoria=:new WHERE categoria=:old"), {"new": new_name, "old": old_name})
        return
    
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


def upsert_transactions(conn, df: pd.DataFrame) -> Tuple[int, int]:
    df = df.copy()
    if "unique_key" not in df.columns:
        df["unique_key"] = df.apply(_compute_unique_key_row, axis=1)

    # Excluir ignorados por historial (p. ej., eliminados previamente)
    try:
        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            ignored = pd.read_sql_query("SELECT unique_key FROM movimientos_ignorados", engine)["unique_key"].tolist()
        else:
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

    def to_bool(v: Any):
        if pd.isna(v) or v is None:
            return None
        if isinstance(v, (bool, np.bool_)):
            return bool(v)
        # aceptar 0/1, "0"/"1"
        try:
            return bool(int(v))
        except Exception:
            s = str(v).strip().lower()
            return s in {"1", "true", "t", "yes", "y", "si", "sí", "s", "verdadero"}

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
        # Si existe columna 'tipo', úsala para decidir si es gasto
        t = row.get("tipo")
        if t is not None and not pd.isna(t):
            tstr = str(t).strip().lower()
            if tstr in ("gasto", "expense", "gastos"):
                return abs(m)
            else:
                return 0.0
        # Fallback por signo
        return abs(m) if m < 0 else 0.0

    rows_dicts: List[Dict[str, Any]] = []
    for _, r in df[cols].iterrows():
        rows_dicts.append({
            "id": None if pd.isna(r["id"]) else int(r["id"]),
            "fecha": to_date_str(r["fecha"]),
            "detalle": None if pd.isna(r["detalle"]) else str(r["detalle"]),
            "monto": to_float(r["monto"]),
            "es_gasto": to_bool(r["es_gasto"]),
            "es_transferencia_o_abono": to_bool(r["es_transferencia_o_abono"]),
            "es_compartido_posible": to_bool(r["es_compartido_posible"]),
            "fraccion_mia_sugerida": to_float(r["fraccion_mia_sugerida"]),
            "monto_mio_estimado": to_float(r["monto_mio_estimado"]),
            "categoria_sugerida": None if pd.isna(r["categoria_sugerida"]) else str(r["categoria_sugerida"]),
            "detalle_norm": None if pd.isna(r["detalle_norm"]) else str(r["detalle_norm"]),
            "monto_real": to_float(default_monto_real(r)),
            "categoria": None if pd.isna(r.get("categoria", None)) else str(r.get("categoria")),
            "nota_usuario": None if pd.isna(r.get("nota_usuario", None)) else str(r.get("nota_usuario")),
            "unique_key": str(r["unique_key"]),
        })

    # Postgres path
    if isinstance(conn, dict) and conn.get("pg") and text is not None:
        import json
        engine = conn["engine"]
        inserted = 0
        ignored = 0
        with engine.begin() as e:
            for r in rows_dicts:
                # single-row insert; if conflicts, rowcount will be 0
                res = e.execute(text(
                    """
                    INSERT INTO movimientos (id, fecha, detalle, monto, es_gasto, es_transferencia_o_abono,
                                              es_compartido_posible, fraccion_mia_sugerida, monto_mio_estimado, categoria_sugerida,
                                              detalle_norm, monto_real, categoria, nota_usuario, unique_key)
                    VALUES (:id, :fecha, :detalle, :monto, :es_gasto, :es_transferencia_o_abono,
                            :es_compartido_posible, :fraccion_mia_sugerida, :monto_mio_estimado, :categoria_sugerida,
                            :detalle_norm, :monto_real, :categoria, :nota_usuario, :unique_key)
                    ON CONFLICT (unique_key) DO NOTHING
                    """
                ), r)
                if (res.rowcount or 0) > 0:
                    inserted += 1
                    # si existían filas con monto nulo, sincronizar monto
                    if r.get("monto") is not None:
                        e.execute(text(
                            "UPDATE movimientos SET monto = :m WHERE unique_key = :uk AND (monto IS NULL OR monto = 0)"
                        ), {"uk": r["unique_key"], "m": r["monto"]})
                else:
                    # duplicado: registrar en movimientos_ignorados con payload JSON
                    payload = json.dumps(r, default=str)
                    e.execute(text(
                        "INSERT INTO movimientos_ignorados (unique_key, payload) VALUES (:uk, :payload) ON CONFLICT (unique_key) DO NOTHING"
                    ), {"uk": r["unique_key"], "payload": payload})
                    ignored += 1
        return inserted, ignored

    # SQLite path
    import json
    sql = (
        "INSERT OR IGNORE INTO movimientos (id, fecha, detalle, monto, es_gasto, es_transferencia_o_abono, "
        "es_compartido_posible, fraccion_mia_sugerida, monto_mio_estimado, categoria_sugerida, detalle_norm, "
        "monto_real, categoria, nota_usuario, unique_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    inserted = 0
    ignored = 0
    for r in rows_dicts:
        try:
            conn.execute(sql, (
                r["id"], r["fecha"], r["detalle"], r["monto"], r["es_gasto"], r["es_transferencia_o_abono"], r["es_compartido_posible"],
                r["fraccion_mia_sugerida"], r["monto_mio_estimado"], r["categoria_sugerida"], r["detalle_norm"], r["monto_real"], r["categoria"], r["nota_usuario"], r["unique_key"]
            ))
            inserted += 1
            # Sincronizar monto si estaba nulo/0
            if r.get("monto") is not None:
                conn.execute(
                    "UPDATE movimientos SET monto = ? WHERE unique_key = ? AND (monto IS NULL OR monto = 0)",
                    (r["monto"], r["unique_key"]),
                )
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                payload = json.dumps(r, default=str)
                conn.execute(
                    "INSERT OR IGNORE INTO movimientos_ignorados (unique_key, payload) VALUES (?, ?)",
                    (r["unique_key"], payload),
                )
                ignored += 1
            else:
                raise
    conn.commit()
    return inserted, ignored


def load_all(conn) -> pd.DataFrame:
    if isinstance(conn, dict) and conn.get("pg"):
        engine = conn["engine"]
        df = pd.read_sql_query("SELECT * FROM movimientos", engine)
    else:
        df = pd.read_sql_query("SELECT * FROM movimientos", conn)
    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        for c in ["es_gasto", "es_transferencia_o_abono", "es_compartido_posible"]:
            if c in df.columns:
                try:
                    df[c] = df[c].apply(lambda x: bool(int(x)) if pd.notna(x) else False)
                except Exception:
                    df[c] = df[c].astype(bool)
    return df


def apply_edits(conn, df_edits: pd.DataFrame) -> int:
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
    
    def to_bool(v: Any):
        if pd.isna(v) or v is None:
            return None
        if isinstance(v, (bool, np.bool_)):
            return bool(v)
        # aceptar 0/1, "0"/"1"
        try:
            return bool(int(v))
        except Exception:
            s = str(v).strip().lower()
            return s in {"1", "true", "t", "yes", "y", "si", "sí", "s", "verdadero"}

    def to_float(v: Any):
        if pd.isna(v) or v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    # Postgres path
    if isinstance(conn, dict) and conn.get("pg") and text is not None:
        engine = conn["engine"]
        for _, r in df_edits.iterrows():
            where_clause = ""
            params = {}
            
            if pd.notna(r.get("id", None)):
                where_clause = "id = :id"
                params["id"] = int(r["id"])
            elif pd.notna(r.get("unique_key", None)):
                where_clause = "unique_key = :uk"
                params["uk"] = str(r["unique_key"])
            else:
                continue

            sets = []
            set_vals = {}
            for c in editable_cols:
                if c in r.index:
                    sets.append(f"{c} = :{c}")
                    val = r[c]
                    # Asegurar escalar
                    if isinstance(val, pd.Series):
                        val = val.iloc[0] if not val.empty else None
                    if isinstance(val, (np.generic,)):
                        val = val.item()
                    if c in {"es_gasto", "es_transferencia_o_abono", "es_compartido_posible"}:
                        set_vals[c] = to_bool(val)
                    elif c in {"fraccion_mia_sugerida", "monto_mio_estimado", "monto_real"}:
                        set_vals[c] = to_float(val)
                    else:
                        try:
                            na = pd.isna(val)
                            if isinstance(na, (pd.Series, np.ndarray, list)):
                                na = False
                        except Exception:
                            na = False
                        set_vals[c] = None if na else (None if val is None else str(val))
            
            if not sets:
                continue

            sql = f"UPDATE movimientos SET {', '.join(sets)} WHERE {where_clause}"
            set_vals.update(params)
            engine.execute(text(sql), set_vals)
            updates += 1
        
        return updates

    # SQLite path
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
                    set_vals.append(to_bool(val))
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


def delete_transactions(conn, *, unique_keys: Optional[List[str]] = None, ids: Optional[List[int]] = None) -> int:
    deleted = 0
    # Construir lista de keys para ignorar en futuras ingestas
    keys_to_ignore: List[str] = []
    
    if isinstance(conn, dict) and conn.get("pg") and text is not None:
        engine = conn["engine"]
        
        if ids:
            with engine.begin() as e:
                rows = e.execute(text("SELECT unique_key FROM movimientos WHERE id = ANY(:ids)"), {"ids": ids}).fetchall()
                keys_to_ignore += [r[0] for r in rows if r and r[0]]
                # También marca id:* por si suben un CSV futuro que no tenga la misma unique_key
                keys_to_ignore += [f"id:{int(i)}" for i in ids]
        
        if unique_keys:
            keys_to_ignore += list(unique_keys)

        if keys_to_ignore:
            with engine.begin() as e:
                e.executemany(
                    text("INSERT INTO movimientos_ignorados(unique_key) VALUES (:uk) ON CONFLICT DO NOTHING"),
                    [{"uk": k} for k in keys_to_ignore if k],
                )

        if unique_keys:
            with engine.begin() as e:
                result = e.execute(text("DELETE FROM movimientos WHERE unique_key = ANY(:keys)"), {"keys": unique_keys})
                deleted += result.rowcount or 0
        
        if ids:
            with engine.begin() as e:
                result = e.execute(text("DELETE FROM movimientos WHERE id = ANY(:ids)"), {"ids": ids})
                deleted += result.rowcount or 0
        
        return deleted

    # SQLite path
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
