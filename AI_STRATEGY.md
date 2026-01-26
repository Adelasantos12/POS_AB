# Estrategia de Asistencia IA - Adelé POS

Para optimizar la operación de tienda sin añadir complejidad, se propone la integración de un asistente de lenguaje natural con las siguientes capacidades:

## 1. Mapeo de Atributos por Descripción
**Objetivo:** Que el usuario pueda escribir "Vestido de seda largo con manga francesa en color rojo" y el sistema pre-llene el formulario de Producto Rápido.

- **Tecnología:** OpenAI GPT-3.5/4 Turbo o modelos locales ligeros.
- **Implementación:**
  - Un campo de texto libre en el modal de Producto Rápido.
  - El backend envía la descripción al LLM con un prompt estructurado que define el catálogo de atributos (Telas, Escotes, Mangas).
  - El LLM devuelve un JSON con los campos identificados.

## 2. Detección Inteligente de Duplicados
**Objetivo:** Ir más allá del `SequenceMatcher` básico para identificar productos similares por semántica.

- **Tecnología:** Embeddings (text-embedding-3-small).
- **Implementación:**
  - Generar un embedding del conjunto de rasgos (`rasgo1` + `rasgo2` + `modelo`).
  - Usar búsqueda vectorial (Cosine Similarity) para encontrar los 3 productos más parecidos en el inventario actual de 2000+ items.
  - Mostrar miniaturas de los productos sugeridos para confirmación visual del operador.

## 3. Generación Automática de Descripciones para Marketing
**Objetivo:** Ayudar a vender por redes sociales.

- **Tecnología:** GPT-4 Vision.
- **Implementación:**
  - Al subir la foto del producto, la IA genera una descripción atractiva basada en los atributos detectados en la imagen y los datos técnicos ingresados.

## Roadmap de Implementación
- **Fase 1:** Prototipo de extracción de atributos (Texto -> JSON).
- **Fase 2:** Búsqueda por similitud semántica (Embeddings).
- **Fase 3:** Análisis de imágenes (Vision).
