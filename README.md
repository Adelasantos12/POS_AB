# Adelé Boutique POS

Sistema de Punto de Venta e Inventario para Adelé Boutique.

## Despliegue en Railway

### Variables de Entorno (Environment Variables)
- `DJANGO_SECRET_KEY`: Una clave secreta larga y aleatoria.
- `ENVIRONMENT`: Establecer a `production` para desactivar DEBUG.
- `DJANGO_ALLOWED_HOSTS`: Dominios permitidos (ej: `adele-pos.up.railway.app`).
- `DATABASE_URL`: URL de la base de datos PostgreSQL (proporcionada por Railway).
- `DB_SSL_REQUIRE`: `True` para conexiones seguras.
- `GEMINI_API_KEY`: API Key para funciones de IA (opcional).

### Pasos de Deploy
1. El sistema usa `start.sh` para:
   - Ejecutar migraciones automáticamente.
   - Configurar roles y permisos iniciales.
   - Recopilar archivos estáticos.
   - Iniciar el servidor Gunicorn.
2. Railway detectará el `Procfile` y ejecutará `./start.sh`.

## Desarrollo Local

1. Instalar dependencias: `pip install -r requirements.txt`
2. Configurar base de datos: `python manage.py migrate`
3. Crear superusuario: `python manage.py createsuperuser`
4. Ejecutar servidor: `python manage.py runserver`

## Carga Masiva (Excel)

Para poblar catálogos iniciales, accede a **Dashboard > Carga Masiva**.
- **Modelos:** Columnas `[Modelo, Descripción, Precio]`.
- **Telas:** Columnas `[Tela, Proveedor, Notas]`.

El sistema es inteligente e identifica si el registro ya existe para actualizarlo o crearlo.

## Estrategia Offline

El POS cuenta con un modo offline que permite:
1. Seguir vendiendo sin conexión a internet.
2. Las ventas se guardan en el navegador (`localStorage`).
3. Al recuperar la conexión, aparece un botón de **Sincronizar** para enviar los datos al servidor.
4. Consulta `OFFLINE_STRATEGY.md` para más detalles técnicos.

## Apartados y Tickets

El sistema genera folios automáticos:
- **NV-XXXXX** para pedidos de Novias.
- **DM-XXXXX** para pedidos de Damas.

Puedes realizar apartados desde el POS activando el switch "Es un Apartado" o desde la sección de Novias. Los saldos se actualizan automáticamente al registrar pagos parciales.
