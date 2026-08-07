"""
Servicio de impresión de etiquetas Brother QL-800
Adelé Boutique (Gdl) — ByEasy POS

Cinta instalada : 62 mm continua (DK-22243 o similar)
Largo de etiqueta: 20 mm  (el QL-800 corta según el alto de la imagen)

Cálculo de píxeles a 300 DPI:
  Cinta 62 mm  → 696 px de área imprimible
  Alto  20 mm  → 236 px  (20 / 25.4 * 300 ≈ 236)

Layout (696 × 236 px):
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
BROTHER_LABEL_SIZE    = '62'      # cinta continua 62 mm (DK-22243); corta a LABEL_H
BROTHER_BACKEND       = 'pyusb'

# 62 mm tape at 300 DPI → 696 px printable width; 20 mm height → 236 px
LABEL_W  = 696   # px
LABEL_H  = 236   # px

MARGIN_X = 20    # px lateral (~1.7 mm cada lado)
MARGIN_Y = 10    # px superior/inferior

SKU_STRIP_H = 30  # px — franja inferior para SKU


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


# ── Diseño de etiqueta ───────────────────────────────────────────────────────

def crear_imagen_etiqueta(producto):
    """
    Genera imagen landscape 566 × 165 px para DK-11204.

    brother_ql rotate='auto' la rota a portrait (165 × 566) al enviarla
    a la impresora, de modo que ocupe el ancho completo de la cinta.
    """
    img  = Image.new('RGB', (LABEL_W, LABEL_H), color='white')
    draw = ImageDraw.Draw(img)

    sku_text    = producto.sku or ""
    precio_text = f"${producto.precio_venta:,.0f}" if producto.precio_venta else "$---"
    talla_text  = f"T: {producto.talla}" if producto.talla else ""
    color_text  = producto.color.nombre.upper() if getattr(producto, 'color', None) else ""

    # Fuentes
    f_price = _font(52, bold=True)
    f_talla = _font(28, bold=False)
    f_color = _font(22, bold=True)
    f_sku   = _font(20, bold=False)

    # Altura disponible para el barcode (sin franja SKU ni márgenes)
    bc_zone_h = LABEL_H - 2 * MARGIN_Y - SKU_STRIP_H   # ≈ 129 px

    barcode_placed = False
    bc_w = 0

    if producto.barcode_image:
        try:
            from PIL import Image as PilImage

            try:
                bc_img = PilImage.open(producto.barcode_image.path)
            except Exception:
                import urllib.request, tempfile, os
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                tmp.close()
                urllib.request.urlretrieve(producto.barcode_image.url, tmp.name)
                bc_img = PilImage.open(tmp.name)
                os.unlink(tmp.name)

            bc_h = bc_zone_h
            bc_w = int(bc_img.width * bc_h / bc_img.height)
            bc_w = min(bc_w, int((LABEL_W - 2 * MARGIN_X) * 0.60))
            bc_img = bc_img.convert('RGB').resize((bc_w, bc_h), Image.LANCZOS)
            img.paste(bc_img, (MARGIN_X, MARGIN_Y))
            barcode_placed = True

        except Exception as exc:
            logger.warning(f"No se pudo cargar barcode para {producto.sku}: {exc}")

    # ── Zona derecha: precio + talla ─────────────────────────────────────────
    right_x = MARGIN_X + bc_w + 14 if barcode_placed else int(LABEL_W * 0.55)
    right_w = LABEL_W - MARGIN_X - right_x

    if right_w > 40:
        price_w = draw.textlength(precio_text, font=f_price)
        if price_w > right_w:
            f_price = _font(38, bold=True)
            price_w = draw.textlength(precio_text, font=f_price)

        mid_h = 56 + (32 if talla_text else 0) + (28 if color_text else 0)
        price_y = MARGIN_Y + max(0, (bc_zone_h - mid_h) // 2)
        draw.text((right_x, price_y), precio_text, fill='black', font=f_price)

        next_y = price_y + 58
        if talla_text:
            draw.text((right_x, next_y), talla_text, fill='#222222', font=f_talla)
            next_y += 32
        if color_text:
            draw.text((right_x, next_y), color_text, fill='black', font=f_color)

    # ── Franja inferior: SKU ─────────────────────────────────────────────────
    sku_y = LABEL_H - MARGIN_Y - SKU_STRIP_H + 3
    if sku_text:
        if barcode_placed:
            draw.text((MARGIN_X, sku_y), sku_text, fill='#222222', font=f_sku)
        else:
            f_sku_big = _font(26, bold=True)
            sku_bw = draw.textlength(sku_text, font=f_sku_big)
            draw.text(((LABEL_W - sku_bw) / 2, MARGIN_Y + 8), sku_text,
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

        label_image = crear_imagen_etiqueta(producto).convert('L')

        qlr = BrotherQLRaster(BROTHER_PRINTER_MODEL)
        instructions = convert(
            qlr=qlr,
            images=[label_image],
            label=BROTHER_LABEL_SIZE,
            rotate='0',           # imagen ya tiene el ancho correcto para cinta 62 mm
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
