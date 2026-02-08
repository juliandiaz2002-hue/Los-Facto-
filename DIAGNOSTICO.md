# 🔍 Diagnóstico Completo - Dashboard Facto$

**Fecha:** 8 de febrero de 2025  
**Versión analizada:** app.py (~2436 líneas), db.py, prep.py

---

## 📋 Resumen Ejecutivo

Se identificaron **errores fundamentales** en el manejo de claves únicas, la carga de CSV y la consistencia entre módulos. Las correcciones aplicadas abordan las causas raíz de caídas, duplicados y fallos con archivos bancarios.

---

## 🚨 Errores Críticos Encontrados y Corregidos

### 1. **unique_key inconsistente (CRÍTICO - CAUSA DE DUPLICADOS Y REINGESTA)**

**Problema:** `app.py` usaba `hash()` de Python para generar `unique_key`:
```python
return f"h:{hash((fstr, mc_val, d))}"  # ❌ hash() NO es determinístico entre sesiones
```
- En Python 3.3+, `hash()` incluye sal para seguridad → **varía entre reinicios**
- `db.py` usa `hashlib.sha256` → formato `k:xxx` (determinístico)
- **Consecuencia:** Las tombstones (filas borradas) usaban claves `k:xxx`, pero el CSV generaba `h:xxx` → las filas eliminadas volvían a aparecer al subir de nuevo el CSV.

**Corrección:** Uso exclusivo del algoritmo de `db._compute_unique_key_row` vía `compute_unique_keys_for_df()` antes del filtro de tombstones y upsert.

---

### 2. **Filtro de Tombstones con claves incorrectas**

**Problema:** Se filtraban tombstones usando `unique_key` generado por `hash()` en lugar del canónico de la BD.

**Corrección:** Se llama a `compute_unique_keys_for_df()` antes del filtro de tombstones para alinear claves con la BD.

---

### 3. **Carga CSV frágil (encoding y formato)**

**Problemas:**
- Sin detección de encoding → archivos Latin-1/CP1252 de bancos chilenos fallaban
- Columnas fijas (`fecha`, `detalle`, `monto`) → no reconocía `glosa`, `descripcion`, `cargo`, `importe`
- Formato de fecha rígido → `DD/MM/YYYY` mal interpretado
- Sin `on_bad_lines="skip"` → una línea corrupta tiraba todo el proceso

**Correcciones:**
- Detección de encoding con `chardet`
- Aliases de columnas: `glosa`→`detalle`, `cargo`→`monto`, `fraccion_mia`→`fraccion_mia_sugerida`, etc.
- `pd.to_datetime(..., dayfirst=True)` para fechas chilenas
- Fallback con `on_bad_lines="skip"` en lectura CSV

---

### 4. **Incompatibilidad con prep.py**

**Problema:** `prep.py` genera `fraccion_mia`, `monto_mio`, `id` (sha1); la app esperaba `fraccion_mia_sugerida`, `monto_mio_estimado`.

**Corrección:** Mapeo de columnas en `load_df` y en `upsert_transactions` para aceptar ambos formatos.

---

## ⚠️ Problemas de Rendimiento (identificados, no corregidos por complejidad)

| Área | Situación | Recomendación |
|------|-----------|---------------|
| **load_all** | Carga toda la tabla sin límite | Paginación o filtro por rango de fechas por defecto |
| **upsert_transactions** | Inserción fila por fila en Postgres | Batch insert con `executemany` o COPY |
| **build_suggestions_df** | Uso de `iterrows()` | Vectorización con merge/groupby |
| **Dashboard** | Varios gráficos Altair por carga | Lazy rendering o tabs para gráficos |
| **st.cache_data(load_df)** | Cache por archivo puede ser inefectivo | TTL corto o invalidación explícita tras subida |

---

## 🔧 Recomendaciones de Arquitectura

### Corto plazo (ya implementadas)
- [x] unique_key canónico en todo el flujo
- [x] Tombstones con claves correctas
- [x] Encoding y columnas flexibles en CSV
- [x] Compatibilidad con prep.py

### Medio plazo
1. **Migrar carga directa:** Permitir subir CSV crudo de banco y procesar con lógica de `prep.py` integrada en la app.
2. **Índices DB:** Revisar que `idx_movimientos_fecha`, `idx_movimientos_categoria` estén en uso.
3. **Límite de carga:** Mostrar primeras N filas en tablas y gráficos; opción "cargar más".
4. **Validación pre-upload:** Preview del CSV antes de insertar (columnas detectadas, muestra, advertencias).

### Largo plazo
1. **API REST:** Separar backend (FastAPI/Flask) de Streamlit para mejor escalabilidad.
2. **Jobs asíncronos:** Subir CSV → procesamiento en background → notificación al terminar.
3. **Tests:** Suite de tests para `load_df`, `upsert_transactions`, `compute_unique_keys_for_df`.

---

## 📁 Archivos Modificados

| Archivo | Cambios |
|---------|---------|
| `app.py` | `compute_unique_keys_for_df` antes de tombstone; encoding y aliases en `load_df`; fechas flexibles; import `io` |
| `db.py` | Nueva función `compute_unique_keys_for_df`; alias `fraccion_mia`/`monto_mio` en upsert |

---

## ✅ Checklist Post-Deploy

- [ ] Subir CSV de banco (Latin-1, punto y coma) y confirmar carga correcta
- [ ] Borrar una transacción y volver a subir el mismo CSV → no debe reaparecer
- [ ] Usar CSV generado por `prep.py` → debe procesarse sin errores
- [ ] Revisar que no haya duplicados por `unique_key` en la BD

---

*Diagnóstico realizado tras revisión completa del código. Las correcciones priorizan estabilidad y compatibilidad sobre optimizaciones de rendimiento.*
