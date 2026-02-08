from playwright.sync_api import sync_playwright, expect
import os

def verify_boutique_features():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1. Login
        page.goto("http://localhost:8000/login/")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "admin")
        page.click('button[type="submit"]')

        # 2. Select Profile
        page.wait_for_url("**/perfiles/")
        page.click('text="admin"')

        # 3. Authenticate Profile
        page.wait_for_url("**/perfiles/autenticar/**")
        page.fill('input[name="password"]', "admin")
        page.click('button[type="submit"]')

        # 4. Inventory View (Check Barcode & AI trigger)
        page.goto("http://localhost:8000/inventario/")
        page.wait_for_selector('table')
        page.screenshot(path="verification/inventario_list.png")

        # Open Modal
        page.click('text="Nuevo Producto"')
        page.wait_for_selector('#modalNuevoProducto')
        page.screenshot(path="verification/inventario_modal_ai.png")

        # 5. Catalogs View (Check default data)
        page.goto("http://localhost:8000/catalogos/colores/")
        page.wait_for_selector('.color-card')
        page.screenshot(path="verification/catalogo_colores.png")

        # 6. Novias Detail (Check special fields)
        # Create a test novia first via shell if none exist, or just go to list
        page.goto("http://localhost:8000/novias/")
        page.screenshot(path="verification/novias_list.png")

        browser.close()

if __name__ == "__main__":
    if not os.path.exists("verification"):
        os.makedirs("verification")
    verify_boutique_features()
