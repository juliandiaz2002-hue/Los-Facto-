# finanzas-julian

Plataforma mínima (local/Streamlit) para subir cartolas, estandarizar, revisar transacciones y consolidar un **master** histórico con aprendizaje de categorías por comercio y matching de **reembolsos**.

## 0) Estructura

```
finanzas-julian/
├─ app/
│  └─ app.py
├─ data/
│  ├─ master.csv                 # se crea al primer update
│  ├─ merchant_map.json          # mapeo de comercios -> categoría (aprende con el uso)
│  └─ config.json                # aliases de cuentas propias, tolerancias, etc.
├─ prep.py                       # estandariza un CSV crudo del banco -> standardized.csv
├─ update_master.py              # integra un standardized.csv al master, dedup y aprendizaje
├─ requirements.txt
└─ README.md
```

## 1) Crear venv e instalar deps

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

## 2) Estandarizar un CSV crudo

Coloca tu export del banco como `raw.csv` o la ruta que prefieras:

```bash
python prep.py --in raw.csv --out data/standardized.csv
```

## 3) Actualizar el master (apéndice de movimientos nuevos)

```bash
python update_master.py --in data/standardized.csv --master data/master.csv
```

- Aprende categorías nuevas según `merchant_map.json` (y lo actualiza).
- Hace match básico de **reembolsos** (abonos positivos) contra gastos previos cercanos.
- Evita duplicados usando un hash por (`fecha`,`detalle_norm`,`monto`).
- Marca transferencias/abonos entre tus **propias cuentas** usando `config.json`.

## 4) Revisar y editar en Streamlit

```bash
streamlit run app/app.py
```

- Filtros por fecha/categoría; tabla editable para `categoria` y `fraccion_mia`.
- Botón **Guardar cambios**: escribe `data/master.csv` y actualiza `merchant_map.json`.

## 5) GitHub + Streamlit Cloud (rápido)

1. Crea un repo en GitHub y sube todo el folder.
2. En Streamlit Cloud: **New app** → selecciona repo y `app/app.py`.
3. Variables opcionales: ninguna necesaria; los archivos se guardan en el filesystem del deploy (para persistir a largo plazo, integra Git LFS o un bucket S3/Drive). Para local es suficiente.

## Notas
- `config.json` incluye `account_aliases` (palabras/últimos dígitos para detectar **movimientos entre tus cuentas**) y parámetros de matching de reembolsos.
- Los nombres de columnas de tu banco se detectan automáticamente, pero si tu banco cambia el formato, ajusta `prep.py`.
