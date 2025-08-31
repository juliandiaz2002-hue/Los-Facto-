#!/usr/bin/env python3
"""
Script de prueba para verificar que la aplicación Facto$ funcione correctamente
"""

import sys
from pathlib import Path

# Agregar el directorio actual al path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Prueba que todas las importaciones funcionen"""
    print("🧪 Probando importaciones...")
    
    try:
        import streamlit as st
        print(f"✅ Streamlit {st.__version__}")
    except ImportError as e:
        print(f"❌ Error importando Streamlit: {e}")
        return False
    
    try:
        import pandas as pd
        print(f"✅ Pandas {pd.__version__}")
    except ImportError as e:
        print(f"❌ Error importando Pandas: {e}")
        return False
    
    try:
        import numpy as np
        print(f"✅ NumPy {np.__version__}")
    except ImportError as e:
        print(f"❌ Error importando NumPy: {e}")
        return False
    
    try:
        import altair as alt
        print(f"✅ Altair {alt.__version__}")
    except ImportError as e:
        print(f"❌ Error importando Altair: {e}")
        return False
    
    try:
        from db import get_conn, init_db, get_categories
        print("✅ Módulo db importado correctamente")
    except ImportError as e:
        print(f"❌ Error importando módulo db: {e}")
        return False
    
    return True

def test_database():
    """Prueba la funcionalidad de la base de datos"""
    print("\n🗄️ Probando base de datos...")
    
    try:
        from db import get_conn, init_db, get_categories, replace_categories
        
        # Obtener conexión
        conn = get_conn()
        print("✅ Conexión a base de datos establecida")
        
        # Inicializar base de datos
        init_db(conn)
        print("✅ Base de datos inicializada")
        
        # Probar categorías
        categories = get_categories(conn)
        if categories:
            print(f"✅ Categorías cargadas: {len(categories)} encontradas")
        else:
            print("⚠️ No hay categorías, sembrando categorías por defecto...")
            from config_local import DEFAULT_CATEGORIES
            replace_categories(conn, DEFAULT_CATEGORIES)
            categories = get_categories(conn)
            print(f"✅ Categorías sembradas: {len(categories)} creadas")
        
        return True
        
    except Exception as e:
        print(f"❌ Error en base de datos: {e}")
        return False

def test_streamlit_config():
    """Prueba la configuración de Streamlit"""
    print("\n⚙️ Probando configuración de Streamlit...")
    
    config_path = Path(".streamlit/config.toml")
    if config_path.exists():
        print("✅ Archivo de configuración .streamlit/config.toml encontrado")
        return True
    else:
        print("❌ Archivo de configuración .streamlit/config.toml no encontrado")
        return False

def test_requirements():
    """Prueba que requirements.txt exista"""
    print("\n📦 Probando archivos de dependencias...")
    
    req_path = Path("requirements.txt")
    if req_path.exists():
        print("✅ requirements.txt encontrado")
        return True
    else:
        print("❌ requirements.txt no encontrado")
        return False

def main():
    """Función principal de pruebas"""
    print("🚀 Iniciando pruebas del Dashboard de Facto$...\n")
    
    tests = [
        ("Importaciones", test_imports),
        ("Base de datos", test_database),
        ("Configuración Streamlit", test_streamlit_config),
        ("Dependencias", test_requirements),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Error en prueba '{test_name}': {e}")
            results.append((test_name, False))
    
    # Resumen de resultados
    print("\n" + "="*50)
    print("📊 RESUMEN DE PRUEBAS")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASÓ" if result else "❌ FALLÓ"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nResultado: {passed}/{total} pruebas pasaron")
    
    if passed == total:
        print("\n🎉 ¡Todas las pruebas pasaron! La aplicación está lista para usar.")
        print("\nPara ejecutar la aplicación:")
        print("1. streamlit run app.py")
        print("2. Abre http://localhost:8501 en tu navegador")
    else:
        print(f"\n⚠️ {total - passed} prueba(s) fallaron. Revisa los errores arriba.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
