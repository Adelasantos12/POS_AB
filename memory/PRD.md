# PRD - Adelé POS System
**Última actualización:** 2026-01-25

## Problem Statement Original
Sistema POS completo para boutique con gestión de usuarios basada en perfiles (estilo macOS), caja desacoplada del usuario, inventario basado en movimientos (no edición directa), auditoría centralizada, y reportes exportables. El sistema debe ser simple: el usuario solo elige, confirma y cobra. Una pantalla = una acción principal.

## Arquitectura
- **Backend:** Django 5.1.4 con PostgreSQL (SQLite en desarrollo)
- **Frontend:** Templates Django con Bootstrap 5, estilo minimalista tipo PayPal
- **Sesiones:** Django Sessions con perfil activo almacenado en sesión

## User Personas
1. **Cajera/Vendedora** - Opera la caja, registra ventas, no necesita pensar
2. **Admin de Tienda** - Gestiona usuarios, ve reportes, configura roles
3. **Superadmin** - Acceso total, múltiples tiendas

## Roles del Sistema
| Rol | Permisos |
|-----|----------|
| Caja | abrir_caja, vender, cobrar |
| Vendedor | vender, cobrar |
| Inventario | editar_inventario |
| Agenda | gestionar_agenda |
| Admin | todos menos ver_todo |
| Superadmin | ver_todo |

## What's Been Implemented ✅

### 2026-01-25 - MVP v1.0
1. **Sistema de Perfiles (estilo macOS)**
   - Login de terminal (Django Auth)
   - Selección de perfil con avatares coloridos
   - Autenticación de perfil con contraseña
   - Indicador visual "Trabajando como: [nombre] - [rol]"
   - Cambiar perfil sin cerrar terminal

2. **Panel de Gestión de Usuarios**
   - Lista con: nombre, roles (chips), permisos (lenguaje humano), estado, último acceso
   - Editar usuario: toggle activar/desactivar, checkboxes de roles
   - Resetear contraseña (sin mostrarla)
   - Ver historial de acciones

3. **Modelo de Caja Desacoplada**
   - Caja pertenece a Tienda + Fecha
   - Registra quién abrió y operó
   - Bloqueo: no vender sin caja abierta
   - Apertura con monto inicial

4. **Sistema de Inventario con Movimientos**
   - Modelo MovimientoInventario (ENTRADA, SALIDA, AJUSTE, VENTA, DEVOLUCION)
   - Stock es resultado de movimientos, no edición directa
   - Niveles visuales: Agotado, Bajo, Normal, Alto

5. **Auditoría Centralizada**
   - Helper único `registrar_auditoria()`
   - Acciones: LOGIN_PERFIL, LOGOUT, APERTURA_CAJA, CIERRE_CAJA, VENTA, etc.
   - Registro de IP, entidad afectada, timestamp

6. **Exportación de Reportes**
   - Inventario CSV
   - Inventario Excel (.xlsx con formato)
   - Ventas PDF

7. **UI/UX PayPal Style**
   - Tema claro minimalista
   - Tipografía: IBM Plex Sans + Manrope
   - Botones pill-shaped
   - Sidebar con navegación
   - Cards con bordes suaves

## Backlog - Next Features

### P0 (Critical)
- [ ] Integración PayPal para pagos
- [ ] Impresora térmica de tickets
- [ ] Impresora Brother para etiquetas

### P1 (High)
- [ ] Módulo de IA para análisis de ventas (usuario eligió hacer pruebas con IA)
- [ ] Cierre de caja con cuadre de efectivo
- [ ] Dashboard con gráficos interactivos

### P2 (Medium)
- [ ] Agenda de grupos/pedidos
- [ ] Clientes con historial
- [ ] Notificaciones de stock bajo

### P3 (Low)
- [ ] Multi-tienda con selector
- [ ] Devoluciones y garantías
- [ ] App móvil (PWA)

## API Mocked
- `api_ai_strategy` - Genera estrategia de ventas simulada basada en datos locales

## Credenciales de Prueba
| Usuario | Contraseña | Rol |
|---------|------------|-----|
| admin | admin123 | Admin |
| ana | caja123 | Caja, Vendedor |
| carlos | inv123 | Inventario |
