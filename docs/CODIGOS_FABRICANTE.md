# Códigos del fabricante y costo en carga en bloque

Base: rama feature/costos-inversion-2026-10-02, respaldo congelado 38ded2f. Trabajo independiente en feature/codigos-fabricante-costos-bloque. La usuaria informó que desplegó la rama de costos. No modificar referencias congeladas ni desplegar este cambio sin instrucción.

## Uso

Inventario → Códigos del fabricante. Administración vincula un código con las variantes de un mismo modelo. Aplica a cualquier categoría (capas, fajas, etc.). Crear variantes conserva el flujo existente de foto, modelo, color y talla. Vincular no altera etiquetas ni suma existencias.

Registrar entrada por cantidad: elegir variante, cantidad real y Boutique/Bodega. Confirmar crea unidades internas con costo e historial, sin exigir imprimirlas. Repetir la misma confirmación no duplica la entrada. Cantidad significa piezas adicionales, no sustitución del saldo. Si el conteo inicial está abierto hay que terminarlo primero. Las existencias anteriores sin unidades identificadas no se convierten automáticamente.

En Caja, escanear el código presenta colores/tallas y stock vendible. Enter del lector no selecciona la primera opción. Elegir la variante y cobrar; solo se asignan unidades disponibles en Boutique. Cada venta retiene costos e historial. Requiere conexión. Los identificadores internos son contables: una etiqueta compartida no prueba qué ejemplar físico se vendió; la asignación sigue el orden de recepción. Para trazabilidad física individual, mantener etiquetas propias.

Corregir color/talla: Administración reclasifica una cantidad entre variantes del mismo código. Conserva total, códigos internos, costo y ubicación; registra motivo y variantes anteriores. Solo piezas disponibles sin venta previa. No edita ventas históricas. No sirve para eliminar pérdidas o mercancía inexistente.

La pantalla incluye existencias por ubicación/color/talla y ventas y devoluciones registradas por combinación. No interpreta ventas anteriores a la implantación ni equipara devoluciones físicas con reembolsos.

## Carga en bloque

Había dos rutas: modelos por fotos ya incluía costo; /inventario/subida-bloque/ no. Se añade costo unitario opcional en la tabla y API, solo para Admin. Se guarda como referencia al crear producto; vacío permanece NULL. No se reescriben costos de productos existentes ni de ventas anteriores. La ruta antigua sigue registrando existencias legacy: su costo de referencia no convierte esos registros en unidades valoradas por el dashboard. Usar las entradas por cantidad del nuevo módulo para unidades con inversión individual; no volver a ingresar existencias ya registradas.

## Arquitectura y límites

Migraciones aditivas preparacion 0006/0007: alias externo, entrada idempotente y corrección idempotente. Reutiliza PiezaEtiqueta y MovimientoPieza. Preserva costo/ubicación y usa transacciones y bloqueo de productos. Protege prefijo numérico interno 8 + 11 dígitos. Los códigos externos admiten letras y números y conservan ceros iniciales. Alta/vínculo y correcciones restringidos a Admin; Vendedor no recibe ni puede fijar costos.

No se cambió el ciclo anterior de apartados/entregas. Movimientos fuera de Boutique conservan los accesos individuales existentes; el nuevo formulario por cantidad solo recibe en Boutique/Bodega. No se ha comprobado Safari, lector físico ni impresora ni concurrencia en PostgreSQL. No se consultaron ni modificaron datos de producción.

## Verificación realizada

196 pruebas Django aprobadas en SQLite, incluidas 5 nuevas que recorren la API real de venta con caja abierta, reintento, stock por variante/ubicación, costo histórico, corrección idempotente, permisos y costo de carga legacy. Las 31 pruebas del módulo de preparación también pasaron. Plantillas renderizadas y JavaScript de Caja/carga en bloque comprobado con Node. Migraciones consistentes (`makemigrations --check`). No es una prueba visual ni del lector físico.
