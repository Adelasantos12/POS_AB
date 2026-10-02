# Punto de restauración del POS — 2 de octubre de 2026

Congelación solicitada por Adela antes de integrar costos y análisis de inversión.

- Repositorio: Adelasantos12/POS_AB.
- Commit estable: `b50f9a7467026492b2a17655cc8401a135cc309f`.
- Copia estable: `stable/pos-2026-10-02`. No avanzar esta referencia.
- Rama que utiliza Railway: `claude/review-repo-structure-DNkLG`.
- Despliegue estable: `1358a344-a03d-4be0-b971-6977dda79754` (SUCCESS).
- Trabajo nuevo: `feature/costos-inversion-2026-10-02`.

La rama estable es un punto de referencia de código, no un respaldo de la base de datos ni de Cloudinary. No se borraron, reiniciaron ni copiaron datos de producción para este trabajo.

## Lo que debe conservarse

1. Agregar modelo con foto, nombre, categoría, tela, características y notas antes de las variantes.
2. Subir hasta 20 fotos, revisar sugerencias de IA y guardar modelos sin sumar inventario.
3. Agregar variantes dentro del modelo, con foto compartida, color, tela y talla.
4. Imprimir etiquetas individuales desde Inventario. Cada prenda tiene código numérico propio; reimprimir conserva el código.
5. Conteo inicial de etiquetas distintas, separado de cantidades estimadas. El cierre activa solo lo contado.
6. Recepción posterior con Boutique, Bodega, Otro local o Taller; ubicación y estado por escaneo.
7. Ubicaciones y movimientos: grupos con excepciones individuales, responsable, regreso previsto e historial.
8. Regresos sin duplicar existencias; bloqueo de venta si la prenda no está disponible en Boutique.
9. Devolución física de prendas con venta vinculada, solo administración. No efectúa reembolsos.
10. Totales por variante/modelo y cabecera. Eliminación de pruebas por Admin, con bloqueo por historial o inventario confirmado; Vendedora no puede borrar.

## Límites conocidos que no deben ocultarse

- Las ventas antiguas sin vínculo individual no pueden devolverse automáticamente por el nuevo flujo.
- Los apartados conservan la implementación previa; no se rediseñó su ciclo completo de entrega/cancelación.
- La desaparición reportada de la foto de Princesa no tuvo diagnóstico concluyente. No afirmar que se recuperó o que fue eliminada.
- Las sugerencias de IA requieren la configuración externa existente y revisión humana.
- Las pruebas automatizadas fueron locales con SQLite; no equivalen a probar impresora Brother/Safari ni todos los flujos visuales de producción.
- Las imágenes se almacenan según la configuración de Cloudinary. La rama de Git no respalda los archivos subidos.

## Regla de continuidad

No desplegar la rama de costos en el servicio actual ni fusionarla sin una instrucción posterior de Adela. Validar con una base aislada antes de su puesta en producción. Un retorno de código no debe intentar deshacer automáticamente migraciones ni borrar costos o historial.
