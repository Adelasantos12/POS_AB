"""
Servicio de impresión de etiquetas Brother QL-800
Para Adelé Boutique (Gdl) - ByEasy POS
"""
import os
import logging
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Configuración de la impresora Brother QL-800
BROTHER_PRINTER_MODEL = 'QL-800'
BROTHER_LABEL_SIZE = '62'  # 62mm labels
BROTHER_BACKEND = 'pyusb'  # USB connection

def get_brother_printer():
    """Detecta y retorna la impresora Brother QL-800 conectada por USB"""
    try:
        from brother_ql.backends.helpers import discover
        from brother_ql.backends import backend_factory
        
        # Descubrir impresoras conectadas
        available_devices = discover(backend_identifier=BROTHER_BACKEND)
        
        if not available_devices:
            logger.warning("No se encontró impresora Brother QL conectada")
            return None, "No se encontró impresora Brother QL-800 conectada por USB"
        
        # Usar la primera impresora encontrada
        printer_identifier = available_devices[0]['identifier']
        logger.info(f"Impresora encontrada: {printer_identifier}")
        
        return printer_identifier, None
        
    except ImportError:
        return None, "Librería brother_ql no instalada. Ejecuta: pip install brother_ql"
    except Exception as e:
        logger.error(f"Error al detectar impresora: {e}")
        return None, f"Error al detectar impresora: {str(e)}"


def crear_imagen_etiqueta(producto, width=696, height=271):
    """
    Crea una imagen de etiqueta para el producto
    Tamaño optimizado para etiquetas Brother 62mm
    """
    # Crear imagen blanca
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Intentar cargar fuentes del sistema
    try:
        font_grande = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        font_mediana = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        font_pequeña = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except:
        font_grande = ImageFont.load_default()
        font_mediana = ImageFont.load_default()
        font_pequeña = ImageFont.load_default()
    
    # Dibujar contenido
    y_pos = 15
    
    # Categoría
    draw.text((20, y_pos), producto.categoria.nombre.upper(), fill='black', font=font_grande)
    y_pos += 40
    
    # Rasgos
    rasgo_texto = f"{producto.rasgo1}"
    if producto.rasgo2:
        rasgo_texto += f" | {producto.rasgo2}"
    draw.text((20, y_pos), rasgo_texto, fill='black', font=font_mediana)
    y_pos += 30
    
    # Color y Talla
    draw.text((20, y_pos), f"Color: {producto.color.nombre}  |  Talla: {producto.talla}", fill='gray', font=font_pequeña)
    y_pos += 25
    
    # Línea separadora
    draw.line([(20, y_pos), (width - 20, y_pos)], fill='lightgray', width=1)
    y_pos += 10
    
    # Precio
    precio_texto = f"${producto.precio_venta:,.0f}"
    draw.text((20, y_pos), precio_texto, fill='black', font=font_grande)
    
    # SKU a la derecha
    draw.text((width - 200, y_pos + 5), f"SKU: {producto.sku}", fill='gray', font=font_pequeña)
    y_pos += 45
    
    # Código de barras (si existe)
    if producto.barcode_image:
        try:
            barcode_path = producto.barcode_image.path
            barcode_img = Image.open(barcode_path)
            barcode_img = barcode_img.resize((200, 50))
            img.paste(barcode_img, (width - 220, y_pos))
        except:
            pass
    
    # Nombre de la tienda
    draw.text((20, height - 30), "Adelé Boutique (Gdl)", fill='lightgray', font=font_pequeña)
    
    return img


def imprimir_etiqueta_brother(producto, cantidad=1):
    """
    Imprime etiqueta(s) para un producto en la Brother QL-800
    
    Args:
        producto: Instancia del modelo Producto
        cantidad: Número de etiquetas a imprimir
        
    Returns:
        dict: {success: bool, message: str}
    """
    try:
        from brother_ql.conversion import convert
        from brother_ql.backends.helpers import send
        from brother_ql.raster import BrotherQLRaster
        
        # Detectar impresora
        printer_id, error = get_brother_printer()
        if error:
            return {'success': False, 'message': error}
        
        # Crear imagen de etiqueta
        label_image = crear_imagen_etiqueta(producto)
        
        # Convertir a formato Brother
        qlr = BrotherQLRaster(BROTHER_PRINTER_MODEL)
        
        # Convertir imagen
        instructions = convert(
            qlr=qlr,
            images=[label_image],
            label=BROTHER_LABEL_SIZE,
            rotate='auto',
            threshold=70.0,
            dither=False,
            compress=False,
            red=False,
            dpi_600=False,
            hq=True,
            cut=True
        )
        
        # Imprimir la cantidad solicitada
        for i in range(cantidad):
            send(
                instructions=instructions,
                printer_identifier=printer_id,
                backend_identifier=BROTHER_BACKEND,
                blocking=True
            )
        
        logger.info(f"Etiquetas impresas: {cantidad} para producto {producto.sku}")
        return {
            'success': True, 
            'message': f'✅ {cantidad} etiqueta(s) impresa(s) para {producto.sku}'
        }
        
    except ImportError as e:
        return {
            'success': False,
            'message': f'Librería no disponible: {str(e)}. Instala brother_ql.'
        }
    except Exception as e:
        logger.error(f"Error al imprimir etiqueta: {e}")
        return {
            'success': False,
            'message': f'Error al imprimir: {str(e)}'
        }


def generar_preview_etiqueta(producto):
    """
    Genera una imagen de preview de la etiqueta (sin imprimir)
    Retorna la imagen en formato base64 para mostrar en el frontend
    """
    import base64
    
    try:
        img = crear_imagen_etiqueta(producto)
        
        # Convertir a base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return {
            'success': True,
            'image_base64': f'data:image/png;base64,{img_base64}'
        }
        
    except Exception as e:
        logger.error(f"Error al generar preview: {e}")
        return {
            'success': False,
            'message': str(e)
        }


def verificar_impresora():
    """Verifica el estado de la impresora Brother"""
    printer_id, error = get_brother_printer()
    
    if error:
        return {
            'conectada': False,
            'mensaje': error,
            'modelo': None
        }
    
    return {
        'conectada': True,
        'mensaje': f'Impresora Brother {BROTHER_PRINTER_MODEL} conectada',
        'modelo': BROTHER_PRINTER_MODEL,
        'identificador': printer_id
    }
