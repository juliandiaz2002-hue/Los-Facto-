# Guía de Despliegue - Dashboard de Facto$

## Despliegue Local

### 1. Preparar el entorno

```bash
# Crear entorno virtual
python -m venv .venv

# Activar entorno virtual
# En macOS/Linux:
source .venv/bin/activate
# En Windows:
.venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Inicializar la base de datos

```bash
# Inicializar base de datos SQLite local
python init_db.py
```

### 3. Ejecutar la aplicación

```bash
streamlit run app.py
```

La aplicación estará disponible en: http://localhost:8501

## Despliegue en Render (Plan Free)

### 1. Preparar el repositorio

Asegúrate de que tu repositorio contenga:
- `app.py` - Aplicación principal
- `db.py` - Módulo de base de datos
- `requirements.txt` - Dependencias
- `render.yaml` - Configuración de Render
- `runtime.txt` - Versión de Python

### 2. Crear cuenta en Render

1. Ve a [render.com](https://render.com)
2. Crea una cuenta gratuita
3. Conecta tu repositorio de GitHub

### 3. Desplegar la aplicación

1. En Render, haz clic en "New +"
2. Selecciona "Web Service"
3. Conecta tu repositorio
4. Configura:
   - **Name**: `factos-dashboard`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

### 4. Configurar la base de datos Postgres

1. En Render, crea un nuevo servicio de base de datos:
   - **Type**: PostgreSQL
   - **Name**: `factos-postgres`
   - **Plan**: Free

2. Copia la **Internal Database URL** del servicio Postgres

3. En tu Web Service, agrega la variable de entorno:
   - **Key**: `DATABASE_URL`
   - **Value**: [Internal Database URL de Postgres]

### 5. Variables de entorno requeridas

```bash
PYTHON_VERSION=3.11.9
PYTHONUNBUFFERED=1
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
DATABASE_URL=<Internal URL de tu Postgres>
```

### 6. Desplegar

1. Haz clic en "Create Web Service"
2. Espera a que se complete el build
3. Tu aplicación estará disponible en la URL proporcionada por Render

## Configuración de la Base de Datos

### SQLite (Desarrollo Local)
- Archivo: `data/gastos.db`
- No requiere configuración adicional
- Se crea automáticamente al ejecutar `init_db.py`

### Postgres (Producción)
- Hosted en Render (plan gratuito)
- Se configura automáticamente via `DATABASE_URL`
- Los datos persisten entre redeploys

## Estructura de la Base de Datos

### Tabla `movimientos`
```sql
CREATE TABLE movimientos (
    id INTEGER,
    fecha TIMESTAMP,
    detalle TEXT,
    monto DOUBLE PRECISION,
    es_gasto BOOLEAN,
    es_transferencia_o_abono BOOLEAN,
    es_compartido_posible BOOLEAN,
    fraccion_mia_sugerida DOUBLE PRECISION,
    monto_mio_estimado DOUBLE PRECISION,
    categoria_sugerida TEXT,
    detalle_norm TEXT,
    monto_real DOUBLE PRECISION,
    categoria TEXT,
    nota_usuario TEXT,
    unique_key TEXT UNIQUE
);
```

### Tablas auxiliares
- `categorias` - Lista de categorías disponibles
- `categoria_map` - Mapeo aprendido de detalle_norm → categoría
- `movimientos_ignorados` - Registros ignorados permanentemente

## Solución de Problemas

### Error de conexión a Postgres
- Verifica que `DATABASE_URL` esté configurada correctamente
- Asegúrate de que el servicio Postgres esté activo
- Verifica que la URL use `postgresql://` (no `postgres://`)

### Error de build
- Verifica que `requirements.txt` contenga todas las dependencias
- Asegúrate de que `runtime.txt` especifique una versión válida de Python
- Limpia el cache de build en Render si es necesario

### Error de importación
- Verifica que todos los archivos estén en el repositorio
- Asegúrate de que las rutas de importación sean correctas

## Monitoreo y Mantenimiento

### Logs
- Los logs de la aplicación están disponibles en el dashboard de Render
- Revisa regularmente para detectar errores

### Base de datos
- El plan gratuito de Postgres tiene limitaciones de uso
- Monitorea el uso de la base de datos en el dashboard de Render

### Actualizaciones
- Para actualizar la aplicación, simplemente haz push a tu repositorio
- Render detectará automáticamente los cambios y redeployará

## Costos

### Plan Gratuito de Render
- **Web Service**: Gratis (se "duerme" después de 15 minutos de inactividad)
- **Postgres**: Gratis (hasta 1GB de datos)
- **Bandwidth**: Gratis (hasta 750GB/mes)

### Limitaciones del Plan Gratuito
- El servicio se "duerme" después de 15 minutos de inactividad
- El primer request después del "sueño" puede tardar hasta 1 minuto
- La base de datos Postgres se elimina después de 90 días de inactividad

## Migración de Datos

### De SQLite a Postgres
1. Exporta los datos desde SQLite:
   ```bash
   sqlite3 data/gastos.db ".dump" > backup.sql
   ```

2. Importa a Postgres (requiere configuración manual)

### Backup de Postgres
- Render no proporciona backups automáticos en el plan gratuito
- Considera hacer backups manuales periódicos
- Para producción, considera el plan de pago con backups automáticos
