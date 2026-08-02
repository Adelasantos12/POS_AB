# PRD - ByEasy POS System
**Última actualización:** 2026-01-25
**Tienda:** Adelé Boutique (Gdl)

## Problem Statement Original
Sistema POS completo para boutique de novias con: catálogo de colores/telas con muestras visuales, agenda estilo iPhone Calendar, sistema de novias con grupos de damas, pedidos con seguimiento de estados, y resumen nocturno para el día siguiente.

## Arquitectura
- **Backend:** Django 5.1.4 con SQLite (adaptable a PostgreSQL)
- **Frontend:** Templates Django con Bootstrap 5, estilo minimalista tipo PayPal
- **IA:** Gemini 2.0 Flash para detección de duplicados y validación de colores/telas
- **Impresora:** Brother QL-800 USB para etiquetas

## Usuarios del Sistema

| Usuario | Email | Rol | Contraseña |
|---------|-------|-----|------------|
| Superadmin | adela.santos12@gmail.com | Admin, Superadmin | Karinakakapopo1 |
| CEO Tienda | adeleboutiquegdl@gmail.com | CEO, Admin, Caja, Inventario, Agenda | Karinakakapopo2 |
| Vendedora | vendedora1@adeleboutique.com | Caja, Vendedor | vendedora123 |

## What's Been Implemented ✅

### 2026-01-25 - v1.0 MVP
1. **Sistema de Perfiles (macOS style)**
2. **Detección de Duplicados con IA (Gemini)**
3. **Integración Impresora Brother QL-800**

### 2026-01-25 - v1.1 Catálogos y Agenda
4. **Catálogo de Colores** (39 colores predefinidos)
   - Organizados por familia: Rosa (Palo, Mauve, Blush...), Azul, Verde, etc.
   - Muestras visuales con código hex
   - Botón "Nuevo Color" con validación IA de similitud
   
5. **Catálogo de Telas** (20 tipos predefinidos)
   - Satín, Encaje Chantilly, Tul, Crepe, etc.
   - Descripción de cada tela
   - Código de proveedor
   - Agregar nueva con validación IA

6. **Agenda Calendario (estilo iPhone)**
   - Vista mensual con navegación año/mes
   - Vista por día con desglose por horas (9am-8pm)
   - Tipos de cita: Consulta, Prueba, Ajustes, Entrega, Recogida
   - Leyenda de colores por tipo

7. **Sistema de Novias** (PARCIAL)
   - Modelo Novia con fechas: boda, prueba, entrega, límite
   - Modelo Dama (grupo de la novia)
   - Cada dama puede tener color/tela/modelo diferente

8. **Pedidos en Puerta** (PARCIAL)
   - Estados: Nuevo, Pendiente Tela, En Confección, Listo, Entregado
   - Estados de pago: Sin pago, Apartado, Parcial, Liquidado

9. **Resumen Nocturno**
   - Citas de mañana
   - Resto de la semana
   - Imprimir y Compartir (AirDrop)

## Backlog - Pendiente para Completar

### P0 (En esta sesión)
- [ ] Template de lista de Novias
- [ ] Template de detalle de Novia con grupo
- [ ] Template de Pedidos en Puerta
- [ ] Crear nuevo pedido desde cita/novia
- [ ] Búsqueda por ticket/nombre novia/fecha boda

### P1 (Próxima sesión)
- [ ] Integración PayPal
- [ ] Impresora térmica tickets
- [ ] Agregar imagen a modelo de vestido

## Credenciales
- **Superadmin:** adela.santos12@gmail.com / Karinakakapopo1
- **CEO:** adeleboutiquegdl@gmail.com / Karinakakapopo2
- **Gemini API:** Configurada en .env
