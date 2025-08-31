\
import pandas as pd, numpy as np, re, io, chardet, argparse, json
from pathlib import Path
from datetime import datetime

def sniff_encoding(p):
    raw = Path(p).read_bytes()
    return chardet.detect(raw)['encoding'] or 'utf-8'

def sniff_delimiter(sample_text):
    cands = [';', ',', '\t', '|']
    counts = {d:0 for d in cands}
    for ln in sample_text.splitlines()[:40]:
        for d in cands:
            counts[d] += ln.count(d)
    return max(counts, key=counts.get)

def norm_text(s):
    if pd.isna(s): return ""
    import unicodedata
    s2 = unicodedata.normalize('NFD', str(s))
    s2 = ''.join(ch for ch in s2 if unicodedata.category(ch) != 'Mn')
    return re.sub(r'\s+', ' ', s2).strip().upper()

def try_parse_date(s):
    if pd.isna(s): return pd.NaT
    s = str(s).strip()
    fmts = ["%d-%m-%Y","%d/%m/%Y","%Y-%m-%d","%d-%m-%y","%d/%m/%y","%m/%d/%Y","%d.%m.%Y"]
    for f in fmts:
        try:
            return pd.to_datetime(s, format=f, dayfirst=True, errors='raise')
        except: pass
    return pd.to_datetime(s, dayfirst=True, errors='coerce')

def parse_amount(val):
    if val is None or (isinstance(val,float) and np.isnan(val)): 
        return np.nan
    s = str(val).strip()
    s = re.sub(r'[^\d,.-]','', s)
    if ',' in s and '.' in s:
        s = s.replace('.','').replace(',', '.')
    else:
        if s.count(',') > 1:
            s = s.replace(',','')
        else:
            s = s.replace(',','.')
        s = s.replace(' ','')
    try: return float(s)
    except: return np.nan

def detect_header_and_read(raw_text):
    delim = sniff_delimiter(raw_text)
    lines = raw_text.splitlines()
    header_keywords = ['fecha','detalle','glosa','comercio','descripcion','monto','cargo','abono','debe','haber','saldo','movim']
    header_row_idx = None
    for i, ln in enumerate(lines[:200]):
        parts = [p.strip() for p in ln.split(delim)]
        norm_parts = [re.sub(r'[^A-Za-zÁÉÍÓÚÑáéíóúñ0-9 ]','', p).strip().lower() for p in parts]
        hits = sum(any(k in np for k in header_keywords) for np in norm_parts)
        if hits >= 2 and len(parts) >= 3:
            header_row_idx = i
            break
    if header_row_idx is not None:
        df = pd.read_csv(io.StringIO("\n".join(lines[header_row_idx:])), delimiter=delim, dtype=str)
    else:
        df = pd.read_csv(io.StringIO(raw_text), delimiter=delim, dtype=str)
    return df

def standardize(df):
    df = df.loc[:, ~df.columns.str.contains(r'^Unnamed', na=False)]
    # candidate cols
    cand_date = [c for c in df.columns if re.search(r'fech', c, flags=re.I)]
    cand_desc = [c for c in df.columns if re.search(r'(detalle|glosa|descri|concepto|comercio|nombre|movim)', c, flags=re.I)]
    credit_like = [c for c in df.columns if re.search(r'(abono|haber|credito)', c, flags=re.I)]
    debit_like  = [c for c in df.columns if re.search(r'(cargo|debe|debito)', c, flags=re.I)]
    cand_amount = [c for c in df.columns if re.search(r'(monto|importe|saldo)', c, flags=re.I)]

    if not cand_date:
        for c in df.columns:
            if df[c].astype(str).str.contains(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}').any():
                cand_date.append(c); break
    if not cand_desc:
        lens = {c: df[c].astype(str).str.len().mean() for c in df.columns}
        cand_desc = [max(lens, key=lens.get)] if lens else []

    date_col = cand_date[0] if cand_date else None
    desc_col = cand_desc[0] if cand_desc else None

    std = pd.DataFrame()
    std['fecha'] = df[date_col].apply(try_parse_date) if date_col else pd.NaT
    std['detalle'] = df[desc_col].astype(str) if desc_col else ""
    std['detalle_norm'] = std['detalle'].apply(norm_text)

    if debit_like or credit_like:
        dvals = pd.to_numeric(df[debit_like[0]].apply(parse_amount), errors='coerce') if debit_like else 0.0
        cvals = pd.to_numeric(df[credit_like[0]].apply(parse_amount), errors='coerce') if credit_like else 0.0
        signed = cvals.fillna(0) - dvals.fillna(0)  # inflow - outflow
    else:
        amt_col = cand_amount[0] if cand_amount else None
        raw_amt = pd.to_numeric(df[amt_col].apply(parse_amount), errors='coerce') if amt_col else np.nan
        if amt_col and re.search(r'(cargo|debe|debito)', amt_col, flags=re.I):
            signed = -raw_amt
        else:
            signed = raw_amt

    # Standard: gasto = negativo (sale plata), abono = positivo (entra)
    std['monto'] = signed

    # Flags heurísticos
    TRANSFER_PATTERNS = [r"\bTRASPAS", r"\bTRANSFER", r"\bABONO\b", r"\bREEMB", r"\bREVERSA", r"\bCASHBACK", r"\bPAGO T", r"\bPAGO TARJ"]
    SHARED_PATTERNS = [r"\bDIVIDID", r"\bCOMPARTID", r"\bAMIGOS\b"]

    def has(patterns, text):
        t = norm_text(text)
        return any(re.search(p, t) for p in patterns)

    std['es_transferencia_o_abono'] = std['detalle'].apply(lambda s: has(TRANSFER_PATTERNS, s))
    std['es_compartido_posible'] = std['detalle'].apply(lambda s: has(SHARED_PATTERNS, s))

    std['categoria'] = None
    std['fraccion_mia'] = np.where(std['es_compartido_posible'], 0.5, 1.0)
    std['monto_mio'] = np.where(std['monto'] < 0, std['monto'] * std['fraccion_mia'], 0.0)

    # id_hash (único estable)
    def make_id(row):
        base = f"{row.get('fecha'):%Y-%m-%d}|{row.get('detalle_norm')}|{row.get('monto'):.2f}"
        import hashlib
        return hashlib.sha1(base.encode('utf-8','ignore')).hexdigest()[:16]

    std['id'] = std.apply(make_id, axis=1)
    cols = ['id','fecha','detalle','monto','es_transferencia_o_abono','es_compartido_posible','categoria','fraccion_mia','monto_mio','detalle_norm']
    std = std[cols]
    if std['fecha'].notna().any():
        std = std.sort_values('fecha', ascending=False).reset_index(drop=True)
    return std

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Ruta del CSV crudo del banco")
    ap.add_argument("--out", dest="outp", default="data/standardized.csv", help="Ruta de salida estandarizada")
    args = ap.parse_args()

    enc = sniff_encoding(args.inp)
    raw_text = Path(args.inp).read_text(encoding=enc, errors='replace')
    df = detect_header_and_read(raw_text)
    std = standardize(df)
    Path(args.outp).parent.mkdir(parents=True, exist_ok=True)
    std.to_csv(args.outp, index=False, encoding='utf-8')
    print(f"OK: {args.outp} ({len(std)} filas)")

if __name__ == "__main__":
    main()
