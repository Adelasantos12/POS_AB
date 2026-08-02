from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto("http://localhost:8000/login/")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "admin123")
        page.click('button[type="submit"]')
        time.sleep(2)

        # Check if we are at profile selection or already at dashboard
        if "/perfiles/" in page.url:
            # Select profile
            page.click('text=admin')
            time.sleep(1)
            page.fill('input[name="password"]', "admin123")
            page.click('button[type="submit"]')
            time.sleep(2)

        print(f"Current URL: {page.url}")
        page.screenshot(path="verification/dashboard.png")

        # POS Modal
        page.goto("http://localhost:8000/pos/")
        page.click('text=Venta Rápida')
        time.sleep(1)
        page.screenshot(path="verification/pos_venta_rapida.png")

        # Inventory Modal
        page.goto("http://localhost:8000/inventario/")
        page.click('text=Nuevo Producto')
        time.sleep(1)
        page.screenshot(path="verification/inventario_modal.png")

        # Pedidos Board (The new feature)
        page.goto("http://localhost:8000/pedidos/")
        time.sleep(1)
        page.screenshot(path="verification/pedidos_board.png")

        browser.close()

if __name__ == "__main__":
    run()
