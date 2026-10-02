# Costos e inversión — guía de la nueva rama

Esta función está preparada en `feature/costos-inversion-2026-10-02`. No está activada en la versión de la tienda.

## Cómo se usaría

1. En Agregar modelo o Subir varias fotos, Admin captura costo por prenda, precio sugerido y proveedor. El costo puede quedar pendiente.
2. Al crear variantes, se hereda el costo del modelo; Admin puede indicar uno distinto.
3. Al contar o recibir, cada prenda toma el costo de referencia de su variante. Admin puede indicar el costo real de esa entrada antes de escanear. Vendedora puede recibir, pero no consultar ni modificar costos.
4. En Dashboard Admin → Ver inversión, ubicaciones e IA, se muestran las prendas registradas, costos conocidos y pendientes, ubicación y estado.
5. Para una prenda ya registrada, buscar etiqueta, escribir costo y motivo. La corrección deja un registro y no reescribe ventas anteriores.
6. Para futuras compras, actualizar Costo sugerido para próximas entradas por SKU. Las prendas anteriores conservan su costo.

Todos los importes se capturan en MXN por prenda. Para compras en otra moneda se debe registrar el costo convertido a MXN; no hay conversión automática ni cálculo fiscal. No incluir costo total del lote como si fuera unitario.

## Qué significan los indicadores

- Dinero en inventario: suma de costos conocidos de prendas propias escaneadas, incluidas las apartadas identificadas por el sistema. Si faltan costos, es un subtotal.
- Imprimir etiquetas o crear modelos no suma inversión.
- Un traslado cambia ubicación; no cambia el costo ni crea una nueva prenda.
- Las unidades antiguas sin identificación individual se informan aparte y no se valoran automáticamente.
- Valor a precio de venta: suma de precios actuales. No es ingreso realizado ni garantizado.
- Margen bruto registrado: ingresos atribuibles por prenda menos costo guardado al vender, descontando las devoluciones físicas del período. No es utilidad neta ni confirma un reembolso.
- Operaciones mezcladas con servicios o descuentos sin distribución individual quedan sin margen calculado si no se puede atribuir el ingreso con certeza.
- Antigüedad: días desde el escaneo. No equivale a fecha de compra. La falta de ventas registradas no demuestra ausencia de ventas previas.

## Análisis con IA

Analizar mi inventario genera sugerencias con los totales y hasta 50 modelos de mayor inversión. Incluye evidencia y limitaciones; no ejecuta compras, descuentos, movimientos ni publicidad. Guarda fecha, datos usados y respuesta para revisión.

No envía fotos, datos de clientas ni proveedores en este análisis. Usa el proveedor Gemini ya configurado. Las recomendaciones deben revisarse antes de actuar. Si no hay clave o el servicio falla, los indicadores siguen funcionando.

## Antes de activar

Revisar esta rama con datos de prueba, costos de ejemplo y perfiles Admin/Vendedora. Confirmar después la puesta en producción. No cerrar el inventario real para hacer pruebas.
