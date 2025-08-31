# Dashboard de Facto$ - Finanzas Personales

Una aplicación web moderna para gestionar finanzas personales, subir cartolas bancarias, categorizar gastos automáticamente y obtener insights financieros detallados.

## 🚀 Características Principales

### 📊 Gestión de Datos
- **Upload de CSV**: Sube cartolas bancarias en formato CSV
- **Estandarización automática**: Convierte automáticamente formatos bancarios a formato estándar
- **Deduplicación inteligente**: Evita duplicados usando claves únicas
- **Persistencia robusta**: Soporte para SQLite (local) y PostgreSQL (producción)

### 🏷️ Categorización Inteligente
- **Sugerencias automáticas**: Sistema de sugerencias basado en historial y reglas aprendidas
- **Aprendizaje continuo**: Mejora las sugerencias con cada edición del usuario
- **Mapeo de comercios**: Aprende patrones por detalle de transacción
- **Confianza por fuente**: Diferentes niveles de confianza según la fuente de sugerencia

### 📈 Insights y Análisis
- **Dashboard principal**: KPIs de gastos y categorías más relevantes
- **Gráfico donut**: Distribución de gastos por categoría (centrado, sin recortes)
- **Análisis temporal**: Frecuencia por categoría, ticket promedio, gastos por día de semana
- **Comparación mensual**: Compara gastos del mes actual vs anterior por categoría
- **Tendencias**: Evolución de gastos a lo largo del tiempo

### ✏️ Edición y Gestión
- **Tabla editable**: Edita montos, categorías y notas directamente en la interfaz
- **Filtros avanzados**: Búsqueda por texto, filtros por mes y rango de fechas
- **Gestión de categorías**: Agrega, elimina y renombra categorías con persistencia
- **Exportación**: Descarga CSV enriquecido con todas las categorías y notas

### 🔧 Herramientas de Mantenimiento
- **Reparación de montos**: Sincroniza montos discrepantes automáticamente
- **Gestión de ignorados**: Lista y restaura transacciones marcadas como ignoradas
- **Compatibilidad CSV**: Reimporta CSVs exportados por la app sin problemas

## 🛠️ Stack Técnico

- **Frontend**: Streamlit 1.37.x
- **Backend**: Python 3.11.x
- **Base de datos**: SQLite (local) / PostgreSQL (producción)
- **ORM**: SQLAlchemy 2.0.x
- **Análisis de datos**: Pandas 2.2.x, NumPy 2.x
- **Visualización**: Altair 5.x
- **Despliegue**: Render (plan gratuito)

## 📁 Estructura del Proyecto

```
Dashboard de Facto$/
├── app.py                 # Aplicación principal Streamlit
├── db.py                  # Módulo de base de datos
├── init_db.py            # Script de inicialización de BD
├── config_local.py       # Configuración local
├── requirements.txt      # Dependencias Python
├── render.yaml           # Configuración de despliegue
├── runtime.txt           # Versión de Python
├── DEPLOYMENT.md         # Guía de despliegue detallada
├── env.example           # Variables de entorno de ejemplo
├── data/                 # Base de datos local (SQLite)
│   ├── gastos.db
│   ├── gastos.db-shm
│   └── gastos.db-wal
├── prep.py               # Estandarización de CSV (legacy)
├── update_master.py      # Actualización de master (legacy)
├── merchant_map.json     # Mapeo de comercios (legacy)
└── config.json           # Configuración (legacy)
```

## 🚀 Inicio Rápido

### 1. Clonar y preparar
```bash
git clone <tu-repositorio>
cd "Dashboard de Facto$"
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# o .venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Inicializar base de datos
```bash
python init_db.py
```

### 3. Ejecutar aplicación
```bash
streamlit run app.py
```

La aplicación estará disponible en: http://localhost:8501

## 📊 Formato de Datos de Entrada

### Columnas mínimas requeridas:
- `fecha`: Fecha de la transacción
- `detalle`: Descripción de la transacción
- `monto`: Monto de la transacción

### Columnas opcionales:
- `id`: Identificador único (se genera si no existe)
- `tipo`: "Gasto" o "Abono" (se infiere del signo si no existe)
- `categoria`: Categoría de la transacción
- `nota_usuario`: Notas personalizadas

### Procesamiento automático:
- **Limpieza de montos**: Remueve símbolos ($, CLP), convierte comas decimales
- **Normalización**: Quita tildes, convierte a mayúsculas, colapsa espacios
- **Deduplicación**: Genera claves únicas para evitar duplicados
- **Reparación**: Actualiza montos nulos/cero con valores válidos del CSV

## 🎯 Casos de Uso

### Usuario Nuevo
1. Sube su primera cartola bancaria
2. La app estandariza y categoriza automáticamente
3. Revisa y ajusta categorías según sus preferencias
4. La app aprende de sus ajustes para futuras cargas

### Usuario Recurrente
1. Sube nuevas cartolas mensualmente
2. Las categorías se asignan automáticamente basándose en el historial
3. Revisa sugerencias de alta confianza
4. Exporta CSV enriquecido para archivo personal

### Gestión de Categorías
1. Agrega nuevas categorías según sus necesidades
2. Renombra categorías existentes (se propaga automáticamente)
3. Elimina categorías no utilizadas
4. Todas las operaciones se persisten en la base de datos

## 🌐 Despliegue en Producción

### Render (Recomendado para plan gratuito)
- **Web Service**: Automático con GitHub
- **Base de datos**: PostgreSQL incluido
- **Persistencia**: Datos se mantienen entre redeploys
- **Costos**: Completamente gratuito

Ver [DEPLOYMENT.md](DEPLOYMENT.md) para instrucciones detalladas.

### Otros proveedores
- **Heroku**: Soporte completo
- **Railway**: Soporte completo
- **DigitalOcean**: Requiere configuración manual de BD

## 🔒 Seguridad y Privacidad

- **Datos locales**: En desarrollo, todos los datos se mantienen en tu máquina
- **Sin tracking**: No se recopilan datos de uso
- **Control total**: Tú controlas dónde se almacenan tus datos financieros
- **Sin dependencias externas**: Funciona completamente offline en modo local

## 🤝 Contribuciones

### Reportar bugs
1. Abre un issue en GitHub
2. Describe el problema con pasos para reproducirlo
3. Incluye información del sistema y versión

### Sugerir mejoras
1. Abre un issue con la etiqueta "enhancement"
2. Describe la funcionalidad deseada
3. Explica el beneficio para los usuarios

### Contribuir código
1. Fork del repositorio
2. Crea una rama para tu feature
3. Envía un pull request con descripción clara

## 📝 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo LICENSE para más detalles.

## 🙏 Agradecimientos

- **Streamlit**: Por la excelente plataforma de desarrollo
- **Pandas/NumPy**: Por las herramientas de análisis de datos
- **Altair**: Por la visualización de datos hermosa y declarativa
- **SQLAlchemy**: Por el ORM robusto y flexible

## 📞 Soporte

- **Documentación**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **Issues**: GitHub Issues
- **Discusiones**: GitHub Discussions

---

**Dashboard de Facto$** - Transformando la gestión de finanzas personales con tecnología moderna y UX intuitiva. 💰📊✨
