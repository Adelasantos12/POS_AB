from playwright.sync_api import sync_playwright, expect
import os

def verify_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Login
        page.goto("http://localhost:8000/login/")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "admin123")
        page.click('button[type="submit"]')

        # Select profile
        page.wait_for_url("**/perfiles/")
        page.click('text=Admin')

        # Authenticate profile
        page.wait_for_url("**/perfiles/autenticar/**")
        page.fill('input[name="password"]', "admin123")
        page.click('button[type="submit"]')

        # Go to Pedidos
        page.goto("http://localhost:8000/pedidos/")
        page.wait_for_selector('text=Pedidos')

        # Check if "Cobrar" button exists in the table (if any pedidos exist)
        cobrar_btn = page.locator('button[title="Cobrar"]').first
        if cobrar_btn.is_visible():
            print("Cobrar button found in Pedidos list.")
        else:
            print("No pending pedidos found to verify Cobrar button in list.")

        # Check "Editar Entrega" button
        entrega_btn = page.locator('button[title="Editar Entrega"]').first
        if entrega_btn.is_visible():
            print("Editar Entrega button found.")
            entrega_btn.click()
            page.wait_for_selector('#modalEditarEntrega', state='visible')
            print("Editar Entrega modal is working.")
            page.click('#modalEditarEntrega .btn-close')

        # Go to POS
        page.goto("http://localhost:8000/pos/")
        page.wait_for_url("**/pos/")

        # Search for a known folio or name (e.g. Alice)
        # Note: Need to make sure Alice exists from previous step cleanup?
        # Actually I cleaned up Alice. I'll search for something generic.
        page.fill('#productSearch', 'PED-')
        page.wait_for_timeout(1000) # Wait for debounce and API

        results = page.locator('#searchResults .list-group-item')
        if results.count() > 0:
            print(f"Global search returned {results.count()} results.")
            page.screenshot(path="/home/jules/verification/search_results.png")
        else:
            print("Global search returned 0 results for 'PED-'.")
            page.screenshot(path="/home/jules/verification/pos_empty_search.png")

        browser.close()

if __name__ == "__main__":
    verify_ui()
