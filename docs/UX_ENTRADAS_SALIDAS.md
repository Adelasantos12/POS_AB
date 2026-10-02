# Navegación simplificada: Entradas, Salidas, Buscar prendas y Etiquetas

Desarrollada sobre la rama de costos, sin modificar la versión estable ni Railway.

## Pantalla principal

- Entradas: prendas nuevas o regresos, identificados por su etiqueta.
- Salidas: destino del grupo, escaneo y confirmación.
- Buscar prendas: consulta de ubicación e historial, sin seleccionar para movimientos.
- Etiquetas: abre los modelos para imprimir o reimprimir por variante.
- Agregar modelo y Subir varias fotos permanecen visibles.
- Más opciones conserva conteo inicial, entrada individual, comprobación de etiquetas, movimientos detallados/devoluciones, importación, exportación, costos y registro avanzado según los permisos existentes.

Se elimina la etiqueta ambigua «Preparar vestidos». Las rutas internas originales siguen existiendo.

## Entradas

Escanear crea una selección; no cambia stock hasta confirmar. El servidor reconoce prendas con etiqueta creada pero sin recibir y prendas ya registradas. Las nuevas se registran con las reglas actuales de conteo/recepción y costos. Las que regresan cambian su ubicación/estado sin sumar otra pieza. Las etiquetas sobrantes del cierre inicial continúan bloqueadas.

El grupo admite destinos individuales. Una operación se confirma completa o no se registra ninguna pieza si hay errores. Se conserva la clave de confirmación para no duplicar operaciones por reintento.

Si no hay etiqueta, el acceso lleva a buscar modelo/variante, imprimir una etiqueta nueva o reimprimir la existente. La selección queda en un borrador dentro de la sesión; Inventario permite continuarla. No se vuelve a crear el vestido por perder su etiqueta.

## Salidas

Seleccionar destino. Taller muestra persona/local y motivo (Arreglo, Replicar modelo o Revisión); ese motivo asigna el estado. Para otros destinos se propone disponible, con opción de revisión. Fecha de regreso y notas se agrupan como opcionales. Cada prenda puede tener una excepción individual.

Contador y confirmación permanecen visibles. La confirmación resume cantidades por destino; el resultado muestra folio MOV, cantidad y destinos.

## Borradores y límites

Se guardan en la sesión Django con clave por perfil y tipo de operación. Sobreviven a navegación/recarga de esa sesión. No son una bandeja compartida entre dispositivos ni órdenes de entrega completas. Otra pestaña de la misma sesión puede reemplazar el mismo borrador; no trabajar simultáneamente en dos entradas del mismo perfil. Si falla el guardado se informa y se pide mantener la pantalla abierta.

El regreso conserva historial individual, pero no se añadió todavía un vínculo formal de conciliación contra una orden de salida. No se cambió el tratamiento de apartados o reembolsos.

## Verificación

26 pruebas Django locales aprobadas. Incluyen mezcla de prenda nueva y regreso en una entrada, rechazo/rollback completo si una etiqueta no es válida, reintentos sin duplicar, borradores separados por perfil y consulta sin movimiento. Se comprobó sintaxis JavaScript y ausencia de nuevas migraciones.

Pendiente antes de activar: recorrido visual en Safari y observación de una persona usuaria completando una entrada y una salida sin ayuda. Las pruebas de código no sustituyen la evaluación de usabilidad.
