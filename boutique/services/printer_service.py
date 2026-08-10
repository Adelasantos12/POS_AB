"""
Servicio de impresión de etiquetas Brother QL-800
Adelé Boutique (Gdl) — ByEasy POS

Cinta instalada : 29 mm × 90 mm troquelada (DK-11210 o compatible)

Cálculo de píxeles a 300 DPI:
  Ancho imprimible 29 mm → 306 px
  Alto troquelado  90 mm → 991 px

Layout portrait (306 × 991 px):
  ┌──────────────────┐
  │  $1,200          │  precio (grande)
  │  T: M   AZUL     │  talla + color
  │                  │
  │  ▌▌▌▌▌▌▌▌▌▌▌▌   │  código de barras (centrado)
  │                  │
  │  SKU-0042        │  SKU al pie
  └──────────────────┘
"""
import logging
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── Configuración ────────────────────────────────────────────────────────────
BROTHER_PRINTER_MODEL = 'QL-800'
BROTHER_LABEL_SIZE    = '29x90'   # DK-11210 / DK-11241 29 mm × 90 mm troquelada
BROTHER_BACKEND       = 'pyusb'

# 29 mm × 90 mm a 300 DPI → 306 × 991 px (área imprimible real)
LABEL_W  = 306   # px  (≈ 29 mm)
LABEL_H  = 991   # px  (≈ 90 mm)

MARGIN_X = 14    # px lateral
MARGIN_Y = 16    # px superior/inferior


# ── Detección de impresora ───────────────────────────────────────────────────

def get_brother_printer():
    """Detecta la primera Brother QL conectada por USB."""
    try:
        from brother_ql.backends.helpers import discover
        devices = discover(backend_identifier=BROTHER_BACKEND)
        if not devices:
            return None, "No se encontró impresora Brother QL-800 conectada por USB"
        printer_id = devices[0]['identifier']
        logger.info(f"Impresora encontrada: {printer_id}")
        return printer_id, None
    except ImportError:
        return None, "Librería brother_ql no instalada."
    except Exception as e:
        logger.error(f"Error detectando impresora: {e}")
        return None, f"Error: {e}"


# ── Helper de fuente ─────────────────────────────────────────────────────────

def _font(size, bold=False):
    """Carga fuente TTF del sistema; fallback a fuente por defecto."""
    paths_bold   = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/System/Library/Fonts/Helvetica.ttc"]
    paths_normal = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/System/Library/Fonts/Helvetica.ttc"]
    for p in (paths_bold if bold else paths_normal):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


# ── Diseño de etiqueta portrait 306 × 991 ───────────────────────────────────

