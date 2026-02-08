# Guía de Despliegue - Dashboard de Facto$

Este documento cubre tres escenarios:
- ejecución local,
- Streamlit Community Cloud,
- Render.

## 1) Ejecución local

### Requisitos

- Python 3.11
- Git

### Pasos

```bash
git clone <tu-repo>
cd "Los Facto$"
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 init_db.py
python3 -m streamlit run app.py
```

Abrir: `http://localhost:8501`

## 2) Streamlit Community Cloud (recomendado para hosting gratis de la UI)

### 2.1 Preparar repo

Asegúrate de tener en `main`:
- `app.py`
- `db.py`
- `requirements.txt`
- `runtime.txt`

### 2.2 Crear app

1. Ir a [share.streamlit.io](https://share.streamlit.io/).
2. `New app`.
3. Seleccionar repo, branch `main` y archivo `app.py`.
4. Deploy.

### 2.3 Configurar secretos (si usas PostgreSQL)

En **App settings -> Secrets**, agrega:

```toml
DATABASE_URL = "postgresql://usuario:password@host:5432/base?sslmode=require"
```

Notas:
- Debe ir entre comillas.
- Formato TOML válido.
- Si no defines `DATABASE_URL`, la app intentará SQLite local del contenedor (no recomendado para producción).

### 2.4 Redeploy

- `Reboot app` o `Rerun from latest commit`.

## 3) Render (Web Service)

### 3.1 Uso con `render.yaml`

El repo ya incluye configuración base:
- build: `pip install -r requirements.txt`
- start: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

### 3.2 Variables esperadas

- `DATABASE_URL` (si usas PostgreSQL)
- `PYTHONUNBUFFERED=1`
- `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false`

### 3.3 Consideraciones plan free

- cold starts más lentos;
- menor CPU/RAM que local;
- latencia mayor en primera carga.

## Base de datos y persistencia

La app selecciona backend automáticamente:
- con `DATABASE_URL` -> PostgreSQL,
- sin `DATABASE_URL` -> SQLite `data/gastos.db`.

Tablas clave:
- `movimientos`
- `categorias`
- `categoria_map`
- `movimientos_ignorados`
- `movimientos_borrados` (tombstones)

## Checklist post-deploy

1. Abre la app y revisa que cargue sin errores.
2. Sube un CSV pequeño.
3. Verifica que aparezca en tabla y gráficos.
4. Edita una categoría y guarda.
5. Recarga página y confirma persistencia.
6. Prueba eliminar una fila y reimportar CSV para validar tombstones.

## Troubleshooting rápido

### Error: `installer returned a non-zero exit code`

- Verifica `runtime.txt` (Python 3.11).
- Revisa versiones en `requirements.txt`.
- Reinicia build desde el panel.

### Error: `zsh: command not found: pip`

Usa:

```bash
python3 -m pip install -r requirements.txt
```

### Error: `zsh: command not found: streamlit`

Usa:

```bash
python3 -m streamlit run app.py
```
