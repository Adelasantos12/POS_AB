"""
Servicio de impresión de etiquetas Brother QL-800
Adelé Boutique (Gdl) — ByEasy POS

Cinta instalada : 62 mm  (DK-22243 o similar)
Tamaño de etiqueta: ~52 mm ancho × 17 mm alto

Cálculo de píxeles a 300 DPI:
  Cinta 62 mm → 696 px de área imprimible
  Alto  17 mm → 201 px  (17/25.4*300 ≈ 201)

Layout (696 × 201 px):
  ┌──────────────────────────────────────────────┐
  │ ████████████ barcode ████████████  $1,200    │
  │                                   T: M       │
  │  SKU-0042                                    │
  └──────────────────────────────────────────────┘
"""
import logging
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── Configuración ────────────────────────────────────────────────────────────
BROTHER_PRINTER_MODEL = 'QL-800'
BROTHER_LABEL_SIZE    = '62'      # cinta 62 mm (DK-22243)
BROTHER_BACKEND       = 'pyusb'

LABEL_W  = 696   # px — 62 mm tape at 300 DPI
LABEL_H  = 201   # px — 17 mm at 300 DPI  (17 / 25.4 * 300 ≈ 201)
MARGIN_X = 18    # px lateral
MARGIN_Y = 8     # px superior/inferior

# Franja reservada para SKU al pie del barcode
SKU_STRIP_H = 28  # px


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


# ── Helpers de fuente ────────────────────────────────────────────────────────

def _font(size, bold=False):
    """Carga fuente TTF del sistema; fallback a fuente por defecto."""
    paths_bold   = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/System/Library/Fonts/Helvetica.ttc"]
    paths_normal = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/System/Library/Fonts/Helvetica.ttc"]
    paths = paths_bold if bold else paths_normal
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


# ── Diseño de etiqueta ───────────────────────────────────────────────────────

def crear_imagen_etiqueta(producto):
    """
    Genera imagen de etiqueta para 62 mm × 17 mm (696 × 201 px a 300 DPI).

    Layout:
      • Zona izquierda  — código de barras (alto = LABEL_H - 2*MARGIN_Y - SKU_STRIP_H)
      • Zona derecha    — precio en grande + talla debajo
      • Franja inferior — SKU en letra pequeña debajo del barcode
      Sin barcode: SKU centrado + precio a la derecha.
    """
    img  = Image.new('RGB', (LABEL_W, LABEL_H), color='white')
    draw = ImageDraw.Draw(img)

    content_w = LABEL_W - 2 * MARGIN_X   # ≈ 660 px

    # Fuentes
    f_price = _font(48, bold=True)   # precio  — zona derecha
    f_talla = _font(26, bold=False)  # talla   — zona derecha
    f_sku   = _font(20, bold=False)  # SKU     — franja inferior

    sku_text   = producto.sku or ""
    precio_text = f"${producto.precio_venta:,.0f}" if producto.precio_venta else "$---"
    talla_text  = f"T: {producto.talla}" if producto.talla else ""

    # Altura disponible para el barcode (sin franja SKU)
    bc_zone_h = LABEL_H - 2 * MARGIN_Y - SKU_STRIP_H   # ≈ 157 px

    barcode_placed = False
    bc_w = 0

    if producto.barcode_image:
        try:
            from PIL import Image as PilImage

            try:
                bc_img = PilImage.open(producto.barcode_image.path)
            except Exception:
                import urllib.request, tempfile, os
                url = producto.barcode_image.url
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                tmp.close()
                urllib.request.urlretrieve(url, tmp.name)
                bc_img = PilImage.open(tmp.name)
                os.unlink(tmp.name)

            # Escalar manteniendo proporción; máximo 62 % del ancho útil
            bc_h = bc_zone_h
            bc_w = int(bc_img.width * bc_h / bc_img.height)
            bc_w = min(bc_w, int(content_w * 0.62))
            bc_img = bc_img.convert('RGB').resize((bc_w, bc_h), Image.LANCZOS)
            img.paste(bc_img, (MARGIN_X, MARGIN_Y))
            barcode_placed = True

        except Exception as exc:
            logger.warning(f"No se pudo cargar barcode para {producto.sku}: {exc}")

    # ── Zona derecha: precio + talla ─────────────────────────────────────────
    right_x = MARGIN_X + bc_w + 14 if barcode_placed else MARGIN_X + int(content_w * 0.62) + 14
    right_w = LABEL_W - MARGIN_X - right_x

    if right_w > 40:
        # Precio — alineado arriba en zona derecha
        price_w = draw.textlength(precio_text, font=f_price)
        if price_w > right_w:
            # Reducir fuente si no cabe
            f_price = _font(34, bold=True)
            price_w = draw.textlength(precio_text, font=f_price)
        price_y = MARGIN_Y + max(0, (bc_zone_h - 48 - (30 if talla_text else 0)) // 2)
        draw.text((right_x, price_y), precio_text, fill='black', font=f_price)

        # Talla — debajo del precio
        if talla_text:
            talla_y = price_y + 52
            draw.text((right_x, talla_y), talla_text, fill='#444444', font=f_talla)

    # ── Franja inferior: SKU ─────────────────────────────────────────────────
    sku_y = LABEL_H - MARGIN_Y - SKU_STRIP_H + 4
    if sku_text:
        if barcode_placed:
            # Alineado bajo el barcode
            draw.text((MARGIN_X, sku_y), sku_text, fill='#555555', font=f_sku)
        else:
            # Sin barcode: SKU centrado grande
            f_sku_big = _font(28, bold=True)
            sku_bw = draw.textlength(sku_text, font=f_sku_big)
            draw.text(((LABEL_W - sku_bw) / 2, MARGIN_Y + 10), sku_text,
                      fill='black', font=f_sku_big)

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

        label_image = crear_imagen_etiqueta(producto)

        qlr = BrotherQLRaster(BROTHER_PRINTER_MODEL)
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
