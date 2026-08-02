import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Login
        await page.goto("http://localhost:8000/login/")
        await page.fill('input[name="username"]', "admin")
        await page.fill('input[name="password"]', "admin123")
        await page.click('button[type="submit"]')

        # Select profile (Admin)
        await page.wait_for_url("**/perfiles/")
        await page.click('text=Admin')

        # Go to dashboard
        await page.goto("http://localhost:8000/admin-dashboard/")
        await page.wait_for_selector('[data-testid="daily-summary-row"]')

        await page.screenshot(path="admin_dashboard.png", full_page=True)
        print("Dashboard screenshot saved.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
