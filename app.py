import os
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

st.set_page_config(page_title="Gastos de Julián", layout="wide")

st.title("Gastos de Julián — Revisión transacción por transacción")

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
    # Filtro por mes (además del rango de fechas)
    df_months = df.copy()
    df_months["mes"] = df_months["fecha"].dt.to_period("M").astype(str)
    months = sorted([m for m in df_months["mes"].dropna().unique().tolist()])
    sel_mes = st.selectbox("Mes", options=["Todos"] + months, index=0)
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
if sel_mes and sel_mes != "Todos":
    y, m = sel_mes.split("-")
    start = pd.to_datetime(f"{y}-{m}-01")
    end = start + pd.offsets.MonthEnd(1)
    dfv = dfv[(dfv["fecha"] >= start) & (dfv["fecha"] <= end)]
elif isinstance(rango, tuple) and len(rango) == 2:
    dfv = dfv[(dfv["fecha"] >= pd.to_datetime(rango[0])) & (dfv["fecha"] <= pd.to_datetime(rango[1]))]
elif rango:
    dfv = dfv[dfv["fecha"].dt.date == rango]

# tipo por signo y monto sin signo para mostrar
dfv["tipo"] = np.where(dfv["monto"] < 0, "Gasto", np.where(dfv["monto"] > 0, "Abono", "Cero"))
dfv["monto_cartola"] = dfv["monto"].abs()

# Solo gastos en la vista principal
dfv = dfv[dfv["tipo"] == "Gasto"].copy()

# Filtro por categoría (para acompañar interacción del gráfico)
cat_options = sorted([c for c in categories if c])
sel_cats = st.sidebar.multiselect("Categorías", options=["Todas"] + cat_options, default=["Todas"])
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
    total_real = float(df_plot["monto"].fillna(0).sum()) if "monto" in df_plot.columns else float(df_plot["monto_real_plot"].fillna(0).sum())
    st.metric("Gasto real (visible)", f"${total_real:,.0f}")
with col2:
    top_merchant = (
        df_plot.groupby("detalle_norm")["monto"].sum().abs().sort_values(ascending=False).head(1)
        if "monto" in df_plot.columns and not df_plot.empty else None
    )
    if top_merchant is not None and len(top_merchant) > 0:
        st.metric("Comercio más relevante", f"{top_merchant.index[0]}")

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
    ).properties(height=180)
    st.altair_chart(chart_dow, use_container_width=True)


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
df_month2["mes"] = df_month2["fecha"].dt.to_period("M").astype(str)
mensual2 = df_month2.groupby("mes")["monto"].sum().reset_index()
chart_mensual = alt.Chart(mensual2).mark_line(point=True).encode(
    x=alt.X("mes:N"), y=alt.Y("monto:Q", axis=alt.Axis(format=",.0f")), tooltip=["mes:N", alt.Tooltip("monto:Q", format=",.0f")]
).properties(height=220)
st.altair_chart(chart_mensual, use_container_width=True)