def crear_imagen_etiqueta(producto):
    """
    Genera imagen portrait 306 × 991 px para etiqueta troquelada 29 × 90 mm.

    Zonas (de arriba hacia abajo):
      1. Precio + talla + color  (~220 px)
      2. Código de barras        (~580 px)
      3. SKU al pie              (~130 px)
    """
    img  = Image.new('RGB', (LABEL_W, LABEL_H), color='white')
    draw = ImageDraw.Draw(img)

    sku_text    = producto.sku or ""
    precio_text = f"${producto.precio_venta:,.0f}" if producto.precio_venta else "$---"
    talla_text  = f"T: {producto.talla}" if getattr(producto, 'talla', None) else ""
    color_text  = producto.color.nombre.upper() if getattr(producto, 'color', None) else ""

    # Fuentes
    f_price  = _font(46, bold=True)
    f_talla  = _font(26, bold=False)
    f_color  = _font(22, bold=True)
    f_sku    = _font(22, bold=False)

    printable_w = LABEL_W - 2 * MARGIN_X   # 278 px

    # ── Zona 1: Precio ───────────────────────────────────────────────────────
    y = MARGIN_Y
    price_w = draw.textlength(precio_text, font=f_price)
    if price_w > printable_w:
        f_price = _font(32, bold=True)
        price_w = draw.textlength(precio_text, font=f_price)
    draw.text(((LABEL_W - price_w) / 2, y), precio_text, fill='black', font=f_price)
    y += 54

    # Talla + color en una misma línea
    if talla_text or color_text:
        line = f"{talla_text}  {color_text}".strip()
        line_w = draw.textlength(line, font=f_talla)
        # Si color no cabe junto a talla, usa solo talla en esta línea
        if line_w > printable_w:
            draw.text((MARGIN_X, y), talla_text, fill='#333333', font=f_talla)
            y += 32
            color_w = draw.textlength(color_text, font=f_color)
            draw.text(((LABEL_W - color_w) / 2, y), color_text, fill='black', font=f_color)
            y += 30
        else:
            draw.text(((LABEL_W - line_w) / 2, y), line, fill='#333333', font=f_talla)
            y += 34

    y += 10  # espacio antes del barcode

    # ── Zona 2: Código de barras ─────────────────────────────────────────────
    bc_area_h = LABEL_H - y - MARGIN_Y - 46 - 10   # reserva pie para SKU

    if producto.barcode_image and bc_area_h > 40:
        try:
            try:
                bc_img = Image.open(producto.barcode_image.path)
            except Exception:
                import urllib.request, tempfile, os
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                tmp.close()
                urllib.request.urlretrieve(producto.barcode_image.url, tmp.name)
                bc_img = Image.open(tmp.name)
                os.unlink(tmp.name)

            # Escala para que quepa en el ancho disponible manteniendo proporción
            bc_w_target = printable_w
            bc_h_target = int(bc_img.height * bc_w_target / bc_img.width)
            if bc_h_target > bc_area_h:
                bc_h_target = bc_area_h
                bc_w_target = int(bc_img.width * bc_h_target / bc_img.height)

            bc_img = bc_img.convert('RGB').resize((bc_w_target, bc_h_target), Image.LANCZOS)
            bc_x = (LABEL_W - bc_w_target) // 2
            img.paste(bc_img, (bc_x, y))
            y += bc_h_target
        except Exception as exc:
            logger.warning(f"No se pudo cargar barcode para {producto.sku}: {exc}")

    # ── Zona 3: SKU al pie ───────────────────────────────────────────────────
    if sku_text:
        sku_w = draw.textlength(sku_text, font=f_sku)
        sku_y = LABEL_H - MARGIN_Y - 28
        draw.text(((LABEL_W - sku_w) / 2, sku_y), sku_text, fill='#444444', font=f_sku)

    return img


# ── Impresión ─────────────────────────────────────────────────────────────────

def imprimir_etiqueta_brother(producto, cantidad=1):
    """Imprime etiqueta(s) en la Brother QL-800 por USB."""
    try:
        from brother_ql.conversion import convert
        from brother_ql.backends.helpers import send
        from brother_ql.raster import BrotherQLRaster

        printer_id, error = get_brother_printer()
        if error:
            return {'success': False, 'message': error}

        label_image = crear_imagen_etiqueta(producto).convert('L')

        qlr = BrotherQLRaster(BROTHER_PRINTER_MODEL)
        instructions = convert(
            qlr=qlr,
            images=[label_image],
            label=BROTHER_LABEL_SIZE,
            rotate='auto',        # la librería orienta automáticamente
            threshold=70,
            dither=False,
            compress=False,
            red=False,
            dpi_600=False,
            hq=True,
            cut=True,
        )

        for _ in range(cantidad):
            send(
                instructions=instructions,
                printer_identifier=printer_id,
                backend_identifier=BROTHER_BACKEND,
                blocking=True,
            )

        logger.info(f"Etiquetas impresas: {cantidad} × {producto.sku}")
        return {'success': True, 'message': f'✅ {cantidad} etiqueta(s) impresa(s) para {producto.sku}'}

    except ImportError as e:
        return {'success': False, 'message': f'Librería no disponible: {e}. Instala brother_ql.'}
    except Exception as e:
        logger.error(f"Error al imprimir etiqueta: {e}")
        return {'success': False, 'message': f'Error al imprimir: {e}'}


# ── Preview ───────────────────────────────────────────────────────────────────

def generar_preview_etiqueta(producto):
    """Devuelve la etiqueta como imagen base64 para previsualizar en el navegador."""
    import base64
    try:
        img = crear_imagen_etiqueta(producto)
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        return {'success': True, 'image_base64': f'data:image/png;base64,{b64}'}
    except Exception as e:
        logger.error(f"Error al generar preview: {e}")
        return {'success': False, 'message': str(e)}


# ── Estado ────────────────────────────────────────────────────────────────────

def verificar_impresora():
    """Verifica si la Brother QL-800 está conectada."""
    printer_id, error = get_brother_printer()
    if error:
        return {'conectada': False, 'mensaje': error, 'modelo': None}
    return {
        'conectada': True,
        'mensaje': f'Impresora Brother {BROTHER_PRINTER_MODEL} lista',
        'modelo': BROTHER_PRINTER_MODEL,
        'identificador': printer_id,
    }
