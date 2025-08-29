import os
import re
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

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
)

st.set_page_config(page_title="Dashboard de Facto$", layout="wide")

# Inyección mínima de estilos para aplicar color primario en el sidebar al instante
st.markdown(
    """
    <style>
    :root { --facto-primary:#133c60; }
    section[data-testid="stSidebar"] > div { background-color: #f0f5fa; }
    [data-testid="stSidebar"] .stButton > button {
        background-color: var(--facto-primary); color: white; border-color: var(--facto-primary);
    }
    [data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] { background-color: var(--facto-primary); }
    [data-testid="stSidebar"] .stSelectbox > div > div { border-color: var(--facto-primary); }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Dashboard de Facto$")

REQUIRED_COLS = {"id", "fecha", "detalle", "monto", "detalle_norm"}

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


@st.cache_data(show_spinner=False)
def load_df(file):
    df = pd.read_csv(file)
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        st.error(f"Faltan columnas requeridas: {sorted(missing)}")
        st.stop()
    # Tipos
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    # Cast numéricos (solo si existen)
    for c in ["monto", "fraccion_mia_sugerida", "monto_mio_estimado", "monto_real"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# Inicializar DB
conn = get_conn()
init_db(conn)

# Cargar/sembrar categorías
categories = get_categories(conn)
if not categories:
    replace_categories(conn, DEFAULT_CATEGORIES)
    categories = DEFAULT_CATEGORIES[:]

uploaded = st.file_uploader(
    "Sube tu CSV estandarizado (movimientos_estandarizados_*.csv)", type=["csv"]
)

if uploaded is not None:
    df_in = load_df(uploaded)
    # Autocompletar categoría desde el mapa aprendido
    df_in = map_categories_for_df(conn, df_in)
    inserted, ignored = upsert_transactions(conn, df_in)
    st.success(f"Ingeridos: {inserted} nuevas filas, ignoradas por duplicado: {ignored}")

# Cargar histórico desde DB
df = load_all(conn)

if df.empty:
    st.info(
        "Sube un CSV estandarizado para comenzar. Primero procesa tu archivo original con el notebook de preparación."
    )
    st.stop()

# Filtros en sidebar
with st.sidebar:
    st.header("Filtros")
    q = st.text_input("Buscar en detalle", "")
    # Filtro por mes (por nombre, p.ej., "agosto")
    months_es = [
        "enero","febrero","marzo","abril","mayo","junio",
        "julio","agosto","septiembre","octubre","noviembre","diciembre"
    ]
    months_present = sorted(pd.unique(df["fecha"].dropna().dt.month))
    month_labels = [months_es[m-1] for m in months_present]
    sel_mes_label = st.selectbox("Mes", options=["Todos"] + month_labels, index=0)
    min_fecha, max_fecha = df["fecha"].min(), df["fecha"].max()
    if pd.isna(min_fecha) or pd.isna(max_fecha):
        rango = None
    else:
        rango = st.date_input(
            "Rango de fechas",
            (min_fecha.date(), max_fecha.date()),
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


dfv = df.copy()
if q:
    dfv = dfv[dfv["detalle_norm"].str.contains(q, case=False, na=False)]
if sel_mes_label and sel_mes_label != "Todos":
    # Filtrar por el mes seleccionado (independiente del año)
    sel_idx = month_labels.index(sel_mes_label)
    sel_month_num = months_present[sel_idx]
    dfv = dfv[dfv["fecha"].dt.month == sel_month_num]
elif isinstance(rango, tuple) and len(rango) == 2:
    dfv = dfv[(dfv["fecha"] >= pd.to_datetime(rango[0])) & (dfv["fecha"] <= pd.to_datetime(rango[1]))]
elif rango:
    dfv = dfv[dfv["fecha"].dt.date == rango]

# tipo por signo y monto sin signo para mostrar
dfv["tipo"] = np.where(dfv["monto"] < 0, "Gasto", np.where(dfv["monto"] > 0, "Abono", "Cero"))
dfv["monto_cartola"] = dfv["monto"].abs()

# Solo gastos en la vista principal
dfv = dfv[dfv["tipo"] == "Gasto"].copy()

# Filtro por categoría (sidebar)
cat_options = sorted([c for c in categories if c])
sel_cats = st.sidebar.multiselect("Categorías", options=["Todas"] + cat_options, default=["Todas"], key="sidebar_cats")
if sel_cats and "Todas" not in sel_cats:
    dfv = dfv[dfv["categoria"].isin(sel_cats)]

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

# Paleta de colores por categoría
palette = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc949", "#af7aa1", "#ff9da7", "#9c755f", "#bab0ab",
]
domain = cat_options
range_colors = (palette * ((len(domain) // len(palette)) + 1))[: len(domain)]

st.markdown("### Insights principales")
col1, col2 = st.columns([1,1])
with col1:
    amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
    total_real = float(df_plot[amt_col].abs().fillna(0).sum())
    st.metric("Gasto real (visible)", f"${total_real:,.0f}")
with col2:
    if not df_plot.empty:
        amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
        cat_agg_metric = df_plot.assign(_amt=np.abs(df_plot[amt_col].astype(float))).groupby("categoria")["_amt"].sum().sort_values(ascending=False)
        if len(cat_agg_metric) > 0:
            st.metric("Categoría más relevante", f"{cat_agg_metric.index[0]}")

# Revisar sugerencias de categorías
def build_suggestions(conn, base_df: pd.DataFrame) -> pd.DataFrame:
    if base_df.empty:
        return pd.DataFrame()
    missing = base_df[(base_df["categoria"].isna()) | (base_df["categoria"].str.strip() == "") | (base_df["categoria"] == "Sin categoría")].copy()
    if missing.empty:
        return pd.DataFrame()

    # 1) Exacto por categoria_map
    try:
        mp = pd.read_sql_query("SELECT detalle_norm, categoria AS cat_map FROM categoria_map", conn)
    except Exception:
        mp = pd.DataFrame(columns=["detalle_norm", "cat_map"])
    sug = missing.merge(mp, on="detalle_norm", how="left")
    sug["sugerida"] = sug["cat_map"]
    sug["fuente"] = np.where(sug["cat_map"].notna(), "map", None)
    sug["confianza"] = np.where(sug["cat_map"].notna(), 1.0, np.nan)

    # 2) Historial dominante
    try:
        hist = pd.read_sql_query(
            """
            SELECT detalle_norm, categoria, COUNT(*) as cnt
            FROM movimientos
            WHERE categoria IS NOT NULL AND TRIM(categoria) <> ''
            GROUP BY detalle_norm, categoria
            """,
            conn,
        )
        if not hist.empty:
            top = hist.sort_values(["detalle_norm", "cnt"], ascending=[True, False]).groupby("detalle_norm").head(1)
            total = hist.groupby("detalle_norm")["cnt"].sum().rename("total")
            top = top.merge(total, on="detalle_norm", how="left")
            top["ratio"] = top["cnt"] / top["total"].replace(0, np.nan)
            top = top[top["ratio"] >= 0.7]
            top = top.rename(columns={"categoria": "cat_hist"})[["detalle_norm", "cat_hist", "ratio"]]
            sug = sug.merge(top, on="detalle_norm", how="left")
            fill_hist = sug["sugerida"].isna() & sug["cat_hist"].notna()
            sug.loc[fill_hist, "sugerida"] = sug.loc[fill_hist, "cat_hist"]
            sug.loc[fill_hist, "fuente"] = "hist"
            sug.loc[fill_hist, "confianza"] = 0.8
    except Exception:
        pass

    # 3) Reglas por palabras clave
    patterns = [
        (r"COPEC|ESMAX|SHELL|ENEX|COCH|PETROBRAS", "Transporte"),
        (r"UBER|DIDI|CABIFY|BEAT|INTERNACIONAL LIME|LIME", "Transporte"),
        (r"RAPPI|UBER\s*EATS|PEDIDOS?\s*YA|D\.?L\.?\s*RAPPI|RAPPI PRO|DELIVERY", "Alimentación"),
        (r"JUMBO|LIDER|TOTTUS|UNIMARC|SANTA\s*ISABEL|SUPERMERCADO", "Supermercado"),
        (r"STARBUCKS|CAFE|COFFEE|PANADERIA|PASTELERIA", "Snack"),
        (r"FARMACIA|CRUZ\s*VERDE|SALCOBRAND|AHUMADA", "Salud"),
        (r"NETFLIX|SPOTIFY|YOUTUBE|DISNEY|APPLE\s*ICLOUD|ICLOUD|MICROSOFT|GOOGLE\s*STORAGE|SUBSCRIPCION|SUBSCRIPTION", "Suscripciones"),
        (r"MERCADOPAGO|MERPAGO|MERCADO\s*PAGO|AMAZON|ALIEXPRESS|EBAY", "Compras"),
        (r"METRO|RED\s*METRO|TRANSANTIAGO|TARJETA\s*BIP", "Transporte"),
        (r"ESPECTACULO|CINE|THEATER|ENTRADA|CONCIERTO", "Ocio"),
        (r"HOTEL|BOOKING|AIRBNB|HOSTAL|VUELO|LATAM|SKY|JETSMART", "Viajes"),
        (r"CERVEZ|VIN[OT]|LICOR|BAR|PUB", "Carrete"),
        (r"TABACO|CIGARROS|CIGARRILLOS", "Tabaco"),
    ]
    no_sug_mask = sug["sugerida"].isna()
    if no_sug_mask.any():
        for pat, cat in patterns:
            idx = no_sug_mask & sug["detalle_norm"].str.contains(pat, case=False, regex=True, na=False)
            sug.loc[idx, "sugerida"] = cat
            sug.loc[idx, "fuente"] = "regex"
            sug.loc[idx, "confianza"] = 0.7
            no_sug_mask = sug["sugerida"].isna()
            if not no_sug_mask.any():
                break

    sug["monto_abs"] = sug["monto"].abs()
    sug = sug[sug["sugerida"].notna()].copy()
    # Default aceptar si confianza alta
    sug["aceptar"] = sug["confianza"].fillna(0) >= 0.9
    sug["manual"] = ""
    return sug

sug_df = build_suggestions(conn, dfv)
if not sug_df.empty:
    st.markdown("#### Revisar sugerencias")
    with st.form("sugerencias_form"):
        sug_view_cols = [
            "id", "unique_key", "fecha", "detalle_norm", "monto_abs", "sugerida", "fuente", "confianza", "aceptar", "manual"
        ]
        sug_view = sug_df[sug_view_cols].copy()
        suged = st.data_editor(
            sug_view,
            use_container_width=True,
            hide_index=True,
            column_config={
                "monto_abs": st.column_config.NumberColumn(format="%.0f", disabled=True),
                "sugerida": st.column_config.TextColumn(disabled=True),
                "fuente": st.column_config.TextColumn(disabled=True),
                "confianza": st.column_config.NumberColumn(format="%.2f", disabled=True),
                "aceptar": st.column_config.CheckboxColumn(),
                "manual": st.column_config.SelectboxColumn(options=[""] + categories, default=""),
                "unique_key": st.column_config.TextColumn(disabled=True),
            },
        )
        col_sug1, col_sug2 = st.columns([1,1])
        apply_sug = col_sug1.form_submit_button("Aplicar seleccionadas")
        apply_all_high = col_sug2.form_submit_button("Aceptar todas ≥ 0.9")

    def apply_category_updates(df_updates: pd.DataFrame):
        if df_updates.empty:
            return 0
        updates = df_updates.copy()
        updates = updates[[c for c in ["unique_key", "id", "detalle_norm", "categoria"] if c in updates.columns]]
        return apply_edits(conn, updates)

    if apply_all_high and not sug_df.empty:
        to_apply = sug_df[sug_df["confianza"] >= 0.9].copy()
        to_apply.rename(columns={"sugerida": "categoria"}, inplace=True)
        to_apply = to_apply[[c for c in ["unique_key","id","detalle_norm","categoria"] if c in to_apply.columns]]
        n = apply_category_updates(to_apply)
        try:
            update_categoria_map_from_df(conn, to_apply)
        except Exception:
            pass
        st.success(f"Aplicadas {n} sugerencias de alta confianza")
        st.rerun()

    if apply_sug and isinstance(suged, pd.DataFrame) and not suged.empty:
        suged = suged.copy()
        chosen = pd.DataFrame()
        # Aceptadas explícitamente
        acc = suged[suged["aceptar"] == True].copy()
        if not acc.empty:
            acc.rename(columns={"sugerida": "categoria"}, inplace=True)
            chosen = pd.concat([chosen, acc], ignore_index=True)
        # Manuales no vacíos
        man_vals = suged["manual"].astype(object).where(suged["manual"].notna(), "").astype(str).str.strip()
        man = suged[man_vals.apply(lambda x: x not in ("", "None", "nan", "NaN"))].copy()
        if not man.empty:
            man.rename(columns={"manual": "categoria"}, inplace=True)
            chosen = pd.concat([chosen, man], ignore_index=True)
        if not chosen.empty:
            chosen = chosen[[c for c in ["unique_key","id","detalle_norm","categoria"] if c in chosen.columns]].drop_duplicates("unique_key")
            n = apply_category_updates(chosen)
            try:
                update_categoria_map_from_df(conn, chosen)
            except Exception:
                pass
            st.success(f"Actualizadas {n} filas con categoría")
            st.rerun()

# Donut por categoría
if not df_plot.empty:
    amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
    cat_agg = df_plot.assign(_amt=np.abs(df_plot[amt_col].astype(float))).groupby("categoria", dropna=False)["_amt"].sum().reset_index()
    cat_agg.rename(columns={cat_agg.columns[1]: "total"}, inplace=True)
    chart_donut = alt.Chart(cat_agg).mark_arc(innerRadius=60).encode(
        theta=alt.Theta("total:Q", stack=True),
        color=alt.Color("categoria:N", scale=alt.Scale(domain=domain, range=range_colors), legend=alt.Legend(title="Categoría")),
        tooltip=["categoria:N", alt.Tooltip("total:Q", format=",.0f", title="Total")],
    ).properties(height=320)
    st.altair_chart(chart_donut, use_container_width=True)
    # Filtro rápido accionable (simula click en donut)
    quick = st.multiselect(
        "Filtro rápido por categoría",
        options=domain,
        default=st.session_state.get("cat_filter", []),
        help="Selecciona categorías para filtrar la tabla inferior",
    )
    # Actualizar estado si cambió
    if quick != st.session_state.get("cat_filter", []):
        st.session_state["cat_filter"] = quick
        st.rerun()

cols = st.columns(3)
with cols[0]:
    # Frecuencia por categoría (número de compras)
    if not df_plot.empty:
        freq = df_plot.groupby("categoria").size().reset_index(name="veces").sort_values("veces", ascending=False)
        chart_freq = alt.Chart(freq).mark_bar().encode(
            x=alt.X("categoria:N", sort='-y', title="Categoría"),
            y=alt.Y("veces:Q", title="Veces"),
            color=alt.Color("categoria:N", scale=alt.Scale(domain=domain, range=range_colors), legend=None),
            tooltip=["categoria:N", "veces:Q"],
        ).properties(height=220)
        st.altair_chart(chart_freq, use_container_width=True)
with cols[1]:
    # Ticket promedio por categoría
    if not df_plot.empty:
        avg = df_plot.assign(_amt=df_plot["monto" if "monto" in df_plot.columns else "monto_real_plot"].abs()).groupby("categoria")['_amt'].mean().reset_index().rename(columns={'_amt':'ticket_prom'})
        chart_avg = alt.Chart(avg).mark_bar().encode(
            x=alt.X("categoria:N", sort='-y', title="Categoría"),
            y=alt.Y("ticket_prom:Q", title="Ticket promedio", axis=alt.Axis(format=",.0f")),
            color=alt.Color("categoria:N", scale=alt.Scale(domain=domain, range=range_colors), legend=None),
            tooltip=["categoria:N", alt.Tooltip("ticket_prom:Q", format=",.0f")],
        ).properties(height=220)
        st.altair_chart(chart_avg, use_container_width=True)
with cols[2]:
    # Gastos por día de la semana
    if not df_plot.empty:
        dia_map = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
        df_plot["dow"] = df_plot["fecha"].dt.dayofweek.map(dia_map)
        df_plot["dow_idx"] = df_plot["fecha"].dt.dayofweek
        amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
        dow_agg = df_plot.assign(_amt=np.abs(df_plot[amt_col].astype(float))).groupby(["dow", "dow_idx"])['_amt'].sum().reset_index()
        dow_agg.rename(columns={"_amt": "total"}, inplace=True)
        chart_dow = alt.Chart(dow_agg).mark_line(point=True).encode(
            x=alt.X("dow:N", sort=["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"], title="Día"),
            y=alt.Y("total:Q", title="Gasto", axis=alt.Axis(format=",.0f")),
            color=alt.value("#4e79a7"),
            tooltip=["dow:N", alt.Tooltip("total:Q", format=",.0f")],
        ).properties(height=220)
        st.altair_chart(chart_dow, use_container_width=True)

# Comercios más repetidos: solo donde fuiste más de una vez, barras horizontales ordenadas
if not df_plot.empty:
    amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
    merch = df_plot.assign(_amt=np.abs(df_plot[amt_col].astype(float))).groupby("detalle_norm").agg(
        total=("_amt", "sum"),
        veces=("_amt", "count"),
    ).reset_index()
    merch = merch[merch["veces"] >= 2].sort_values(["veces","total"], ascending=[False, False]).head(20)
    if not merch.empty:
        chart_merch = alt.Chart(merch).mark_bar().encode(
            x=alt.X("veces:Q", title="Veces"),
            y=alt.Y("detalle_norm:N", sort='-x', title="Comercio"),
            color=alt.Color("total:Q", legend=alt.Legend(title="Total"), scale=alt.Scale(scheme="blues")),
            tooltip=["detalle_norm:N", "veces:Q", alt.Tooltip("total:Q", format=",.0f")],
        ).properties(height=300)
        st.altair_chart(chart_merch, use_container_width=True)

# Aplicar filtro rápido de categorías (afecta tabla y análisis posteriores)
quick_now = st.session_state.get("cat_filter", [])
if quick_now:
    dfv = dfv[dfv["categoria"].isin(quick_now)]
    df_plot = df_plot[df_plot["categoria"].isin(quick_now)]


st.markdown("### Tabla editable")

display_cols = [
    "id",
    "fecha",
    "detalle",
    "tipo",
    "monto",  # editable real
    "categoria",
    "nota_usuario",
    "unique_key",  # para poder detectar deletions
]
existing_cols = [c for c in display_cols if c in dfv.columns or c == "monto"]

# Preparar vista editable:
df_view = dfv.copy()
df_view["monto_bruto_abs"] = df_view["monto"].abs()
df_view["monto"] = df_view["monto_real"].where(df_view.get("monto_real").notna() if "monto_real" in df_view.columns else False, df_view["monto_bruto_abs"])
# Asegurar numérico positivo para edición y evitar warnings de formato
df_view["monto"] = pd.to_numeric(df_view["monto"], errors="coerce").abs().fillna(0)
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

with st.form("editor_form", clear_on_submit=False):
    editable = st.data_editor(
        df_table,
        num_rows="dynamic",  # permite borrar filas en la propia tabla
        use_container_width=True,
        key="tabla_gastos",
        column_config={
            "fecha": st.column_config.DatetimeColumn(format="YYYY-MM-DD"),
            "monto": st.column_config.NumberColumn(format="%.0f", min_value=0.0),
            "categoria": st.column_config.SelectboxColumn(options=categories, default="Sin categoría"),
            "nota_usuario": st.column_config.TextColumn(),
            "unique_key": st.column_config.TextColumn(disabled=True),
        },
        hide_index=True,
    )
    col_s, col_d = st.columns(2)
    save_clicked = col_s.form_submit_button("Guardar cambios en la base")
    download_clicked = col_d.form_submit_button("Descargar CSV enriquecido")

if save_clicked:
    # Detectar eliminadas con anti-join por unique_key y por id
    before_df = df_table[[c for c in ["unique_key","id"] if c in df_table.columns]].copy()
    after_df = editable[[c for c in ["unique_key","id"] if c in editable.columns]].copy()
    before_keys = set(before_df.get("unique_key", pd.Series(dtype=str)).dropna().astype(str))
    after_keys = set(after_df.get("unique_key", pd.Series(dtype=str)).dropna().astype(str))
    to_delete_keys = list(before_keys - after_keys)
    before_ids = set(before_df.get("id", pd.Series(dtype=float)).dropna().astype(int).astype(str)) if "id" in before_df.columns else set()
    after_ids = set(after_df.get("id", pd.Series(dtype=float)).dropna().astype(int).astype(str)) if "id" in after_df.columns else set()
    to_delete_ids = [int(x) for x in (before_ids - after_ids)]

    # Preparar ediciones: solo filas con unique_key (ignoramos filas nuevas)
    edits = editable.dropna(subset=["unique_key"]).copy()
    edits.rename(columns={"monto": "monto_real"}, inplace=True)

    updated = apply_edits(conn, edits)
    try:
        learned = update_categoria_map_from_df(conn, edits)
        if learned:
            st.info(f"Aprendidas {learned} reglas de categoría por 'detalle_norm'. Se aplicarán en futuras cargas.")
    except Exception:
        pass
    deleted = 0
    if to_delete_keys or to_delete_ids:
        deleted = delete_transactions(conn, unique_keys=to_delete_keys or None, ids=to_delete_ids or None)
    st.success(f"Actualizadas {updated} filas. Eliminadas {deleted} filas.")
    st.rerun()

if download_clicked:
    st.download_button(
        "Descargar CSV enriquecido",
        data=editable.to_csv(index=False).encode("utf-8"),
        file_name="movimientos_enriquecidos.csv",
        mime="text/csv",
    )

## Eliminación ahora se maneja directamente quitando filas en la tabla (num_rows="dynamic")


st.markdown("### Más análisis")
df_month2 = df_plot.copy()
months_es = [
    "enero","febrero","marzo","abril","mayo","junio",
    "julio","agosto","septiembre","octubre","noviembre","diciembre"
]
df_month2["mes_num"] = df_month2["fecha"].dt.month
df_month2["anio"] = df_month2["fecha"].dt.year
df_month2["mes_label"] = df_month2.apply(lambda r: f"{months_es[int(r['mes_num'])-1]} {int(r['anio'])}", axis=1)
mensual2 = df_month2.assign(_amt=np.abs(df_month2["monto" if "monto" in df_month2.columns else "monto_real_plot" ].astype(float))).groupby("mes_label")['_amt'].sum().reset_index().rename(columns={'_amt':'monto'})
chart_mensual = alt.Chart(mensual2).mark_line(point=True).encode(
    x=alt.X("mes_label:N", sort=None, title="Mes"),
    y=alt.Y("monto:Q", axis=alt.Axis(format=",.0f"), title="Gasto"),
    tooltip=["mes_label:N", alt.Tooltip("monto:Q", format=",.0f")]
).properties(height=220)
st.altair_chart(chart_mensual, use_container_width=True)

# Comparación puntual: dos barras por categoría (mes seleccionado vs anterior)
df_comp = df_plot.copy()
if not df_comp.empty:
    df_comp["period"] = df_comp["fecha"].dt.to_period("M")
    periods = sorted(df_comp["period"].dropna().unique())
    if len(periods) >= 1:
        # Determinar mes objetivo
        if 'sel_mes_label' in locals() and sel_mes_label != "Todos":
            # Tomar el último año disponible para ese mes
            sel_month_num = months_present[month_labels.index(sel_mes_label)] if sel_mes_label in month_labels else periods[-1].month
            sel_periods = [p for p in periods if p.month == sel_month_num]
            sel_p = sel_periods[-1] if sel_periods else periods[-1]
        else:
            sel_p = periods[-1]
        prev_p = sel_p - 1
        target = [p for p in periods if p in (prev_p, sel_p)]
        if len(target) == 1:
            target.insert(0, target[0])  # duplicar si solo hay uno para que el gráfico no quede vacío
        sub = df_comp[df_comp["period"].isin(target)].copy()
        sub["mes_label"] = sub["period"].apply(lambda p: months_es[p.month-1])
        amt_col = "monto" if "monto" in sub.columns else "monto_real_plot"
        comp = sub.assign(_amt=np.abs(sub[amt_col].astype(float))).groupby(["categoria","mes_label"])['_amt'].sum().reset_index().rename(columns={'_amt':'monto'})
        # Ordenar categorías por total del mes seleccionado
        sel_label = months_es[sel_p.month-1]
        order = comp[comp["mes_label"] == sel_label].sort_values("monto", ascending=False)["categoria"].tolist()
        chart_comp = alt.Chart(comp).mark_bar().encode(
            x=alt.X("categoria:N", sort=order, title="Categoría"),
            xOffset=alt.XOffset("mes_label:N"),
            y=alt.Y("monto:Q", axis=alt.Axis(format=",.0f"), title="Gasto"),
            color=alt.Color("mes_label:N", legend=alt.Legend(title="Mes")),
            tooltip=["categoria:N", "mes_label:N", alt.Tooltip("monto:Q", format=",.0f")],
        ).properties(height=320)
        st.altair_chart(chart_comp, use_container_width=True)
