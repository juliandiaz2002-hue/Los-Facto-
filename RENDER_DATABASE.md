# Base de Datos y Persistencia (Render / Neon / PostgreSQL)

Este proyecto no está amarrado a un proveedor único de base de datos.

## Regla de conexión

La app usa esta lógica:
- Si existe `DATABASE_URL` -> conecta a PostgreSQL.
- Si no existe `DATABASE_URL` -> usa SQLite local (`data/gastos.db`).

Por eso puedes correr:
- UI en Streamlit Community Cloud + BD en Render/Neon,
- UI y BD ambos en Render,
- local con SQLite.

## Formato de `DATABASE_URL`

```text
postgresql://usuario:password@host:5432/base?sslmode=require
```

En Streamlit Community Cloud se define en `Secrets`:

```toml
DATABASE_URL = "postgresql://usuario:password@host:5432/base?sslmode=require"
```

## Qué se guarda

Persisten en PostgreSQL:
- movimientos (`movimientos`),
- categorías (`categorias`),
- reglas aprendidas (`categoria_map`),
- ignorados/tombstones (`movimientos_ignorados`, `movimientos_borrados`).

## Protección contra duplicados y reingesta

- `unique_key` canónica por transacción.
- `upsert` con control de duplicados.
- tombstones para evitar que una transacción borrada reaparezca al reimportar el mismo CSV.

## Verificación rápida

Desde la app, usa:
- panel "🔎 Diagnóstico de Base de Datos" para confirmar backend y conteos,
- exportación de backup completo para validación externa.

## Rendimiento (expectativas reales)

- Localhost casi siempre será más rápido que hosting gratuito.
- En planes free, la latencia inicial suele venir por:
  - cold start de la app,
  - recursos de CPU/RAM limitados,
  - distancia entre app y base.

Para mejorar:
- mantener app y base en la misma región,
- reducir dataset visible con filtros,
- evitar redeploys innecesarios,
- considerar plan pago si necesitas latencia consistente.
