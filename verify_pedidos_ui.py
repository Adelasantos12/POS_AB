import asyncio
from playwright.async_api import async_playwright
import os

async def verify():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        # Login
        await page.goto('http://localhost:8000/login/')
        await page.fill('input[name="username"]', 'admin')
        await page.fill('input[name="password"]', 'admin')
        await page.click('button[type="submit"]')

        # Select profile
        await page.wait_for_url('**/perfiles/')
        await page.goto('http://localhost:8000/perfiles/autenticar/?user_id=1')
        await page.fill('input[name="password"]', 'admin')
        await page.click('button[type="submit"]')

        # Pedidos Dashboard
        await page.goto('http://localhost:8000/pedidos/')
        await page.wait_for_url('**/pedidos/')
        await page.screenshot(path='verification/pedidos_tablero.png')

        await browser.close()

if __name__ == '__main__':
    if not os.path.exists('verification'):
        os.makedirs('verification')
    asyncio.run(verify())
