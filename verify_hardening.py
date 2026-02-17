from playwright.sync_api import sync_playwright, expect
import os

def verify_frontend():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Login
        page.goto("http://localhost:8000/login/")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "admin123")
        page.click('button[type="submit"]')

        # Select profile (Admin)
        page.wait_for_url("**/perfiles/")
        page.click('text=Admin')

        # Authenticate profile
        page.wait_for_url("**/perfiles/autenticar/**")
        page.fill('input[name="password"]', "admin123")
        page.click('button[type="submit"]')

        # Wait for either dashboard or apertura-caja
        page.wait_for_load_state('networkidle')

        if "/apertura-caja/" in page.url:
            page.fill('input[name="monto_apertura"]', "1000")
            page.click('button[type="submit"]')

        # Explicitly go to POS
        page.goto("http://localhost:8000/pos/")
        page.wait_for_url("**/pos/")

        # Open Venta Rápida Modal
        page.click('[data-testid="btn-venta-rapida"]')
        modal = page.locator('[data-testid="venta-rapida-modal"]')

        # Test numeric hardening: clear price and blur
        precio_input = modal.locator('input[name="precio"]')
        precio_input.fill("")
        # Click somewhere else to blur
        modal.locator('text=Tipo de Operación').click()

        # Expect value to be "0"
        expect(precio_input).to_have_value("0")
        print("POS Price input hardening verified.")

        # Test anticipo in Venta Rápida
        anticipo_input = modal.locator('input[name="anticipo"]')
        anticipo_input.fill("")
        modal.locator('text=Tipo de Operación').click()
        expect(anticipo_input).to_have_value("0")
        print("POS Anticipo input hardening verified.")

        # Take screenshot
        page.screenshot(path="/home/jules/verification/pos_hardening.png")
        print("Screenshot saved.")

        browser.close()

if __name__ == "__main__":
    verify_frontend()
