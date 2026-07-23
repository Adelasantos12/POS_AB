"""
Servicio de impresión de etiquetas Brother QL-800
Adelé Boutique (Gdl) — ByEasy POS

Etiqueta física : DK-11204  (17 mm × 54 mm die-cut)
Área imprimible : 165 × 566 px a 300 DPI  (~14 mm × 48 mm)

Se genera la imagen en orientación landscape (566 × 165 px).
brother_ql rotate='auto' la rota 90° al imprimir sobre la cinta de 17 mm.

Layout (566 × 165 px → impreso como 165 × 566 en la cinta):
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
BROTHER_LABEL_SIZE    = '17x54'   # DK-11204: 17 mm × 54 mm die-cut
BROTHER_BACKEND       = 'pyusb'

# Área imprimible para DK-11204 a 300 DPI (portrait nativo):
#   165 px ancho × 566 px largo  →  diseñamos en landscape 566 × 165
LABEL_W  = 566   # px — largo de la etiqueta (54 mm en el feed)
LABEL_H  = 165   # px — ancho imprimible    (17 mm a través de la cinta)

MARGIN_X = 10    # px lateral
MARGIN_Y = 6     # px superior/inferior

SKU_STRIP_H = 24  # px — franja inferior para SKU


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

    # Fuentes
    f_price = _font(44, bold=True)
    f_talla = _font(24, bold=False)
    f_sku   = _font(17, bold=False)

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
            bc_w = min(bc_w, int((LABEL_W - 2 * MARGIN_X) * 0.62))
            bc_img = bc_img.convert('RGB').resize((bc_w, bc_h), Image.LANCZOS)
            img.paste(bc_img, (MARGIN_X, MARGIN_Y))
            barcode_placed = True

        except Exception as exc:
            logger.warning(f"No se pudo cargar barcode para {producto.sku}: {exc}")

    # ── Zona derecha: precio + talla ─────────────────────────────────────────
    right_x = MARGIN_X + bc_w + 12 if barcode_placed else int(LABEL_W * 0.55)
    right_w = LABEL_W - MARGIN_X - right_x

    if right_w > 40:
        price_w = draw.textlength(precio_text, font=f_price)
        if price_w > right_w:
            f_price = _font(32, bold=True)
            price_w = draw.textlength(precio_text, font=f_price)

        mid_h = 44 + (28 if talla_text else 0)
        price_y = MARGIN_Y + max(0, (bc_zone_h - mid_h) // 2)
        draw.text((right_x, price_y), precio_text, fill='black', font=f_price)

        if talla_text:
            draw.text((right_x, price_y + 48), talla_text, fill='#444444', font=f_talla)

    # ── Franja inferior: SKU ─────────────────────────────────────────────────
    sku_y = LABEL_H - MARGIN_Y - SKU_STRIP_H + 3
    if sku_text:
        if barcode_placed:
            draw.text((MARGIN_X, sku_y), sku_text, fill='#666666', font=f_sku)
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

        label_image = crear_imagen_etiqueta(producto)

        qlr = BrotherQLRaster(BROTHER_PRINTER_MODEL)
        instructions = convert(
            qlr=qlr,
            images=[label_image],
            label=BROTHER_LABEL_SIZE,
            rotate='auto',        # rota la imagen landscape 90° para la cinta de 17 mm
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
