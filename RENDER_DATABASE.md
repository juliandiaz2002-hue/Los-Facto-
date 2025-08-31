# 🗄️ Base de Datos en Render - Dashboard de Facto$

## 🌐 **¿Dónde se Guardan los Datos en Render?**

### **Respuesta Corta: SÍ, todos los datos se guardan permanentemente** ✅

Cuando usas la aplicación en `los-facto.onrender.com`, **TODAS** las transacciones, categorías y configuraciones se guardan en una base de datos PostgreSQL que Render proporciona gratuitamente.

## 🏗️ **Arquitectura de la Base de Datos en Render**

### **1. Servicio Web (Tu App)**
- **URL**: `los-facto.onrender.com`
- **Tipo**: Web Service Python
- **Plan**: Gratuito
- **Estado**: Se "duerme" después de 15 minutos de inactividad

### **2. Base de Datos PostgreSQL**
- **Tipo**: PostgreSQL Database
- **Plan**: Gratuito
- **Almacenamiento**: Hasta 1GB
- **Estado**: **SIEMPRE ACTIVA** (no se duerme)
- **Persistencia**: **PERMANENTE**

## 📊 **¿Qué Pasa con Mis Datos?**

### **✅ Datos que SE MANTIENEN:**
- **Transacciones**: Todas las cartolas que subas
- **Categorías**: Categorías personalizadas que crees
- **Mapeos**: Reglas aprendidas de categorización
- **Configuraciones**: Cambios en la tabla editable
- **Notas**: Comentarios que agregues a transacciones

### **❌ Datos que NO se mantienen:**
- **Archivos temporales**: Solo se procesan, no se almacenan
- **Sesiones del navegador**: Se reinician al "despertar" el servicio

## 🔄 **Flujo de Datos en Render**

```
1. Usuario sube CSV → 2. App procesa → 3. Guarda en PostgreSQL → 4. Muestra resultados
                                    ↓
                            Los datos quedan PERMANENTES
```

### **Ejemplo Práctico:**
1. **Subes** `movimientos_enriquecidos.csv` con 34 transacciones
2. **App detecta** que ya existen (por eso dice "ignoradas por duplicado: 34")
3. **Los datos originales** siguen en la base de datos
4. **Puedes editar** categorías, montos y notas
5. **Todo se guarda** en PostgreSQL automáticamente

## 🛡️ **Seguridad y Privacidad**

### **¿Quién puede ver mis datos?**
- **Solo tú**: La base de datos es privada para tu aplicación
- **Render**: Solo ve metadatos técnicos (no contenido)
- **No hay acceso público** a tus datos financieros

### **¿Dónde están físicamente?**
- **Servidores de Render** (generalmente en Estados Unidos)
- **Cumplen GDPR** y regulaciones de privacidad
- **Backups automáticos** (en planes de pago)

## 💾 **Persistencia de Datos**

### **Escenarios de Persistencia:**

#### **✅ Datos SE MANTIENEN:**
- **Servicio se "duerme"** → Datos intactos
- **Redeploy automático** → Datos intactos
- **Actualización de código** → Datos intactos
- **Reinicio del servidor** → Datos intactos

#### **⚠️ Datos se PIERDEN (solo en casos extremos):**
- **Plan gratuito inactivo 90 días** → Base de datos se elimina
- **Cambio de plan** → Requiere migración manual
- **Eliminación manual** → Acción del usuario

## 🔧 **Configuración Técnica**

### **Variables de Entorno en Render:**
```bash
DATABASE_URL=postgresql://usuario:password@host:puerto/nombre_db
PYTHON_VERSION=3.11.9
PYTHONUNBUFFERED=1
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
```

### **Conexión Automática:**
- La app detecta `DATABASE_URL` automáticamente
- Se conecta a PostgreSQL en lugar de SQLite
- **No necesitas configurar nada manualmente**

## 📈 **Ventajas de PostgreSQL en Render**

### **1. Persistencia Total**
- Datos sobreviven a cualquier reinicio
- No hay pérdida de información

### **2. Escalabilidad**
- Soporta miles de transacciones
- Consultas rápidas incluso con mucho volumen

### **3. Confiabilidad**
- Base de datos empresarial
- Transacciones ACID
- Integridad de datos garantizada

### **4. Gratis**
- Plan gratuito incluye 1GB de almacenamiento
- Suficiente para años de datos financieros

## 🚨 **Limitaciones del Plan Gratuito**

### **Almacenamiento:**
- **Máximo**: 1GB de datos
- **Típico**: ~100,000 transacciones
- **Duración**: Hasta 90 días de inactividad

### **Performance:**
- **Primera carga**: Puede tardar hasta 1 minuto
- **Consultas**: Rápidas una vez "despierto"
- **Concurrentes**: Limitado a 1 usuario a la vez

## 🔍 **Verificar que los Datos se Guardan**

### **1. Sube un CSV y verifica:**
- Deberías ver el mensaje "Ingeridos: X nuevas filas"
- Los datos aparecen en la tabla editable
- Los gráficos se actualizan

### **2. Edita una categoría:**
- Cambia una categoría en la tabla
- Haz clic en "Guardar cambios en la base"
- Recarga la página → El cambio persiste

### **3. Agrega una nueva categoría:**
- Ve a "Gestionar categorías" en el sidebar
- Agrega una nueva categoría
- Recarga → La categoría persiste

## 🚀 **Recomendaciones para Uso en Producción**

### **1. Uso Regular:**
- **Sube datos mensualmente** para mantener la app activa
- **Edita categorías** según tus necesidades
- **Exporta CSV** periódicamente como backup

### **2. Monitoreo:**
- Revisa el dashboard de Render regularmente
- Verifica que la base de datos esté activa
- Monitorea el uso de almacenamiento

### **3. Backup (Opcional):**
- **Plan gratuito**: Exporta CSV mensualmente
- **Plan de pago**: Backups automáticos incluidos

## ❓ **Preguntas Frecuentes**

### **Q: ¿Mis datos se pierden si no uso la app?**
**A**: Solo después de 90 días de inactividad total. El uso mensual es suficiente.

### **Q: ¿Puedo acceder a mis datos desde otro lugar?**
**A**: Sí, desde cualquier navegador en `los-facto.onrender.com`

### **Q: ¿Qué pasa si Render cierra?**
**A**: Es muy improbable, pero siempre exporta CSV como backup.

### **Q: ¿Puedo migrar a otro proveedor?**
**A**: Sí, puedes exportar todos los datos y migrar a otro servicio.

## 🎯 **Conclusión**

**En Render, tus datos están 100% seguros y persistentes:**

✅ **Se guardan automáticamente** en PostgreSQL  
✅ **Sobreviven a reinicios** y redeploys  
✅ **Son privados** y solo tuyos  
✅ **Son accesibles** desde cualquier lugar  
✅ **Son permanentes** mientras uses la app  

**¡Puedes usar la aplicación con total confianza de que tus datos financieros están seguros!** 🛡️💰
