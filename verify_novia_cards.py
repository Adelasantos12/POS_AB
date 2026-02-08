import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        try:
            # 1. Login
            print("Step 1: Logging in...")
            await page.goto("http://127.0.0.1:8000/login/")
            await page.fill('input[name="username"]', "admin")
            await page.fill('input[name="password"]', "admin123")
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle")
            print(f"Logged in, current URL: {page.url}")

            # 2. Select Profile
            print("Step 2: Selecting profile...")
            # If already on /perfiles/ skip click if possible, but let's be explicit
            if "/perfiles/" in page.url:
                await page.click('[data-testid="profile-card-admin"]')
                await page.wait_for_load_state("networkidle")
                print(f"Profile selected, current URL: {page.url}")

            # 3. Enter Profile Password
            if "/perfiles/autenticar/" in page.url:
                print("Step 3: Authenticating profile...")
                await page.fill('input[name="password"]', "admin123")
                await page.click('button[type="submit"]')
                await page.wait_for_load_state("networkidle")
                print(f"Authenticated, current URL: {page.url}")

            # 4. Go to Novia detail (Plural: novias)
            print("Step 4: Going to Novia detail...")
            await page.goto("http://127.0.0.1:8000/novias/1/")
            await page.wait_for_load_state("networkidle")
            print(f"At Novia detail, current URL: {page.url}")

            # Take screenshot
            screenshot_path = "verification/novia_detalle_cards_v8.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved to {screenshot_path}")

            # Check for the buttons
            content = await page.content()
            if "Page not found" in content:
                print("FAILED: 404 Page not found")

            print("Cobrar button found:" if 'Cobrar' in content else "Cobrar button NOT found")
            print("Medidas button found:" if 'Medidas' in content else "Medidas button NOT found")
            print("Entregar button found:" if 'Entregar' in content else "Entregar button NOT found")

        except Exception as e:
            print(f"An error occurred: {e}")
            await page.screenshot(path="verification/error_screenshot.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
