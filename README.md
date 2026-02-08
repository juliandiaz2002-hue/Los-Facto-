# Dashboard de Facto$ - Control de Gastos

Aplicación en Streamlit para cargar cartolas en CSV, mantener un historial de movimientos, categorizar gastos con aprendizaje incremental y analizar tendencias.

## Qué hace hoy

- Carga CSV desde sidebar con detección de encoding y delimitador.
- Soporta alias de columnas (`glosa`, `descripcion`, `cargo`, `importe`, etc.).
- Selector de formato de fecha al cargar (`YYYY-MM-DD` o `YYYY-DD-MM`).
- Deduplicación robusta por `unique_key` canónica.
- Persistencia en:
  - SQLite local (`data/gastos.db`) si no hay `DATABASE_URL`.
  - PostgreSQL si existe `DATABASE_URL`.
- Bloqueo de "resurrección" de transacciones borradas usando tombstones (`movimientos_borrados`).
- Gestión de categorías (agregar, eliminar, renombrar, mapear por `detalle_norm`).
- Panel de sugerencias de categoría con flujo:
  - `Aceptar` sugerencia.
  - `Rechazar` y guardar categoría manual.
- Sugerencias priorizan reglas aprendidas y coincidencias por nombre/monto similar.
- Registro manual rápido de gastos desde una fila/formulario compacto.
- Tabla editable de movimientos con:
  - edición de monto/categoría/nota,
  - eliminación directa,
  - descarga CSV enriquecido.
- Dashboard con insights y gráficos:
  - métricas clave,
  - donut por categoría,
  - frecuencia por categoría,
  - gasto por día de semana,
  - ticket promedio,
  - comparación mes actual vs mes anterior,
  - tendencia mensual.
- Herramientas de mantenimiento:
  - reparar montos,
  - revisar/reincorporar `movimientos_ignorados`,
  - diagnóstico de base,
  - exportar backup completo de `movimientos`.

## Stack

- Python 3.11
- Streamlit
- Pandas / NumPy
- Altair
- SQLAlchemy
- SQLite (local) / PostgreSQL (producción)

## Estructura principal

```text
app.py                # UI + lógica principal
/db.py                # conexiones, esquema y operaciones de BD
/init_db.py           # inicialización manual de esquema
/requirements.txt     # dependencias
/runtime.txt          # versión de Python para deploy
/render.yaml          # despliegue en Render
/data/gastos.db       # SQLite local (se crea automáticamente)
```

## Correr en local

1. Crear y activar entorno virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Instalar dependencias

```bash
python3 -m pip install -r requirements.txt
```

3. Inicializar base (opcional, la app también auto-inicializa)

```bash
python3 init_db.py
```

4. Levantar app

```bash
python3 -m streamlit run app.py
```

URL local: `http://localhost:8501`

## Configuración de base de datos

### Opción A: SQLite local (por defecto)

No definas `DATABASE_URL`.

### Opción B: PostgreSQL (Render, Neon u otro)

Define variable de entorno:

```bash
DATABASE_URL=postgresql://usuario:password@host:5432/base?sslmode=require
```

La app detecta automáticamente PostgreSQL cuando existe `DATABASE_URL`.

## Formato CSV mínimo

Columnas mínimas:
- `fecha`
- `detalle`
- `monto`

Aliases aceptados automáticamente:
- `glosa`, `descripcion`, `concepto`, `comercio` -> `detalle`
- `cargo`, `debe`, `debito`, `importe` -> `monto`
- `fecha movimiento`, `date`, `fecha_mov` -> `fecha`

## Flujo recomendado de uso

1. Cargar CSV en "📂 Cargar movimientos" (sidebar).
2. Revisar panel "Sugerencias de categoría" y aceptar/rechazar.
3. Completar ajustes en "Tabla editable" y guardar cambios.
4. Usar insights y gráficos para seguimiento mensual.
5. Exportar backup de base periódicamente.

## Deploy

Guía paso a paso:
- [DEPLOYMENT.md](DEPLOYMENT.md)

Persistencia y arquitectura de BD:
- [RENDER_DATABASE.md](RENDER_DATABASE.md)

## Solución rápida de problemas comunes

Si `pip` no existe:

```bash
python3 -m pip install -r requirements.txt
```

Si `streamlit` no existe:

```bash
python3 -m streamlit run app.py
```

Si el deploy falla por dependencias:
- verifica `requirements.txt` y `runtime.txt`;
- reinicia/redeploya desde el último commit.
