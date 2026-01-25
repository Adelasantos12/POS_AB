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
    Usa Gemini para extraer atributos de un producto desde una descripción textual.
    Retorna un diccionario con los campos identificados.
    """
    model = get_gemini_model()
    if not model:
        return None

    prompt = f"""Analiza la siguiente descripción de un producto de boutique y extrae sus atributos en formato JSON.

DESCRIPCIÓN: "{description}"

CATÁLOGO DE REFERENCIA (Si aplica):
- Categorías comunes: Vestido, Blusa, Pantalón, Falda, Accesorio, Velo, Tocado.
- Tallas comunes: U (Única), S, M, L, XL, 2, 4, 6, 8, 10, 12, 14, 16.

FORMATO JSON ESPERADO:
{{
  "categoria": "Nombre de la categoría",
  "rasgo1": "Modelo o Estilo (ej: Manga Larga, Escote V)",
  "rasgo2": "Material o Tela (ej: Seda, Encaje, Satín)",
  "color": "Color específico",
  "talla": "Talla identificada (Default: U)",
  "precio": 0,
  "confianza": 0.0 a 1.0
}}

Si no estás seguro de un campo, deja el valor por defecto o vacío. Responde ÚNICAMENTE el JSON."""

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

def analyze_duplicate_ai(new_product, existing_products):
    """
    Analiza si un producto nuevo es duplicado de los existentes.
    """
    model = get_gemini_model()
    if not model:
        return "Error: API Key no configurada"

    prompt = f"""Analiza si este producto NUEVO podría ser duplicado de alguno existente en Adelé Boutique.

PRODUCTO NUEVO:
{json.dumps(new_product, indent=2)}

PRODUCTOS EXISTENTES SIMILARES:
{existing_products}

REGLAS:
- Mismo modelo en diferente tela/material = productos DIFERENTES
- Colores parecidos (ej: Rosa palo vs Rosa mauve) = productos DIFERENTES
- Mismo modelo, misma tela, mismo color, misma talla = POSIBLE DUPLICADO

Responde en máximo 2 oraciones:
1. ¿Es probable que sea duplicado? (Sí/No/Verificar)
2. Recomendación breve."""

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
