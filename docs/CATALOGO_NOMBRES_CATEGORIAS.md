# Nombre del modelo, categoría y filtros

Ampliación en feature/codigos-fabricante-costos-bloque. Autorización de la usuaria: subir esta rama a Adelasantos12/POS_AB; no fusionar ni desplegar.

## Captura

- Categoría identifica el tipo de producto: Vestidos, Infantiles, Velos, Capas, Fajas, Accesorios u Otros. No es necesario separar Damas y Fiesta para registrar vestidos. Se conservan todas las categorías anteriores.
- Nombre del modelo es el nombre que usa la tienda, por ejemplo «1 hombro manga caída». Se reutiliza Modelo.nombre; no se crea un campo paralelo.
- Características adicionales siguen disponibles para descripciones opcionales.
- La carga en bloque ahora tiene nombre del modelo separado y categoría mediante lista. La IA sugiere; la persona revisa. Nombres diferentes no se agrupan aunque coincidan color, talla y descripción. La API conserva compatibilidad con cargas anteriores sin nombre explícito.

## Inventario

Filtro de categoría en la parte superior, combinable con búsqueda y conservado al paginar. Orden alfabético por nombre mostrado, también para familias antiguas sin Modelo; insensible a mayúsculas y acentos. Las cifras de cabecera corresponden al conjunto filtrado, como antes con la búsqueda.

Admin dispone de «Editar nombre y categoría» en cada ficha. Actualiza la familia seleccionada, conservando SKU, identificadores internos, fotos, precios, costos y cantidades. Una ficha antigua puede pasar a un Modelo sin recrear productos. No fusiona modelos con nombres existentes ni modifica todas las prendas de una antigua categoría. Los cambios de nombre/categoría se reflejan en consultas que usan el catálogo actual; no reescriben importes históricos.

La migración 0008 añade solo las categorías generales que falten. No reclasifica ni elimina categorías existentes. Su reversión no las borra para evitar pérdida de referencias.

## Validación

Pruebas específicas: filtro combinado, orden de familias nuevas/antiguas, separación de modelos en carga en bloque, reclasificación sin cambiar códigos/cantidades y permisos. JavaScript renderizado de carga e inventario verificado con Node. No se ha verificado visualmente en Safari ni con dispositivos físicos.

Resultado: 200 pruebas Django aprobadas en SQLite. Incluye las pruebas anteriores del POS y las nuevas del catálogo y códigos del fabricante.
