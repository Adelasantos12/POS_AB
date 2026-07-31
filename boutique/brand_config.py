"""
IDENTITY SLOT — reemplaza solo este archivo al cambiar de cliente.
El POS, tickets, modales y lógica de negocio no tocan estos valores directamente.
Para un segundo cliente: crear brand/<slug>/brand_config.py con los mismos keys
y apuntar BoutiqueConfig.brand_config_module al nuevo módulo.
"""

IDENTITY = {
    # ── Presencia ──────────────────────────────────────────────────────
    "BRAND_NAME":          "Adelé Boutique",
    "BRAND_TAGLINE":       "Alta moda nupcial · Cuernavaca",
    "BRAND_PROFILE_SLUG":  "adele_boutique",
    "BRAND_LOGO_PATH":     "brand/adele/logo.svg",   # opcional

    # ── Paleta (CSS custom properties) ─────────────────────────────────
    "BRAND_PRIMARY":       "#9D174D",
    "BRAND_SECONDARY":     "#F9A8D4",

    # ── Tickets PDF — ReportLab usa RGB fraccional ─────────────────────
    "BRAND_RECEIPT_RGB":   (0.616, 0.090, 0.302),

    # ── Tipografía display ──────────────────────────────────────────────
    "BRAND_FONT_FILE":     "brand/adele/adelia.ttf",
    "BRAND_FONT_FALLBACK": "'Playfair Display', Georgia, serif",
}
