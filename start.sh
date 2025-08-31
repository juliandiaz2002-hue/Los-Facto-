#!/bin/bash

echo "🚀 Iniciando Dashboard de Facto$..."

# Verificar si existe entorno virtual
if [ ! -d ".venv" ]; then
    echo "📦 Creando entorno virtual..."
    python3 -m venv .venv
fi

# Activar entorno virtual
echo "🔧 Activando entorno virtual..."
source .venv/bin/activate

# Instalar dependencias
echo "📚 Instalando dependencias..."
pip install -r requirements.txt

# Inicializar base de datos
echo "🗄️ Inicializando base de datos..."
python init_db.py

# Ejecutar aplicación
echo "🌐 Iniciando aplicación..."
streamlit run app.py
