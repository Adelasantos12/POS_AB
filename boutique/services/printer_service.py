"""
Servicio de impresión de etiquetas Brother QL-800
Adelé Boutique (Gdl) — ByEasy POS

Cinta instalada : 62 mm  (DK-22243 o similar)
Tamaño de etiqueta deseado: 52 mm ancho × 20 mm alto

Cálculo de píxeles a 300 DPI:
  Cinta 62 mm → 696 px de área imprimible
  Alto  20 mm → 236 px de alto
  El contenido útil se centra en los 696 px de ancho;
  equivale a ~52 mm de contenido con márgenes laterales de ~5 mm c/u.
"""
import logging
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── Configuración ────────────────────────────────────────────────────────────
BROTHER_PRINTER_MODEL = 'QL-800'
BROTHER_LABEL_SIZE    = '62'      # cinta 62 mm (DK-22243); cambiar a '54' si usas 54 mm
BROTHER_BACKEND       = 'pyusb'   # USB directo

# Dimensiones de imagen a 300 DPI para cinta 62 mm × etiqueta 20 mm de largo
LABEL_W = 696   # px de ancho imprimible para cinta 62 mm
LABEL_H = 236   # px = 20 mm a 300 DPI  (20 / 25.4 * 300 ≈ 236)

# Márgenes laterales para centrar el contenido en ~52 mm
MARGIN_X = 25   # px ≈ 2 mm de cada lado → contenido útil ≈ 646 px ≈ 54.6 mm
MARGIN_Y = 10   # px de margen superior/inferior

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
    Genera la imagen de etiqueta optimizada para 62 mm × 20 mm.

    Layout (696 × 236 px):
      ┌──────────────────────────────────────────┐
      │ CATEGORÍA            TALLA: M   SKU:...  │  ← fila 1  (info compacta)
      │ ─────────────────────────────────────────│
      │ $1,200              Color: Blanco Satín  │  ← fila 2  (precio + attr)
      │ ─────────────────────────────────────────│
      │ ██████ barcode ██████   ADELE-0042       │  ← fila 3  (código de barras)
      └──────────────────────────────────────────┘
    """
    img  = Image.new('RGB', (LABEL_W, LABEL_H), color='white')
    draw = ImageDraw.Draw(img)

    content_w = LABEL_W - 2 * MARGIN_X   # 646 px
    x0 = MARGIN_X

    # Fuentes
    f_big   = _font(52, bold=True)   # precio
    f_med   = _font(30, bold=False)  # atributos
    f_small = _font(22, bold=False)  # SKU / etiqueta
    f_cat   = _font(26, bold=True)   # categoría

    # ── Fila 1: Categoría + Talla + SKU ──────────────────────────────────────
    y1 = MARGIN_Y
    cat_text   = (producto.categoria.nombre if producto.categoria else "---").upper()
    talla_text = f"T: {producto.talla}" if producto.talla else ""
    sku_text   = producto.sku or ""

    draw.text((x0, y1), cat_text, fill='black', font=f_cat)
    if talla_text:
        # Alineado a la derecha
        talla_w = draw.textlength(talla_text, font=f_med)
        draw.text((LABEL_W - MARGIN_X - talla_w, y1 + 2), talla_text, fill='#333333', font=f_med)

    y1 += 32
    # Línea divisoria fina
    draw.line([(x0, y1), (LABEL_W - MARGIN_X, y1)], fill='#CCCCCC', width=1)

    # ── Fila 2: Precio + Color/Material ──────────────────────────────────────
    y2 = y1 + 6
    precio_text = f"${producto.precio_venta:,.0f}" if producto.precio_venta else "$---"
    draw.text((x0, y2), precio_text, fill='black', font=f_big)

    # Color y material (rasgo1/rasgo2) a la derecha del precio
    color_nombre = producto.color.nombre if producto.color else ""
    rasgo2       = producto.rasgo2 or (producto.tela.nombre if producto.tela else "")
    attr_parts   = [p for p in [color_nombre, rasgo2] if p]
    attr_text    = "  ·  ".join(attr_parts)
    if attr_text:
        attr_w = draw.textlength(attr_text, font=f_med)
        draw.text((LABEL_W - MARGIN_X - attr_w, y2 + 14), attr_text, fill='#555555', font=f_med)

    y2 += 62
    draw.line([(x0, y2), (LABEL_W - MARGIN_X, y2)], fill='#CCCCCC', width=1)

    # ── Fila 3: Código de barras + SKU ───────────────────────────────────────
    y3 = y2 + 5
    barcode_placed = False

    if producto.barcode_image:
        try:
            from PIL import Image as PilImage
            # barcode_image puede ser Cloudinary URL o archivo local
            try:
                bc_img = PilImage.open(producto.barcode_image.path)
            except Exception:
                import urllib.request
                import tempfile, os
                url = producto.barcode_image.url
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                tmp.close()
                urllib.request.urlretrieve(url, tmp.name)
                bc_img = PilImage.open(tmp.name)
                os.unlink(tmp.name)

            bc_h = LABEL_H - y3 - MARGIN_Y          # altura disponible restante
            bc_w = int(bc_img.width * bc_h / bc_img.height)
            bc_w = min(bc_w, int(content_w * 0.70))  # máximo 70 % del ancho
            bc_img = bc_img.convert('RGB').resize((bc_w, bc_h), Image.LANCZOS)
            img.paste(bc_img, (x0, y3))
            barcode_placed = True

            # SKU a la derecha del barcode
            sku_x = x0 + bc_w + 10
            if sku_x + 60 < LABEL_W - MARGIN_X:
                draw.text((sku_x, y3 + 4),      sku_text,   fill='#333333', font=f_small)
        except Exception as exc:
            logger.warning(f"No se pudo cargar barcode para {producto.sku}: {exc}")

    if not barcode_placed:
        # Sin barcode: mostrar SKU centrado
        sku_w = draw.textlength(sku_text, font=f_med)
        draw.text(((LABEL_W - sku_w) / 2, y3 + 5), sku_text, fill='#555555', font=f_med)

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
