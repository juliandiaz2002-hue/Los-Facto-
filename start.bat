@echo off
echo 🚀 Iniciando Dashboard de Facto$...

REM Verificar si existe entorno virtual
if not exist ".venv" (
    echo 📦 Creando entorno virtual...
    python -m venv .venv
)

REM Activar entorno virtual
echo 🔧 Activando entorno virtual...
call .venv\Scripts\activate.bat

REM Instalar dependencias
echo 📚 Instalando dependencias...
pip install -r requirements.txt

REM Inicializar base de datos
echo 🗄️ Inicializando base de datos...
python init_db.py

REM Ejecutar aplicación
echo 🌐 Iniciando aplicación...
streamlit run app.py

pause
