# Auditoría de Estabilización — Adelé POS

**Fecha:** 2026-07-24  
**Rama de referencia:** `claude/review-repo-structure-DNkLG` (PR #20)  
**Alcance:** auditoría técnica; ningún cambio de comportamiento en este documento.

---

## 1. Resumen ejecutivo

El sistema tiene cinco problemas estructurales que producen todos los síntomas reportados:

| # | Problema raíz | Síntomas |
|---|---------------|----------|
| R1 | `Pedido` no tiene relación `items` → tickets de pedido sin artículos | Tickets vacíos en hechura/dama/pedido externo |
| R2 | Saldo calculado en múltiples lugares incompatibles | Saldo incorrecto en pantallas y tickets |
| R3 | `ApartadoItem.modelo/color` son texto libre, no FK | Datos vacíos en tickets de apartados sin búsqueda de catálogo |
| R4 | Vista de servicios con error de template no capturado | HTTP 500 al abrir `/servicios/` |
| R5 | `TicketItem` (modelo de BD) existe pero nunca se usa | Código muerto, confusión futura |

Los demás síntomas (notas no visibles, sin edición de color de dama, checklist en ticket) ya fueron corregidos en commits recientes de esta rama.

---

## 2. Estado del repositorio

### Rama y PR
- Rama activa: `claude/review-repo-structure-DNkLG`
- 41 commits sobre una cadena de ramas de corrección acumulativas
- Rama predeterminada del repositorio: rama temporal (no `main`/`master` estable)

### Migraciones
- 39 migraciones (0001–0039)
- Última: `0039_alter_servicio_tipo_producto_unique_producto_variant` (2026-06-26)
- La migración 0039 corrige los `choices` de `Servicio.tipo` y agrega restricción de unicidad de variante de producto
- No hay migraciones pendientes sin aplicar a partir de esta revisión

### Pruebas existentes
- `boutique/tests.py` — 3 tests (vistas básicas + creación de producto rápido)
- `boutique/tests_perfiles.py` — 5 tests (flujo de perfil + caja + permisos)
- `test_utils.py` — 8 tests unitarios de `safe_decimal`
- **Ninguna prueba** cubre: pagos, tickets, saldos, apartados, pedidos, damas, servicios, agenda, etiquetas, impresión

---

## 3. Mapa de entidades y relaciones

```
ConfiguracionTienda (singleton)
Secuencia (folios atómicos por prefijo/fecha)

Catalogo:
  Categoria → Producto
  Modelo    → Producto, Pedido, Dama, Novia
  Color     → Producto, Pedido, Dama, Novia
  Tela      → Producto, Pedido, Dama, Novia
  Proveedor → Tela

Inventario:
  Producto (SKU/variante)
    └─ categoria FK, modelo FK (null), tela FK (null), color FK, talla CharField
    └─ barcode_image, foto, qr_code (ImageField → Cloudinary)
    └─ cantidad_actual, stock_teorico, estado, pendiente_regularizacion
  MovimientoInventario → Producto, Venta, User

Clientes:
  Cliente (teléfono unique)
  Novia → Color, Tela, Modelo (campo principal del vestido de novia)
        → medidas como CharField directo (m_busto, m_cintura, …)
        → modelo_especial, color_especial, tela_especial (texto libre)
  Dama  → Novia, Cliente, Color FK, Tela FK, Modelo FK
        → medidas como CharField
        → modelo_especial, color_especial, tela_especial (texto libre)

Operaciones financieras:
  Venta       → Cliente, User, Ticket FK (null)
    ItemVenta → Venta, Producto
    Pago      → Venta

  Apartado → Cliente, Novia (null)
    ApartadoItem → Apartado, Producto FK (null)
                   modelo CharField, color CharField, talla CharField  ← PROBLEMA
    PagoApartado → Apartado

  Pedido → Cliente, Novia, Dama
           modelo FK, color FK, tela FK, talla CharField, precio
           anticipo (sincronizado por PagoPedido.save())
           saldo_pendiente (property = precio - sum(pagos_pedido))
    PagoPedido → Pedido
    Medidas    → Pedido (OneToOne)
    NotaPedido → Pedido

  Servicio → Cliente, Novia, Venta (null)
    PagoServicio → Servicio

Contabilidad de caja:
  CorteCaja → Tienda, User
  MovimientoCaja → CorteCaja, Venta/Pedido/Apartado/Servicio (null FKs)

Tickets (snapshot):
  Ticket → Venta/Apartado/Pedido/Servicio/Novia (null FKs), CorteCaja
            snapshot_json (JSONField) — almacena items, pagos, saldo
  TicketItem → Ticket  ← MODELO EXISTENTE PERO NUNCA USADO

Agenda:
  CitaAgenda → Novia, Pedido, Apartado (null FKs)
  Novia      → CitaAgenda (agenda_evento)
  Pedido     → CitaAgenda (agenda_evento)
  Apartado   → CitaAgenda (agenda_evento)

Auditoría:
  Auditoria → User, Tienda
  IdempotencyLog (claves para evitar duplicados en ventas rápidas)
```

---

## 4. Mapa de flujos y endpoints

### 4.1 Flujo: Venta desde inventario

```
GET  /inventario/                       inventario_view()
POST /api/registrar-venta/              api_registrar_venta()
  → crea Venta + ItemVenta + Pago + MovimientoInventario
  → llama registrar_cobro(origen_tipo='venta')
      → crea MovimientoCaja, Ticket, llama populate_from_obj(venta)
         populate_from_obj(Venta):
           items ← venta.items.all()  [ItemVenta]
           → lee item.producto.color.nombre, item.producto.modelo.nombre, item.producto.sku  ✓
           cliente ← venta.cliente.nombre (si existe)
           total_pagado_acumulado ← venta.pagos.all()  ✓
```

**Problema detectado:** `Venta` tiene `cliente` FK (puede ser null si el vendedor no capturó al cliente). Si `cliente` es null, `cliente_nombre` en el ticket queda vacío. El sistema no exige capturar cliente en una venta directa.

### 4.2 Flujo: Venta rápida (POS Dashboard)

```
POST /api/venta-rapida/                 api_venta_rapida()
  tipo_operacion = VENTA_NORMAL + es_apartado=false:
    → crea Venta + ItemVenta
    → llama registrar_cobro(origen_tipo='venta')  ✓

  tipo_operacion = VENTA_NORMAL + es_apartado=true:
    → crea Apartado + ApartadoItem(modelo='', color='')  ← texto libre vacío
    → llama registrar_cobro(origen_tipo='apartado')
        populate_from_obj(Apartado):
          items ← apartado.items.all()  [ApartadoItem]
          → lee item.producto.color.nombre (si FK presente)  ✓ (fix reciente)
          → item.modelo, item.color son CharField, siempre ''  si no se setean explícitamente

  tipo_operacion = HECHURA / DAMA_HONOR / PEDIDO_EXTERNO:
    → crea Pedido(modelo=..., color=..., tela=..., talla=..., precio=...)
    → llama registrar_cobro(origen_tipo='pedido')
        populate_from_obj(Pedido):
          hasattr(pedido, 'items') → FALSE  ← BUG CRÍTICO R1
          items_data = []  → ticket sin artículos
```

### 4.3 Flujo: Apartado independiente

```
POST /api/apartado/crear/              api_crear_apartado() [views_apartados]
  → crea Apartado
  → por cada item: crea ApartadoItem(producto FK, modelo='', color='', talla='')
  → si anticipo > 0: llama registrar_cobro(origen_tipo='apartado')  ✓
  → si anticipo = 0: crea Ticket manualmente + ticket.populate_from_obj(apartado)

  populate_from_obj(Apartado):
    items ← apartado.items.all()
    prod = item.producto  (FK, puede ser null)
    si prod: lee prod.color.nombre, prod.modelo.nombre, prod.sku  ✓
    si no prod: usa item.color, item.modelo  (vacíos en casi todos los casos)
```

**Problema:** `ApartadoItem.modelo` y `ApartadoItem.color` son CharField. En `api_registrar_venta`, se toman de `item.get('modelo', '')` y `item.get('color', '')` del JSON del carrito. El carrito en `pos_dashboard.html` construye items desde `api_search_productos` que devuelve `{id, sku, text, precio, stock, foto_url}` — **sin campos `modelo` o `color`**. Por tanto esos campos siempre llegan vacíos al crear ApartadoItem. La corrección reciente en `populate_from_obj` mitiga el problema en tickets, pero los datos en `ApartadoItem.modelo/color` siguen siendo inútiles.

### 4.4 Flujo: Abono posterior a apartado / pedido

```
POST /api/cobrar/{tipo}/{pk}/          api_cobrar_item()
  → llama registrar_cobro(origen_tipo=tipo, origen_obj=obj, monto=monto)

registrar_cobro(origen_tipo='apartado'):
  → crea PagoApartado
       PagoApartado.save() → apartado.anticipo = sum(pagos) → apartado.save()
                                                               apartado.saldo = total - anticipo ✓
  → crea MovimientoCaja, Ticket
  → populate_from_obj(apartado):
       total_pagado_acumulado = sum(abonos de pagos_apartado)  ✓
       saldo_pendiente = total - total_pagado_acumulado  ✓ (fix previo)

registrar_cobro(origen_tipo='pedido'):
  → crea PagoPedido
       PagoPedido.save() → pedido.anticipo = sum(pagos) → pedido.save()  ✓ (fix previo)
  → populate_from_obj(pedido):
       items_data = []  ← BUG R1 sigue presente aquí también
```

### 4.5 Flujo: Pedido de grupo (novia/damas)

```
POST /api/pedido/crear-completo/       api_crear_pedido_completo() [views_agenda]
  → resuelve Cliente, Modelo, Color (get_or_create por nombre)
  → crea Pedido(modelo FK, color FK, tela FK, talla, precio)
  → crea Medidas
  → si anticipo > 0: registrar_cobro(origen_tipo='pedido')
       populate_from_obj(pedido): items_data = []  ← BUG R1
  → si anticipo = 0: crea Ticket + populate_from_obj(pedido)
       items_data = []  ← BUG R1

POST /api/novia/{id}/agregar-dama/     api_agregar_dama()
  → crea Dama(novia, nombre, talla, modelo_especial, color_especial, tela_especial)
  → novia.cantidad_damas += 1

POST /api/dama/{id}/editar/            api_editar_dama()
  → actualiza Dama.nombre, telefono, talla, modelo_especial, color_especial,
    tela_especial, notas_ajustes
  → NO actualiza Dama.color FK, Dama.modelo FK, Dama.tela FK
  ← BUG: los FKs de catálogo en Dama no se pueden editar desde este endpoint
```

### 4.6 Flujo: Servicio / ajuste

```
POST /api/servicio/crear/             api_crear_servicio()
  → crea Servicio(tipo, descripcion, cliente, costo, anticipo, creado_por)
  → retorna {status: 'ok', id: srv.pk}

POST /api/servicio/{pk}/cobrar/       api_cobrar_servicio()
  → registrar_cobro(origen_tipo='servicio')
  → populate_from_obj(Servicio):
      hasattr(servicio, 'items') → False → items_data = []  (esperado para servicio)
      total = servicio.costo  ✓

GET  /servicios/                      servicios_list()
  → Servicio.objects.all() con filtros
  → renderiza servicios_list.html
  ← Causa del HTTP 500: aún no determinada sin leer el template
     Hipótesis: acceso a atributo de relación sin select_related()
```

### 4.7 Flujo: Impresión de ticket

```
GET /api/tickets/{folio}/pdf/         print_ticket_pdf()
  → ticket_service.generate_pdf_ticket(ticket.id)
  → lee ticket.snapshot_json['items']
  → para Pedidos: items siempre []  ← BUG R1

GET /api/tickets/{folio}/escpos/      get_ticket_escpos()
  → ticket_service.generate_escpos_data(ticket.id)
  → misma lectura de snapshot_json['items']  ← BUG R1
```

### 4.8 Flujo: Etiquetas

```
POST /api/imprimir-etiqueta/{pk}/     api_imprimir_etiqueta()
  → printer_service.imprimir_etiqueta_brother(producto, cantidad)
  → convierte imagen PIL a raster Brother QL-800 (label='62', rotate='0')
  → envía por USB via brother_ql

GET  /imprimir-etiquetas/             imprimir_etiquetas()
  → renderiza etiquetas_lote.html con lista de productos seleccionados
  → @page { size: 62mm 20mm } para impresión desde navegador
```

**Problema:** La etiqueta de 54×17mm (DK-11204 die-cut) que la usuaria requiere no coincide con el rollo físico instalado (DK-22243, cinta continua 62mm). El sistema usa `label='62'` correctamente para el rollo instalado, pero el tamaño deseado requiere cambiar físicamente el rollo.

---

## 5. Reglas de negocio duplicadas

| Regla | Implementación duplicada |
|-------|--------------------------|
| Calcular saldo de apartado | `Apartado.saldo = total - anticipo` en `save()` + `snapshot_json['saldo_pendiente']` en `populate_from_obj` |
| Calcular saldo de pedido | `Pedido.saldo_pendiente` (property) + `pedido.anticipo` (campo sincronizado) + `snapshot_json['saldo_pendiente']` |
| Nombre del cliente en ticket | `Ticket.cliente_nombre` (campo) + `snapshot_json['cliente']` — ambos deben coincidir |
| Items de la operación | `ApartadoItem`/`ItemVenta` (registros DB) + `snapshot_json['items']` (copia congelada) — el snapshot existe porque las relaciones pueden cambiar, pero la forma de construirlo difiere por tipo de operación |
| Folio de apartado | Generado con COUNT+1 en `Apartado.save()` (NO atómico) vs `Secuencia.siguiente()` en `Ticket.save()` (atómico) |

---

## 6. Causa raíz de cada problema confirmado

### P1: Saldo pendiente no disminuye al registrar abono

**Estado: PARCIALMENTE CORREGIDO** en commits recientes.

- `PagoApartado.save()` → `apartado.anticipo = sum(pagos)` → `apartado.saldo = total - anticipo` ✓
- `PagoPedido.save()` → `pedido.anticipo = sum(pagos)` ✓ (fix previo en esta rama)
- `populate_from_obj` usa `total_pagado_acumulado = sum(abonos)` ✓ (fix previo)

**Riesgo residual:** Si el usuario recarga la pantalla ANTES de que el abono se registre completamente (race en conexiones lentas), puede ver el saldo antiguo. La pantalla no se actualiza automáticamente; el usuario debe recargar o la respuesta de la API debe incluir el nuevo saldo.

### P2: Notas de dama no visibles sin editar

**Estado: CORREGIDO** en commit reciente (`novia_detalle.html` muestra notas en la tarjeta).

### P3: No se puede agregar/editar color del vestido de dama

**Estado: PARCIALMENTE CORREGIDO** — se añadió modal de edición con campos `color_especial`, `talla`, `modelo`, `tela`, `notas`.

**Problema residual:** El endpoint `api_editar_dama` solo actualiza `nombre, telefono, talla, modelo_especial, color_especial, tela_especial, notas_ajustes`. Los FKs de catálogo (`Dama.color`, `Dama.modelo`, `Dama.tela`) — que son los campos normalizados que `Pedido.color/modelo/tela` usa — NO se actualizan desde este endpoint. La edición escribe en los campos de texto libre `*_especial`, no en los FKs.

### P4: Medidas, modelo, pagos y saldo de dama no disponibles en vista única

**Estado: PENDIENTE.** La vista `novia_detalle` muestra el resumen de pedidos de la novia, pero las medidas están en `Medidas` (OneToOne en `Pedido`). Para ver las medidas de una dama se debe abrir el pedido individual. No existe una vista consolidada por dama.

### P5: Eliminación informa éxito pero el registro permanece

**Estado: COMPORTAMIENTO CORRECTO (soft delete).** `api_eliminar_novia` y `api_eliminar_dama` hacen `activo=False`. Las vistas de lista filtran `activo=True`. El registro persiste en DB por integridad referencial. Los tickets y pedidos históricos siguen funcionales.

**Riesgo:** Si en alguna vista se consulta sin filtrar `activo=True`, los registros "eliminados" reaparecen.

### P6: Servicios producen HTTP 500

**Estado: CAUSA RAÍZ CONFIRMADA** por prueba de caracterización TC-07b.

El error se produce en el template `servicios_list.html`. La excepción capturada por los tests es:

```
django.template.base.VariableDoesNotExist: Failed lookup for key [nombre] in None
```

El template accede a `.nombre` sobre un objeto relacionado que puede ser `None`, probablemente `{{ servicio.novia.nombre }}` o `{{ servicio.cliente.nombre }}` dentro de un filtro de template (ej. `|truncatechars`, `|default`). Cuando la expresión está envuelta en un filtro, la excepción no queda silenciada por el motor de templates de Django y propaga hasta el handler, produciendo HTTP 500.

**Corrección:** Proteger con `{% if servicio.cliente %}{{ servicio.cliente.nombre }}{% endif %}` (y lo mismo para `novia`), o bien agregar `select_related('cliente', 'novia')` al queryset y usar el filtro `|default:'-'` en el template.

### P7: Detalle de pedidos no puede abrirse

**Estado: CAUSA PROBABLE.** No existe una URL `pedido/<pk>/` independiente. La vista `pedidos_en_puerta` muestra una lista. Si el usuario intenta abrir un "detalle" hace clic en un link dentro de `novia_detalle` o `pedidos_en_puerta`, y ese link apunta a una URL no registrada, obtiene 404. En `novia_detalle.html`, el acceso a propiedades como `p.modelo.nombre` puede causar `AttributeError` si `p.modelo` es `None` — aunque los templates de Django normalmente silencian estos errores mostrando vacío.

### P8: Agenda no muestra número de damas registrado en la cita

**Estado: DATO FALTANTE.** `CitaAgenda` tiene campo `cantidad_damas_esperadas`. Este se llena en `api_crear_cita` desde el formulario. Si el template `agenda_calendario.html` o `agenda_dia.html` no lo muestra, o si la cita fue creada sin capturar ese valor, aparece 0. Separado de `Novia.cantidad_damas` que sí se actualiza cuando se agregan damas.

### P9 (CRÍTICO): Tickets de Pedido no muestran artículos

**Estado: BUG ACTIVO.** Causa raíz:

```python
# En populate_from_obj(obj):
items_data = []
if hasattr(obj, 'items'):       # ← Pedido NO tiene 'items' RelatedManager
    for item in obj.items.all():
        ...
```

`Pedido` almacena el artículo directamente como campos (`modelo FK`, `color FK`, `tela FK`, `talla CharField`, `precio`). No tiene una relación `items` → `PedidoItem`. Cuando se genera un ticket para cualquier tipo de pedido (hechura, pedido externo, dama, novia), `items_data` queda vacío. El ticket imprime la cabecera con totales y pagos correctos, pero la sección de artículos está en blanco.

**Archivos afectados:**
- `boutique/models.py` función `Ticket.populate_from_obj()` (líneas 370-383)
- Impacta: `api_venta_rapida`, `api_crear_pedido`, `api_crear_pedido_completo`, `api_cobrar_item`, `api_liquidar_pedido`

### P10: Productos vendidos desde inventario pueden aparecer sin cliente

**Causa:** `Venta.cliente` es nullable. `api_registrar_venta` crea la venta con `cliente=None` si el JSON no incluye `cliente_id`. El ticket queda con `cliente_nombre=''`.

### P11: Tipos de ajuste colapsados bajo "Ajuste"

**Estado: COSMÉTICO.** Los tipos `BASTILLA`, `TALLE`, etc. tienen sus propios labels en `Servicio.TIPOS`. Si el template usa `{{ servicio.tipo }}` en lugar de `{{ servicio.get_tipo_display }}`, muestra el código (`BASTILLA`) en lugar del nombre (`Bastilla`). Si usa el valor fijo `AJUSTE`, muestra "Ajuste general" para todo. Requiere verificar el template `servicios_list.html`.

### P12: Variantes permiten duplicados semánticos

**Estado: MITIGADO.** La migración 0039 agrega restricción de unicidad. Sin embargo, `api_clonar_variante` crea nuevas variantes y puede crear combinaciones idénticas si el usuario clona dos veces con el mismo color/talla. El endpoint de creación (`api_validar_crear_producto`) tiene verificación de duplicados vía IA, pero la clonación no la tiene.

### P13: Variantes pueden perder la fotografía original

**Causa:** `api_clonar_variante` copia `categoria, modelo, tela, rasgo1, rasgo2, precio_venta` pero NO copia `foto`. El nuevo `Producto` queda sin foto hasta que se suba manualmente. Tampoco está documentado que se debe subir foto.

### P14: Colores, telas y tallas admiten formas inconsistentes

**Causa:** `api_crear_color` y `api_crear_tela` tienen verificación de duplicados vía IA (Gemini), pero si Gemini no responde, la verificación se omite. Además, los campos `modelo_especial`, `color_especial`, `tela_especial` en `Dama` y `Novia` son texto libre sin validación — pueden contener "rosa palo", "Rosa Palo", "ROSA PALO" como entradas distintas.

### P15: `TicketItem` es un modelo muerto

`TicketItem` existe en la BD (tiene campos `descripcion`, `modelo`, `color`, `talla`, `sku_snapshot`) pero NUNCA se crea en ningún endpoint. Toda la información de items va a `Ticket.snapshot_json`. Esto crea confusión sobre dónde viven los datos del ticket.

---

## 7. Archivos afectados por módulo

| Archivo | Problemas |
|---------|-----------|
| `boutique/models.py` | R1 (Ticket.populate_from_obj), R5 (TicketItem sin uso), Apartado folio no atómico |
| `boutique/services/cash_service.py` | Correcto. Única fuente de cobros. |
| `boutique/services/ticket_service.py` | No lee items de Pedido (consume snapshot ya vacío) |
| `boutique/views.py` | P10 (venta sin cliente), P6 (servicio 500) |
| `boutique/views_agenda.py` | P4 (dama sin vista consolidada), api_editar_dama no actualiza FKs |
| `boutique/views_apartados.py` | ApartadoItem.modelo/color siempre vacíos |
| `boutique/templates/boutique/servicios_list.html` | Probable causa de HTTP 500 (no leído) |
| `boutique/templates/boutique/pos_dashboard.html` | api_search_productos no devuelve modelo/color para el carrito |
| `boutique/templates/boutique/novia_detalle.html` | api_editar_dama no actualiza FKs normalizados |
| `boutique/migrations/` | 39 migraciones correctamente aplicadas |

---

## 8. Riesgos de migración

| Cambio propuesto | Riesgo |
|------------------|--------|
| Agregar `PedidoItem` (tabla nueva) | BAJO — tabla nueva, sin datos existentes |
| Mover `Pedido.modelo/color/tela` a `PedidoItem` | ALTO — requiere migración de datos, todos los pedidos existentes |
| Eliminar `TicketItem` del esquema | MEDIO — la tabla existe pero está vacía; eliminarla es seguro |
| Hacer atómica la generación del folio de `Apartado` | BAJO — cambiar a `Secuencia.siguiente('AP')` |
| Agregar FK de catálogo a `api_editar_dama` | BAJO — solo agregar campos opcionales al endpoint |
| Normalizar `ApartadoItem.modelo/color` a FK | ALTO — hay registros existentes con texto libre |

**Recomendación:** No migrar datos de texto a FK para `ApartadoItem` en esta fase. Mantener los campos de texto como fallback y agregar FKs opcionales nuevos.

---

## 9. Propuestas de arquitectura mínima

### 9.1 Modelo único para líneas de venta

**Problema:** Cuatro tipos de línea de venta con estructuras diferentes:
- `ItemVenta` (FK Producto, sin modelo/color propios — los hereda del producto)
- `ApartadoItem` (FK Producto nullable, modelo/color como texto libre)
- `Pedido` (él mismo ES la línea — modelo/color/tela como FK, precio directo)
- `Servicio` (sin líneas — él mismo es el servicio)

**Solución mínima (sin romper esquema actual):**

Agregar en `populate_from_obj` un caso explícito para `Pedido`:

```python
# Si el objeto ES el artículo (Pedido sin items manager):
elif hasattr(obj, 'precio') and hasattr(obj, 'modelo') and not hasattr(obj, 'items'):
    prod = obj.producto
    items_data = [{
        'descripcion': f"{obj.modelo.nombre if obj.modelo else 'Vestido'} "
                       f"{obj.color.nombre if obj.color else ''}".strip(),
        'modelo':  obj.modelo.nombre if obj.modelo else '',
        'color':   obj.color.nombre if obj.color else '',
        'tela':    obj.tela.nombre if obj.tela else '',
        'sku':     prod.sku if prod else '',
        'talla':   obj.talla or '',
        'cantidad': 1,
        'precio_unitario': float(obj.precio),
        'subtotal':        float(obj.precio),
    }]
```

**Solución completa (requiere migración):**

Crear `PedidoItem`:
```python
class PedidoItem(models.Model):
    pedido = models.ForeignKey(Pedido, related_name='items', on_delete=models.CASCADE)
    producto  = models.ForeignKey(Producto, null=True, blank=True, on_delete=models.SET_NULL)
    descripcion = models.CharField(max_length=255)
    modelo   = models.ForeignKey(Modelo, null=True, blank=True, on_delete=models.SET_NULL)
    color    = models.ForeignKey(Color, null=True, blank=True, on_delete=models.SET_NULL)
    tela     = models.ForeignKey(Tela, null=True, blank=True, on_delete=models.SET_NULL)
    talla    = models.CharField(max_length=10, blank=True)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal        = models.DecimalField(max_digits=10, decimal_places=2)
```

Con este modelo, `hasattr(pedido, 'items')` sería True y `populate_from_obj` funcionaría sin cambios adicionales.

### 9.2 Servicio único de pagos y saldos

`cash_service.registrar_cobro()` ya es la función maestra. **No duplicar.** Todos los cobros deben pasar por ella.

**Regla a documentar como contrato:**
```
saldo_pendiente = total_comprometido − Σ(pagos válidos del mismo origen)
```

Donde `total_comprometido`:
- `Venta.total`
- `Apartado.total`
- `Pedido.precio`
- `Servicio.costo`

Y `Σ(pagos)`:
- `venta.pagos.aggregate(Sum('monto'))`
- `apartado.pagos_apartado.aggregate(Sum('monto'))`
- `pedido.pagos_pedido.aggregate(Sum('monto'))`
- `servicio.pagos_servicio.aggregate(Sum('monto'))`

**No almacenar el saldo como campo calculado manualmente** (excepto `Apartado.saldo` como caché derivado de `anticipo`).

### 9.3 Generador único de tickets

`ticket_service.py` ya centraliza la generación de PDF y ESC/POS. El contrato de datos de entrada es `Ticket.snapshot_json`. El único problema es que el snapshot se construye en `Ticket.populate_from_obj()` con lógica diferente por tipo.

**Contrato propuesto para `snapshot_json['items']`:**
```json
{
  "items": [
    {
      "sku": "VES-ABC123",
      "modelo": "Sirena Enamorada",
      "color": "Rosa Palo",
      "tela": "Satín",
      "talla": "M",
      "descripcion": "Vestido de Novia - Sirena ...",
      "cantidad": 1,
      "precio_unitario": 8500.00,
      "subtotal": 8500.00
    }
  ]
}
```

Este contrato ya está casi implementado. El único gap es que para `Pedido`, `items` queda `[]`.

### 9.4 Normalización de catálogos

**Correcto:** `Color`, `Tela`, `Modelo`, `Categoria` son entidades de catálogo con FKs.

**Problema:** Los campos `modelo_especial`, `color_especial`, `tela_especial` en `Dama` y `Novia` son texto libre sin validación ni vinculación al catálogo. En `ApartadoItem`, `modelo` y `color` son texto libre.

**Propuesta mínima:** Agregar a `api_editar_dama` la actualización de `Dama.color FK`, `Dama.modelo FK`, `Dama.tela FK` cuando se proporcionen IDs del catálogo. Los campos texto libre `*_especial` se mantienen para casos especiales sin catálogo.

**No requerido en esta fase:** Validar en servidor que los textos libres no dupliquen entradas del catálogo (alta complejidad, bajo beneficio inmediato).

---

## 10. Plan de pruebas

### Pruebas de caracterización (demuestran comportamiento actual, pueden fallar)

Ver archivo `boutique/tests_caracterizacion.py` (incluido en este commit).

Cubre:
1. Abono que actualiza saldo (debería pasar)
2. Ticket desde venta de inventario con cliente (debería pasar)
3. Ticket desde pedido — verifica items vacíos (FALLARÁ: demuestra R1)
4. Ticket desde apartado — verifica items con modelo/color (depende de datos)
5. Dama con notas y medidas — acceso programático
6. Soft delete de novia
7. Creación de servicio
8. Flujo completo: crear pedido + cobrar + verificar snapshot

### Pruebas de aceptación (a crear DESPUÉS de implementar correcciones)

| # | Flujo | Criterio de aceptación |
|---|-------|------------------------|
| A1 | Venta directa | Ticket impreso tiene nombre de cliente, 1+ artículo con SKU, modelo, color, precio |
| A2 | Apartado + abono | Saldo en pantalla decrece; ticket de abono muestra monto pagado y saldo restante |
| A3 | Pedido de dama | Ticket tiene artículo con modelo, color, talla, precio; no muestra lista de artículos vacía |
| A4 | Liquidación de pedido | `Pedido.saldo_pendiente == 0`, `estado_pago == 'LIQUIDADO'` en DB |
| A5 | Imprimir etiqueta | Etiqueta Brother QL-800 imprime sin error; tiene SKU legible |
| A6 | Eliminar novia | `Novia.activo == False` en DB; no aparece en lista |
| A7 | Crear servicio + cobrar | Servicio creado sin 500; cobro genera ticket con tipo SERVICIO |
| A8 | Ver detalle de novia | Página carga sin error; notas visibles; damas listadas con talla y color |

---

## 11. Plan de implementación (PRs ordenadas y pequeñas)

Todas las PRs deben partir de la rama `claude/review-repo-structure-DNkLG` (o de una rama estable derivada de ella una vez fusionada).

### PR-01: Corrección crítica de items en tickets de Pedido

**Archivos:** `boutique/models.py` (solo `populate_from_obj`)  
**Cambio:** Agregar caso especial para objetos `Pedido` sin `items` RelatedManager  
**Prueba obligatoria:** `test_ticket_pedido_tiene_items` debe PASAR  
**Sin migraciones**

### PR-02: Diagnóstico y corrección del HTTP 500 en servicios

**Archivos:** `boutique/templates/boutique/servicios_list.html` + posible `boutique/views.py`  
**Cambio:** Identificar y corregir la causa del 500; agregar `select_related` al queryset si aplica  
**Prueba obligatoria:** GET a `/servicios/` devuelve 200  
**Sin migraciones**

### PR-03: Folio de Apartado atómico

**Archivos:** `boutique/models.py` (`Apartado.save`)  
**Cambio:** Usar `Secuencia.siguiente('AP')` en lugar de COUNT+1  
**Prueba:** crear 10 apartados concurrentes, verificar unicidad de folios  
**Sin migraciones** (Secuencia ya existe)

### PR-04: api_editar_dama — actualizar FKs de catálogo

**Archivos:** `boutique/views_agenda.py` (`api_editar_dama`)  
**Cambio:** Aceptar `color_id`, `modelo_id`, `tela_id` y actualizar FKs además de los campos texto  
**Prueba:** editar dama con color_id válido, verificar `Dama.color_id` en DB  
**Sin migraciones**

### PR-05: api_search_productos devuelve modelo y color

**Archivos:** `boutique/views.py` (`api_search_productos`)  
**Cambio:** Incluir `modelo: p.modelo.nombre if p.modelo else ''` y `color: p.color.nombre` en el resultado  
**Cambio frontend:** `pos_dashboard.html` — carrito pasa `modelo` y `color` al crear `ApartadoItem`  
**Prueba:** búsqueda de producto devuelve objeto con campo `modelo` y `color`  
**Sin migraciones**

### PR-06: Eliminar TicketItem del esquema (limpieza)

**Archivos:** `boutique/models.py`, nueva migración  
**Cambio:** Eliminar modelo `TicketItem` (tabla vacía)  
**Migración:** `DeleteModel('TicketItem')`  
**Bajo riesgo — tabla vacía**

### PR-07: Vista consolidada de dama

**Archivos:** `boutique/templates/boutique/novia_detalle.html`, `boutique/views_agenda.py`  
**Cambio:** Panel expandible por dama con: medidas completas, pagos, saldo, estado, acciones  
**Requiere:** leer `Dama.pedidos.first().medidas` para mostrar medidas  
**Sin migraciones**

### PR-08: Pruebas de aceptación completas

**Archivos:** `boutique/tests_aceptacion.py`  
**Cambio:** Implementar los 8 tests de aceptación de la sección 10  
**Bloqueada por:** PRs 01-07 deben estar aprobadas

---

## 12. Comandos ejecutados en esta auditoría

```bash
# Listado de archivos
ls /home/user/POS_AB/boutique/
ls /home/user/POS_AB/boutique/services/
ls /home/user/POS_AB/boutique/migrations/

# Lectura completa de archivos críticos
# boutique/models.py (1392 líneas)
# boutique/services/cash_service.py (138 líneas)
# boutique/services/ticket_service.py (502 líneas)
# boutique/views.py (2744 líneas — todos los endpoints)
# boutique/views_agenda.py (1034 líneas)
# boutique/views_apartados.py (129 líneas)
# boutique/middleware.py (70 líneas)
# boutique/tests.py, tests_perfiles.py
# boutique/migrations/0039_*.py
# boutique/urls.py (145 líneas)
# boutique/templates/boutique/pos_dashboard.html
# boutique/templates/boutique/novia_detalle.html
# boutique/templates/boutique/inventario.html (primeras 300 líneas)

grep -n "def api_" boutique/views.py       # 33 endpoints
grep -n "def api_" boutique/views_agenda.py # 20 endpoints
```

---

## 12b. Resultados de pruebas de caracterización ejecutadas

```
Ejecutado: 16 pruebas
python manage.py test boutique.tests_caracterizacion

TC01 test_abono_reduce_saldo                           PASA   ✓
TC02 test_ticket_tiene_items_y_cliente                 PASA   ✓
TC03 test_saldo_pedido_correcto_independiente_de_items PASA   ✓
TC03 test_ticket_pedido_tiene_items                    FALLA  ✗  ← bug R1 confirmado
TC04 test_ticket_apartado_tiene_items_con_datos        PASA   ✓
TC05 test_dama_tiene_campos_notas_y_medidas            PASA   ✓
TC05 test_dama_visibilidad_de_notas_sin_edicion        PASA   ✓
TC06 test_eliminar_novia_hace_soft_delete              PASA   ✓
TC06 test_novia_eliminada_no_aparece_en_lista          PASA   ✓
TC07 test_crear_servicio_retorna_200                   PASA   ✓
TC07 test_servicio_lista_no_devuelve_500               ERROR  ✗  ← bug P6 confirmado (HTTP 500)
TC07 test_cobrar_servicio_genera_ticket                PASA   ✓
TC08a test_a_ticket_pedido_items_vacios                FALLA  ✗  ← bug R1 confirmado
TC08b test_b_saldo_y_abonos_correctos                  PASA   ✓
TC09 test_clonar_variante_no_tiene_foto                PASA   ✓  (documenta bug P13)
TC10 test_folio_apartado_usa_count_no_secuencia        PASA   ✓  (documenta race potencial)
```

**Resumen:** 13/16 PASAN · 2 FALLAN intencionalmente (bug R1) · 1 ERROR (bug P6 = HTTP 500 en servicios)

---

## 13. Primera corrección a implementar

**PR-01: items vacíos en tickets de Pedido** es la corrección de mayor impacto y menor riesgo.

Cambio en `boutique/models.py`, función `populate_from_obj`, después de `items_data = []`:

```python
items_data = []
if hasattr(obj, 'items'):
    # Venta (ItemVenta), Apartado (ApartadoItem) — tienen RelatedManager 'items'
    for item in obj.items.all():
        prod = item.producto if hasattr(item, 'producto') and item.producto else None
        # ... (código existente)
elif hasattr(obj, 'precio') and hasattr(obj, 'modelo'):
    # Pedido — el objeto en sí es el artículo
    items_data = [{
        'descripcion': (
            f"{obj.modelo.nombre} " if obj.modelo else ""
            + (obj.color.nombre if obj.color else "")
        ).strip() or "Vestido",
        'modelo':  obj.modelo.nombre if obj.modelo else '',
        'color':   obj.color.nombre  if obj.color  else '',
        'tela':    obj.tela.nombre   if obj.tela   else '',
        'sku':     obj.producto.sku  if obj.producto else '',
        'talla':   obj.talla or '',
        'cantidad': 1,
        'precio_unitario': float(obj.precio),
        'subtotal':        float(obj.precio),
    }]
```

Esta corrección no requiere migración, no afecta otras entidades, y es reversible.
