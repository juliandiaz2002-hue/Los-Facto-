import os
import re
import unicodedata
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime, timedelta

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

st.title("Dashboard de Facto$")

# Estilos ligeros (color primario en sidebar)
st.markdown(
    """
    <style>
    :root { --facto-primary:#133c60; }
    section[data-testid="stSidebar"] > div { background-color: #f0f5fa; }
    [data-testid="stSidebar"] .stButton > button { background-color: var(--facto-primary); color: white; border-color: var(--facto-primary); }
    [data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] { background-color: var(--facto-primary); }
    [data-testid="stSidebar"] .stSelectbox > div > div { border-color: var(--facto-primary); }
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

@st.cache_data(show_spinner=False)
def load_df(file):
    df = pd.read_csv(file)
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        st.error(f"Faltan columnas requeridas: {sorted(missing)}")
        st.stop()
    
    df["fecha"] = pd.to_datetime(df.get("fecha"), errors="coerce")
    
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
    
    for c in ["monto", "fraccion_mia_sugerida", "monto_mio_estimado", "monto_real"]:
        if c in df.columns:
            df[c] = df[c].apply(_clean_amount)
    
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
    
    return df

def build_suggestions_df(df, conn):
    """Construir DataFrame de sugerencias de categoría"""
    # Filas sin categoría o "Sin categoría"
    mask = (df["categoria"].isna()) | (df["categoria"] == "") | (df["categoria"] == "Sin categoría")
    sug_df = df[mask].copy()
    
    if sug_df.empty:
        return pd.DataFrame()
    
    # Fuentes de sugerencia
    suggestions = []
    
    for _, row in sug_df.iterrows():
        detalle_norm = row["detalle_norm"]
        if pd.isna(detalle_norm) or detalle_norm == "":
            continue
            
        # 1. Mapa exacto (confianza 1.0)
        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            from sqlalchemy import text
            result = engine.execute(text("SELECT categoria FROM categoria_map WHERE detalle_norm = :dn"), {"dn": detalle_norm})
            exact_match = result.fetchone()
        else:
            cur = conn.execute("SELECT categoria FROM categoria_map WHERE detalle_norm = ?", (detalle_norm,))
            exact_match = cur.fetchone()
        
        if exact_match:
            suggestions.append({
                "unique_key": row.get("unique_key", ""),
                "detalle": row["detalle"],
                "detalle_norm": detalle_norm,
                "sugerida": exact_match[0],
                "fuente": "Mapa exacto",
                "confianza": 1.0,
                "aceptar": False,
                "manual": ""
            })
            continue
        
        # 2. Historial dominante por detalle_norm (≥70%)
        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            result = engine.execute(text("""
                SELECT categoria, COUNT(*) as cnt, 
                       COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as pct
                FROM movimientos 
                WHERE detalle_norm = :dn AND categoria IS NOT NULL AND categoria != 'Sin categoría'
                GROUP BY categoria
                HAVING COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() >= 70
                ORDER BY cnt DESC
                LIMIT 1
            """), {"dn": detalle_norm})
            hist_match = result.fetchone()
        else:
            cur = conn.execute("""
                SELECT categoria, COUNT(*) as cnt
                FROM movimientos 
                WHERE detalle_norm = ? AND categoria IS NOT NULL AND categoria != 'Sin categoría'
                GROUP BY categoria
                HAVING COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() >= 70
                ORDER BY cnt DESC
                LIMIT 1
            """, (detalle_norm,))
            hist_match = cur.fetchone()
        
        if hist_match:
            suggestions.append({
                "unique_key": row.get("unique_key", ""),
                "detalle": row["detalle"],
                "detalle_norm": detalle_norm,
                "sugerida": hist_match[0],
                "fuente": "Historial dominante",
                "confianza": 0.8,
                "aceptar": False,
                "manual": ""
            })
            continue
        
        # 3. Reglas por regex/keywords (confianza 0.7)
        # Aquí podrías implementar reglas más sofisticadas
        suggestions.append({
            "unique_key": row.get("unique_key", ""),
            "detalle": row["detalle"],
            "detalle_norm": detalle_norm,
            "sugerida": "Sin categoría",
            "fuente": "Sin sugerencia",
            "confianza": 0.0,
            "aceptar": False,
            "manual": ""
        })
    
    return pd.DataFrame(suggestions)


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


# Preparar base de trabajo
dfv = df.copy()
# Asegurar tipo numérico en monto para evitar NaNs o strings
if "monto" in dfv.columns:
    dfv["monto"] = pd.to_numeric(dfv["monto"], errors="coerce").fillna(0)
# Determinar tipo de movimiento: usa columna 'tipo' si existe (por ejemplo en CSV exportado),
# si no, deriva desde el signo de 'monto'.
if "tipo" in dfv.columns:
    dfv["tipo_calc"] = dfv["tipo"].astype(str)
else:
    dfv["tipo_calc"] = np.where(dfv["monto"] < 0, "Gasto", np.where(dfv["monto"] > 0, "Abono", "Cero"))
    # Fallback para CSV enriquecido re-importado (montos positivos, sin columna 'tipo')
    if not (dfv["tipo_calc"] == "Gasto").any() and (dfv["monto"] >= 0).all():
        dfv["tipo_calc"] = "Gasto"
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

# Tipo final y monto para mostrar
dfv["tipo"] = dfv["tipo_calc"]
dfv["monto_cartola"] = dfv["monto"].abs()

# Solo gastos en la vista principal (soporta CSVs exportados con 'monto' positivo)
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
    amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
    total_real = float(df_plot[amt_col].abs().fillna(0).sum())
    st.metric("Gasto real (visible)", f"${total_real:,.0f}")
with col2:
    if not df_plot.empty:
        cat_agg_metric = df_plot.assign(_amt=np.abs(df_plot[amt_col].astype(float))).groupby("categoria")["_amt"].sum().sort_values(ascending=False)
        if len(cat_agg_metric) > 0:
            st.metric("Categoría más relevante", f"{cat_agg_metric.index[0]}")

# Donut por categoría (centrado y simple)
if not df_plot.empty:
    amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
    cat_agg = (
        df_plot.assign(_amt=np.abs(pd.to_numeric(df_plot[amt_col], errors="coerce").fillna(0)))
        .groupby("categoria", dropna=False)["_amt"].sum().reset_index()
        .rename(columns={"_amt": "total"})
        .sort_values("total", ascending=False)
    )
    
    # Layout simple: donut centrado, sin redundancia
    st.markdown("### Distribución de Gastos por Categoría")
    
    # Donut centrado y optimizado
    chart_donut = (
        alt.Chart(cat_agg)
        .mark_arc(
            innerRadius=80, 
            outerRadius=140, 
            cornerRadius=4, 
            padAngle=0.02,
            stroke="#ffffff",
            strokeWidth=2
        )
        .encode(
            theta=alt.Theta("total:Q", stack=True),
            color=alt.Color(
                "categoria:N",
                scale=alt.Scale(domain=domain, range=range_colors),
                legend=alt.Legend(
                    title="Categoría",
                    orient="bottom",
                    direction="horizontal",
                    columns=4
                )
            ),
            tooltip=[
                alt.Tooltip("categoria:N", title="Categoría"),
                alt.Tooltip("total:Q", format=",.0f", title="Total")
            ],
        )
        .properties(
            width=500, 
            height=400
        )
        .configure_view(stroke=None)
        .configure_axis(grid=False)
    )
    
    # Centrar el donut
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.altair_chart(chart_donut, use_container_width=True, theme="streamlit")
    
    # Selector simple de categoría para filtrado
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

cols_ins = st.columns(3)
with cols_ins[0]:
    if not df_plot.empty:
        amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
        freq = df_plot.groupby("categoria").size().reset_index(name="veces").sort_values("veces", ascending=False)
        # Gráfico de frecuencia mejorado
        chart_freq = (
            alt.Chart(freq)
            .mark_bar(
                cornerRadiusTopLeft=4,
                cornerRadiusTopRight=4,
                stroke="#ffffff",
                strokeWidth=1
            )
            .encode(
                x=alt.X("categoria:N", sort='-y', title="Categoría"),
                y=alt.Y("veces:Q", title="Cantidad de Transacciones"),
                color=alt.Color("categoria:N", legend=None),
                tooltip=[
                    alt.Tooltip("categoria:N", title="Categoría"),
                    alt.Tooltip("veces:Q", title="Cantidad")
                ],
            )
            .properties(
                height=220,
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
with cols_ins[1]:
    if not df_plot.empty:
        amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
        avg = df_plot.assign(_amt=df_plot[amt_col].abs()).groupby("categoria")["_amt"].mean().reset_index().rename(columns={'_amt':'ticket_prom'})
        # Gráfico de ticket promedio mejorado
        chart_avg = (
            alt.Chart(avg)
            .mark_bar(
                cornerRadiusTopLeft=4,
                cornerRadiusTopRight=4,
                stroke="#ffffff",
                strokeWidth=1
            )
            .encode(
                x=alt.X("categoria:N", sort='-y', title="Categoría"),
                y=alt.Y("ticket_prom:Q", title="Ticket Promedio", axis=alt.Axis(format=",.0f")),
                color=alt.Color("categoria:N", legend=None),
                tooltip=[
                    alt.Tooltip("categoria:N", title="Categoría"),
                    alt.Tooltip("ticket_prom:Q", format=",.0f", title="Ticket Promedio")
                ],
            )
            .properties(
                height=220,
                title={
                    "text": "Ticket Promedio por Categoría",
                    "fontSize": 14,
                    "fontWeight": "bold",
                    "color": "#133c60"
                }
            )
            .configure_view(stroke=None)
            .configure_axis(grid=False)
        )
        st.altair_chart(chart_avg, use_container_width=True)
with cols_ins[2]:
    if not df_plot.empty:
        dia_map = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
        df_plot["dow"] = df_plot["fecha"].dt.dayofweek.map(dia_map)
        df_plot["dow_idx"] = df_plot["fecha"].dt.dayofweek
        amt_col = "monto" if "monto" in df_plot.columns else "monto_real_plot"
        dow_agg = df_plot.assign(_amt=np.abs(df_plot[amt_col].astype(float))).groupby(["dow", "dow_idx"])['_amt'].sum().reset_index()
        dow_agg.rename(columns={"_amt": "total"}, inplace=True)
        # Gráfico de gastos por día de semana mejorado
        chart_dow = (
            alt.Chart(dow_agg)
            .mark_line(
                point=True,
                stroke="#4e79a7",
                strokeWidth=3,
                pointSize=60
            )
            .encode(
                x=alt.X("dow:N", sort=["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"], title="Día de la Semana"),
                y=alt.Y("total:Q", title="Total de Gastos", axis=alt.Axis(format=",.0f")),
                tooltip=[
                    alt.Tooltip("dow:N", title="Día"),
                    alt.Tooltip("total:Q", format=",.0f", title="Total")
                ],
            )
            .properties(
                height=220,
                title={
                    "text": "Gastos por Día de la Semana",
                    "fontSize": 14,
                    "fontWeight": "bold",
                    "color": "#133c60"
                }
            )
            .configure_view(stroke=None)
            .configure_axis(grid=False)
        )
        st.altair_chart(chart_dow, use_container_width=True)

# Comparación mes seleccionado vs anterior
if sel_mes and sel_mes != "Todos" and not df_plot.empty:
    st.markdown("### Comparación mes seleccionado vs anterior")
    try:
        y, m = sel_mes.split("-")
        current_start = pd.to_datetime(f"{y}-{m}-01")
        current_end = current_start + pd.offsets.MonthEnd(1)
        
        # Mes anterior
        prev_start = current_start - pd.offsets.MonthBegin(1)
        prev_end = current_start - pd.offsets.Day(1)
        
        # Datos del mes actual
        current_data = df_plot[(df_plot["fecha"] >= current_start) & (df_plot["fecha"] <= current_end)].copy()
        current_data["mes"] = "Actual"
        
        # Datos del mes anterior
        prev_data = df_plot[(df_plot["fecha"] >= prev_start) & (df_plot["fecha"] <= prev_end)].copy()
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
            chart_comparison = alt.Chart(comparison_agg).mark_bar().encode(
                x=alt.X("categoria:N", title="Categoría"),
                y=alt.Y("total:Q", title="Total", axis=alt.Axis(format=",.0f")),
                color=alt.Color("mes:N", title="Mes"),
                tooltip=["categoria:N", "mes:N", alt.Tooltip("total:Q", format=",.0f")],
            ).properties(height=250)
            st.altair_chart(chart_comparison, use_container_width=True)
    except Exception as e:
        st.warning(f"No se pudo generar la comparación: {e}")

# Sugerencias de categoría
st.markdown("### Sugerencias de categoría")
suggestions_df = build_suggestions_df(dfv, conn)

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
        
        col_apply, col_accept_all = st.columns(2)
        with col_apply:
            apply_selected = st.form_submit_button("Aplicar seleccionadas")
        with col_accept_all:
            accept_high_conf = st.form_submit_button("Aceptar todas ≥ 0.9")
        
        if apply_selected or accept_high_conf:
            # Aplicar sugerencias aceptadas
            to_apply = suggestions_df.copy()
            
            if accept_high_conf:
                # Aceptar todas con confianza ≥ 0.9
                high_conf_mask = to_apply["confianza"] >= 0.9
                to_apply.loc[high_conf_mask, "aceptar"] = True
            
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

# Formulario de edición mejorado
with st.form("editor_form", clear_on_submit=False):
    st.markdown("**✏️ Edita las transacciones y guarda los cambios**")
    
    editable = st.data_editor(
        df_table,
        num_rows="dynamic",  # permite borrar filas en la propia tabla
        use_container_width=True,
        key="tabla_gastos",
        column_config={
            "fecha": st.column_config.DatetimeColumn(
                format="YYYY-MM-DD",
                help="Fecha de la transacción"
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
    
    # Botones de acción mejorados
    col_s, col_d, col_info = st.columns([1, 1, 2])
    with col_s:
        save_clicked = st.form_submit_button(
            "💾 Guardar cambios",
            help="Guarda todos los cambios en la base de datos",
            use_container_width=True
        )
    with col_d:
        download_clicked = st.form_submit_button(
            "📥 Descargar CSV",
            help="Descarga la tabla actual en formato CSV",
            use_container_width=True
        )
    with col_info:
        if save_clicked:
            st.info("🔄 Procesando cambios...")
        elif download_clicked:
            st.info("📤 Preparando descarga...")

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
amt_col = "monto" if "monto" in df_month2.columns else "monto_real_plot"
mensual2 = df_month2.assign(_amt=np.abs(pd.to_numeric(df_month2[amt_col], errors="coerce").fillna(0))).groupby("mes")["_amt"].sum().reset_index().rename(columns={"_amt":"monto"})
# Gráfico de tendencias mensuales mejorado
chart_mensual = (
    alt.Chart(mensual2)
    .mark_line(
        point=True,
        stroke="#133c60",
        strokeWidth=3,
        pointSize=80
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

# Botón "Reparar montos" para sincronizar monto = abs(monto_real) para "Gasto"
st.markdown("### Herramientas de mantenimiento")
if st.button("Reparar montos"):
    try:
        # Buscar discrepancias entre monto y monto_real para gastos
        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            from sqlalchemy import text
            result = engine.execute(text("""
                UPDATE movimientos 
                SET monto = ABS(monto_real) 
                WHERE monto_real IS NOT NULL 
                AND monto_real > 0 
                AND (monto IS NULL OR monto = 0 OR ABS(monto) != monto_real)
                AND tipo = 'Gasto'
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

# Panel para listar/restaurar "movimientos_ignorados"
with st.expander("Movimientos ignorados"):
    try:
        if isinstance(conn, dict) and conn.get("pg"):
            engine = conn["engine"]
            ignored_df = pd.read_sql_query("SELECT unique_key, created_at FROM movimientos_ignorados ORDER BY created_at DESC", engine)
        else:
            ignored_df = pd.read_sql_query("SELECT unique_key, created_at FROM movimientos_ignorados ORDER BY created_at DESC", conn)
        
        if not ignored_df.empty:
            st.write(f"Total de movimientos ignorados: {len(ignored_df)}")
            st.dataframe(ignored_df, use_container_width=True)
            
            # Opción para restaurar
            if st.button("Restaurar todos los ignorados"):
                try:
                    if isinstance(conn, dict) and conn.get("pg"):
                        engine = conn["engine"]
                        engine.execute(text("DELETE FROM movimientos_ignorados"))
                    else:
                        conn.execute("DELETE FROM movimientos_ignorados")
                        conn.commit()
                    st.success("Todos los movimientos ignorados han sido restaurados. Pueden volver a aparecer en futuras cargas.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al restaurar: {e}")
        else:
            st.info("No hay movimientos ignorados.")
    except Exception as e:
        st.warning(f"No se pudo cargar movimientos ignorados: {e}")
