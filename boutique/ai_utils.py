import google.generativeai as genai
from django.conf import settings
import json
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

if hasattr(settings, 'GEMINI_API_KEY') and settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)

def get_gemini_model(model_name="gemini-2.0-flash"):
    """Configura y devuelve el modelo de Gemini"""
    if not hasattr(settings, 'GEMINI_API_KEY') or not settings.GEMINI_API_KEY:
        return None
    return genai.GenerativeModel(model_name)

def extract_product_attributes(description):
    """
    Usa Gemini para extraer atributos de un producto desde una descripción textual normalizados al catálogo.
    """
    from .models import Categoria, Color, Tela

    # Obtener valores del catálogo para normalización
    categorias = list(Categoria.objects.exclude(nombre="Sin definir").values_list('nombre', flat=True))
    colores = list(Color.objects.exclude(nombre="Sin definir").values_list('nombre', flat=True))
    telas = list(Tela.objects.all().values_list('nombre', flat=True))
    tallas = ["U", "XS", "S", "M", "L", "XL", "2", "4", "6", "8", "10", "12", "14", "16"]

    model = get_gemini_model()
    if not model:
        return None

    prompt = f"""Analiza la siguiente descripción de un producto de boutique y extrae sus atributos en formato JSON.
Debes normalizar los valores basándote ÚNICAMENTE en las opciones del catálogo proporcionadas.

DESCRIPCIÓN: "{description}"

CATÁLOGO DE REFERENCIA:
- Categorías: {', '.join(categorias)}
- Colores: {', '.join(colores)}
- Telas: {', '.join(telas)}
- Tallas: {', '.join(tallas)}

FORMATO JSON ESPERADO:
{{
  "categoria": "Valor del catálogo o null",
  "rasgo1": "Texto libre corto (Modelo/Estilo)",
  "rasgo2": "Valor del catálogo de telas o null",
  "color": "Valor del catálogo o null",
  "talla": "Valor del catálogo o null (Default: U)",
  "precio": 0,
  "confianza": 0.0 a 1.0
}}

Si no estás seguro de un campo según el catálogo, devuelve null. Responde ÚNICAMENTE el JSON."""

    try:
        response = model.generate_content(prompt)
        # Limpiar respuesta por si trae markdown
        text = response.text.strip()
        if text.startswith('```json'):
            text = text[7:-3].strip()
        elif text.startswith('```'):
            text = text[3:-3].strip()

        return json.loads(text)
    except Exception as e:
        logger.error(f"Error extraendo atributos con Gemini: {e}")
        return None

import time

def analyze_product_image(image_data, mime_type='image/jpeg'):
    """
    Usa Gemini Vision para analizar una imagen de una prenda y extraer atributos normalizados al catálogo.
    """
    start_time = time.time()
    # Normalizar mime_type — Gemini acepta jpeg, png, webp, heic, heif
    if not mime_type or mime_type == 'application/octet-stream':
        mime_type = 'image/jpeg'
    logger.info("AI Analysis: Starting image analysis with Gemini Vision")
    from .models import Categoria, Color, Tela

    # Obtener valores del catálogo para normalización
    categorias = list(Categoria.objects.exclude(nombre__icontains='sin definir').values_list('nombre', flat=True))
    colores = list(Color.objects.exclude(nombre__icontains='sin definir').values_list('nombre', flat=True))
    telas = list(Tela.objects.all().values_list('nombre', flat=True))
    tallas = ["U", "XS", "S", "M", "L", "XL", "2", "4", "6", "8", "10", "12", "14", "16"]

    model = get_gemini_model()
    if not model:
        return None

    prompt = f"""Analiza esta prenda de ropa y extrae sus atributos en formato JSON para un sistema de inventario de boutique de vestidos de novia y quinceañera en México.
Debes normalizar los valores basándote ÚNICAMENTE en las opciones del catálogo proporcionadas.

CATÁLOGO:
- Categorías disponibles: {', '.join(categorias) if categorias else 'Novias, Quinceañera, Damas, Accesorios'}
- Colores disponibles: {', '.join(colores) if colores else 'Blanco, Rosa, Aqua, Vino, Champagne'}
- Telas disponibles: {', '.join(telas) if telas else 'Satín, Encaje, Chiffón, Tul, Mikado'}
- Tallas: {', '.join(tallas)}

INSTRUCCIONES:
1. Devuelve null si no puedes identificar un valor con seguridad razonable — NO inventes ni uses "Sin definir".
2. rasgo1 = modelo/corte del vestido (ej: Sirena, A-line, Princesa, Con cola, Sin manga).
3. rasgo2 = material/tela del catálogo o null.
4. precio_sugerido = estimado en pesos MXN según calidad visible (entre 800 y 8000).

FORMATO JSON (responde SOLO el JSON, sin explicaciones):
{{
  "categoria": "opción exacta del catálogo o null",
  "rasgo1": "descripción corta del modelo/corte o null",
  "rasgo2": "opción exacta de telas del catálogo o null",
  "color": "opción exacta del catálogo o null",
  "talla": "U",
  "precio_sugerido": 0,
  "confianza": 0.0
}}"""

    try:
        response = model.generate_content([
            prompt,
            {'mime_type': mime_type, 'data': image_data}
        ])
        duration = time.time() - start_time
        logger.info(f"AI Analysis: Gemini Vision response received in {duration:.2f}s")

        text = response.text.strip()
        if text.startswith('```json'):
            text = text[7:-3].strip()
        elif text.startswith('```'):
            text = text[3:-3].strip()

        return json.loads(text)
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"AI Analysis: Error after {duration:.2f}s: {e}")
        return None

def analyze_duplicate_ai(new_product, existing_products):
    """
    Analiza si un producto nuevo es duplicado de los existentes con consejos accionables.
    """
    model = get_gemini_model()
    if not model:
        return "Error: API Key no configurada"

    prompt = f"""Analiza si este producto NUEVO podría ser duplicado de alguno existente en Adelé Boutique.

PRODUCTO NUEVO:
{json.dumps(new_product, indent=2)}

PRODUCTOS EXISTENTES SIMILARES:
{existing_products}

REGLAS DE NEGOCIO:
- Diferente tela/material = productos DIFERENTES (ej: Crepé vs Seda).
- Colores parecidos pero con nombre distinto = productos DIFERENTES (ej: Rosa Palo vs Rosa Mauve).
- Mismo modelo, misma tela, mismo color, misma talla = POSIBLE DUPLICADO.

RESPONDE DE FORMA DIRECTA Y ACCIONABLE (Máximo 3 oraciones):
1. ¿Es duplicado? (Indica probabilidad Alta/Media/Baja).
2. Acción recomendada: "Usar SKU existente" o "Crear como nueva variante".
3. Nota sobre qué lo hace diferente si aplica (ej: "Es la misma tela pero en talla XL")."""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error analizando duplicados con Gemini: {e}")
        return "Error en el análisis de IA"

def generate_sales_strategy(context_data):
    """
    Genera recomendaciones de venta basadas en datos de la boutique.
    """
    model = get_gemini_model()
    if not model:
        return "API Key no disponible para generar estrategia."

    prompt = f"""Eres un consultor de retail experto. Analiza estos datos de Adelé Boutique y da 3-4 recomendaciones concretas.

DATOS:
{context_data}

Responde en español, práctico y breve (máximo 200 palabras). Usa emojis."""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error generando estrategia con Gemini: {e}")
        return "Error al conectar con el servicio de IA."
