# Implementación y traspaso técnico — costos

## Base y aislamiento

Base remota b50f9a7467026492b2a17655cc8401a135cc309f; árbol 9ae0230779a99eb053b2ee82a5f17de78036b391. Rama nueva feature/costos-inversion-2026-10-02. La referencia estable y el servicio Railway se mantienen intactos.

## Datos

- Modelo: costo_referencia nullable, precio_sugerido nullable, proveedor.
- Producto/variante: costo_referencia nullable, heredado al crear variante.
- PiezaEtiqueta: costo_unitario nullable. Se fija al escanear por primera vez en conteo/recepción; imprimir no lo fija.
- MovimientoPieza: costo_unitario y precio_unitario como fotografía de venta/devolución. No se recalculan con cambios de precio o referencia.
- CambioCosto: antes/después, motivo, fecha, responsable por corrección de costo de una prenda propia.
- AnalisisInversion: fotografía JSON, texto, fecha, responsable y nombre del modelo de IA.
- Migraciones aditivas boutique/0051 y preparacion/0005; valores históricos quedan NULL. No hay asignación automática de costos antiguos ni cambios de códigos/fotos/existencias.

## Reglas de cálculo

La valoración incluye prendas con contada no nula y no vendidas, más estado APARTADA (el flujo anterior marca vendida al apartar). Excluye modelos sin piezas y etiquetas sin contar. Separamos costos faltantes, inventario legacy sin serialización, y conteo sin cierre. El dinero disponible se restringe a Boutique, DISPONIBLE y variante confirmada.

El margen usa eventos VENDIDA/DEVOLUCION de los últimos 30 días, con ambos importes conocidos. Al vender, se conserva precio de ItemVenta solo cuando la suma de líneas coincide con Venta.total; si hay diferencias por servicios/descuentos no atribuibles, se deja NULL. No es cálculo de margen fiscal ni utilidad neta. Devoluciones revierten margen operativo por recepción física, no un asiento de caja.

## Permisos y concurrencia

Se reutiliza es_admin (Admin/Superadmin/CEO/Supervisora según permisos existentes). Vendedor no accede a las rutas de inversión, costos o IA. ModelForm omite campos de costo/proveedor y recepción ignora overrides enviados por vendedores. Los cambios de costo y ventas bloquean la misma fila de prenda con select_for_update. Movimientos no cambian costo; devoluciones conservan snapshots del evento de venta.

## IA

Usa get_gemini_client y GEMINI_MODEL existentes. Solo agregados/modelos, sin fotos/clientes/proveedor. Límite 5 solicitudes/hora por usuario; texto escapado en HTML/textContent. Salida consultiva, sin herramientas de mutación. Errores no alteran inventario. Prueba con proveedor simulado; no se gastó una llamada real ni se verificó calidad factual del modelo externo.

## Validación

Suite: python manage.py test preparacion --noinput. Incluye pruebas anteriores y 6 de costos: valoración incompleta, referencia futura, permisos, costo histórico/devolución errores/IA sin mutación y captura de costos por rol. Resultado: 23 pruebas locales aprobadas. Validación local SQLite; ejecutar también en PostgreSQL y revisar Safari en staging antes de activar. No se probaron impresión física ni producción porque están congeladas.

## Puesta en producción futura

Solo tras instrucción posterior: respaldo de base y archivos, staging con datos aislados, migraciones aditivas, revisión de roles/cobertura de costos. Nunca usar la base real para pruebas ni cerrar el conteo real. Mantener rama estable como referencia; no revertir schema eliminando historial financiero.
