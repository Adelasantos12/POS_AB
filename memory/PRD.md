# PRD - ByEasy POS System
**Última actualización:** 2026-01-25
**Tienda:** Adelé Boutique (Gdl)

## Problem Statement Original
Sistema POS completo para boutique con gestión de usuarios basada en perfiles (estilo macOS), caja desacoplada del usuario, inventario basado en movimientos (no edición directa), auditoría centralizada, y reportes exportables. El sistema debe ser simple: el usuario solo elige, confirma y cobra. Una pantalla = una acción principal.

## Arquitectura
- **Backend:** Django 5.1.4 con SQLite (adaptable a PostgreSQL)
- **Frontend:** Templates Django con Bootstrap 5, estilo minimalista tipo PayPal
- **IA:** Gemini 2.0 Flash para detección de duplicados y estrategias
- **Impresora:** Brother QL-800 USB para etiquetas

## Usuarios del Sistema

| Usuario | Email | Rol | Contraseña |
|---------|-------|-----|------------|
| Superadmin | adela.santos12@gmail.com | Admin, Superadmin | Karinakakapopo1 |
| CEO Tienda | adeleboutiquegdl@gmail.com | CEO, Admin, Caja, Inventario, Agenda | Karinakakapopo2 |
| Vendedora | vendedora1@adeleboutique.com | Caja, Vendedor | vendedora123 |

## Roles del Sistema
| Rol | Permisos |
|-----|----------|
| Superadmin | Acceso total + crear usuarios |
| CEO | Acceso total (igual que Admin) |
| Admin | Todo excepto ver_todo |
| Caja | abrir_caja, vender, cobrar |
| Vendedor | vender, cobrar |
| Inventario | editar_inventario |

## What's Been Implemented ✅

### 2026-01-25 - MVP v1.0
1. **Branding ByEasy POS**
   - Logo "ByEasy - Tu punto de venta fácil"
   - Badge "Adelé Boutique (Gdl)" visible en toda la app
   - Estilo minimalista tipo PayPal

2. **Sistema de Perfiles (macOS style)**
   - Login de terminal (Django Auth)
   - Selección de perfil con avatares coloridos
   - Autenticación de perfil con contraseña
   - Indicador visual "Trabajando como: [nombre] - [rol]"

3. **Detección de Duplicados con IA (Gemini)**
   - Verifica productos similares al crear uno nuevo
   - Diferencia tonos de color (Rosa Palo ≠ Rosa Mauve)
   - Análisis de IA con recomendaciones
   - Bloquea duplicados exactos
   - Checkbox para confirmar "es producto diferente"

4. **Integración Impresora Brother QL-800**
   - Servicio de impresión de etiquetas USB
   - Verificar estado de impresora desde POS
   - Imprimir etiquetas individuales o en lote
   - Preview de etiqueta antes de imprimir

5. **Panel de Gestión de Usuarios**
   - Solo Superadmin y CEO pueden crear usuarios
   - Roles múltiples por usuario
   - Permisos en lenguaje humano

6. **Exportación de Reportes**
   - Inventario: CSV y Excel (.xlsx)
   - Ventas: CSV y PDF

## Backlog - Next Features

### P0 (Critical)
- [ ] Integración PayPal para pagos
- [ ] Impresora térmica de tickets

### P1 (High)
- [ ] Cierre de caja con cuadre de efectivo
- [ ] Impresión de ticket de venta

### P2 (Medium)
- [ ] Agenda de grupos/pedidos
- [ ] Clientes con historial
- [ ] Multi-tienda

## Credenciales de Producción
- **Superadmin:** adela.santos12@gmail.com / Karinakakapopo1
- **CEO:** adeleboutiquegdl@gmail.com / Karinakakapopo2
- **Gemini API:** Configurada en .env
