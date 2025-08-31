#!/usr/bin/env python3
"""
Configuración local para desarrollo de Facto$
"""

import os
from pathlib import Path

# Configuración de la aplicación
APP_NAME = "Dashboard de Facto$"
APP_VERSION = "1.0.0"

# Configuración de la base de datos
DB_PATH_DEFAULT = os.path.join("data", "gastos.db")

# Configuración de Streamlit
STREAMLIT_CONFIG = {
    "browser.gatherUsageStats": False,
    "server.port": 8501,
    "server.address": "localhost",
    "theme.primaryColor": "#133c60",
    "theme.backgroundColor": "#ffffff",
    "theme.secondaryBackgroundColor": "#f0f5fa",
    "theme.textColor": "#262730",
}

# Categorías por defecto
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

# Configuración de archivos
SUPPORTED_CSV_COLUMNS = {
    "required": {"fecha", "detalle", "monto"},
    "optional": {
        "id", "detalle_norm", "categoria", "nota_usuario", 
        "monto_real", "tipo", "es_gasto", "es_transferencia_o_abono"
    }
}

# Configuración de gráficos
CHART_CONFIG = {
    "donut": {
        "innerRadius": 70,
        "outerRadius": 130,
        "cornerRadius": 2,
        "padAngle": 0.01,
        "width": 380,
        "height": 320
    },
    "colors": [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
        "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
        "#edc949", "#af7aa1", "#ff9da7", "#9c755f", "#bab0ab",
    ]
}

# Configuración de sugerencias
SUGGESTION_CONFIG = {
    "confidence_thresholds": {
        "exact_match": 1.0,
        "historical_dominant": 0.8,
        "rules_based": 0.7,
        "min_acceptable": 0.9
    },
    "historical_threshold": 70.0  # Porcentaje mínimo para considerar dominante
}
