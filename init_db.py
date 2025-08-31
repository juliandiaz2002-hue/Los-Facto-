#!/usr/bin/env python3
"""
Script de inicialización de la base de datos para Facto$
"""

import os
import sys
from pathlib import Path

# Agregar el directorio actual al path para importar db
sys.path.insert(0, str(Path(__file__).parent))

from db import get_conn, init_db, replace_categories

DEFAULT_CATEGORIES = [
    "Sin categoría",
    "Alimentación",
    "Tabaco",
    "Transporte",
    "Vivienda",
    "Servicios",
    "Salud",
    "Educación",
    "Compras",
    "Ocio",
    "Viajes",
    "Bancos/Comisiones",
    "Mascotas",
    "Hogar",
    "Suscripciones",
    "Impuestos",
    "Ahorro/Inversión",
    "Transferencias",
    "Ingresos",
    "Otros",
]

def main():
    print("🚀 Inicializando base de datos de Facto$...")
    
    # Obtener conexión (autodetecta Postgres vs SQLite)
    conn = get_conn()
    
    if isinstance(conn, dict) and conn.get("pg"):
        print("📊 Usando base de datos Postgres")
        db_type = "Postgres"
    else:
        print("💾 Usando base de datos SQLite local")
        db_type = "SQLite"
    
    # Inicializar tablas
    print("🔧 Creando tablas...")
    init_db(conn)
    print("✅ Tablas creadas correctamente")
    
    # Sembrar categorías por defecto
    print("🌱 Sembrando categorías por defecto...")
    replace_categories(conn, DEFAULT_CATEGORIES)
    print(f"✅ {len(DEFAULT_CATEGORIES)} categorías sembradas")
    
    print(f"\n🎉 Base de datos {db_type} inicializada correctamente!")
    print("Puedes ejecutar 'streamlit run app.py' para iniciar la aplicación")

if __name__ == "__main__":
    main()
