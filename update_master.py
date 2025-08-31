\
import pandas as pd, numpy as np, argparse, json, re
from pathlib import Path
from datetime import timedelta

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

def norm_text(s):
    if pd.isna(s): return ""
    import unicodedata
    s2 = unicodedata.normalize('NFD', str(s))
    s2 = ''.join(ch for ch in s2 if unicodedata.category(ch) != 'Mn')
    return re.sub(r'\s+', ' ', s2).strip().upper()

def load_json(path, default):
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding='utf-8')
    return default

def apply_merchant_map(df, merchant_map):
    df = df.copy()
    cats = []
    for t in df['detalle_norm']:
        cat = None
        for key, val in merchant_map.items():
            if key in t:
                cat = val; break
        cats.append(cat)
    df['categoria'] = df['categoria'].fillna(pd.Series(cats, index=df.index))
    return df

def mark_own_transfers(df, account_aliases):
    pats = [re.escape(a.upper()) for a in account_aliases]
    rx = re.compile("|".join(pats)) if pats else None
    if rx is None:
        df['es_entre_cuentas'] = False
    else:
        df['es_entre_cuentas'] = df['detalle_norm'].str.contains(rx)
    return df

def match_reimbursements(df, window_days=21, tol=1000):
    # Busca abonos (+) que compensen gastos (-) previos de similar monto.
    df = df.sort_values('fecha')
    df['match_id'] = None
    # index para búsqueda rápida por monto aproximado
    gastos = df[df['monto'] < 0][['id','fecha','monto','detalle_norm']].copy()
    abonos = df[df['monto'] > 0][['id','fecha','monto','detalle_norm']].copy()

    for idx, row in abonos.iterrows():
        monto = row['monto']
        fmin = row['fecha'] - timedelta(days=window_days)
        candidates = gastos[(gastos['fecha'] >= fmin) & (gastos['fecha'] <= row['fecha'])]
        # diferencia de montos inversos dentro de tolerancia
        diff = (candidates['monto'].abs() - abs(monto)).abs()
        near = candidates[diff <= tol].copy()
        if len(near):
            # pick the closest by amount, then most recent
            near['absdiff'] = diff.loc[near.index]
            best = near.sort_values(['absdiff','fecha'], ascending=[True, False]).head(1)
            g_id = best['id'].iloc[0]
            df.loc[idx, 'match_id'] = g_id
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="CSV estandarizado (salida de prep.py)")
    ap.add_argument("--master", dest="master", default="data/master.csv", help="Ruta del master.csv")
    ap.add_argument("--merchant-map", dest="mmap", default="data/merchant_map.json")
    ap.add_argument("--config", dest="config", default="data/config.json")
    args = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)

    # Load inputs
    df_new = pd.read_csv(args.inp, parse_dates=['fecha'])
    if Path(args.master).exists():
        df_master = pd.read_csv(args.master, parse_dates=['fecha'])
    else:
        df_master = pd.DataFrame(columns=df_new.columns)

    merchant_map = load_json(args.mmap, {})
    config = load_json(args.config, {
        "account_aliases": [],
        "reimbursement_window_days": 21,
        "reimbursement_amount_tolerance": 1000
    })

    # Dedup by 'id'
    ids_master = set(df_master['id'].astype(str)) if len(df_master) else set()
    df_new = df_new[~df_new['id'].astype(str).isin(ids_master)].copy()

    # Apply merchant map
    df_new = apply_merchant_map(df_new, merchant_map)

    # Mark own account transfers
    df_new = mark_own_transfers(df_new, [a.upper() for a in config.get("account_aliases", [])])

    # Combine
    df_all = pd.concat([df_master, df_new], ignore_index=True)
    df_all = df_all.drop_duplicates(subset=['id'])

    # Reimbursement matching on full set
    df_all = match_reimbursements(df_all,
        window_days=int(config.get("reimbursement_window_days", 21)),
        tol=float(config.get("reimbursement_amount_tolerance", 1000)))

    # Compute monto_mio (again) based on categoria/fraccion and excluding own transfers
    if 'fraccion_mia' not in df_all.columns:
        df_all['fraccion_mia'] = np.where(df_all.get('es_compartido_posible', False), 0.5, 1.0)
    df_all['es_gasto'] = (df_all['monto'] < 0) & (~df_all.get('es_transferencia_o_abono', False))
    df_all['monto_mio'] = np.where(df_all['es_gasto'], df_all['monto'] * df_all['fraccion_mia'], 0.0)
    df_all.loc[df_all.get('es_entre_cuentas', False)==True, 'monto_mio'] = 0.0

    # Persist
    df_all.to_csv(args.master, index=False, encoding='utf-8')
    print(f"Master actualizado: {args.master} ({len(df_all)} filas)")

    # Learn merchant_map from rows with categoria manual
    learned = {}
    for _, r in df_all.iterrows():
        cat = r.get('categoria')
        det = str(r.get('detalle_norm') or "")
        if isinstance(cat, str) and len(cat.strip())>0 and len(det)>3:
            # learn by exact merchant token prefix (first token or before '*')
            key = det.split('*')[0].strip()
            if len(key)>=3:
                learned[key] = cat.strip()
    # merge and save
    merchant_map.update(learned)
    Path(args.mmap).write_text(json.dumps(merchant_map, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"merchant_map.json actualizado con {len(learned)} nuevas reglas (si correspondía).")

if __name__ == "__main__":
    main()
