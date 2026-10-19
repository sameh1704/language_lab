from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    context = browser.new_context()

    responses = []
    def on_response(resp):
        if "/login/" in resp.url:
            responses.append((resp.status, resp.url))

    context.on("response", on_response)

    page = context.new_page()
    page.goto("http://localhost:8000/login/", wait_until="domcontentloaded")
    page.fill('input[name="username"]', "teacher_qa")
    page.fill('input[name="password"]', "teacher_qa123")
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    print("URL:", page.url.encode("ascii", "replace").decode())
    print("Login responses:", responses)
    err = page.locator(".err").count()
    print("Error divs:", err)
    if err:
        print("Error text:", page.locator(".err").first.inner_text().encode("ascii", "replace").decode())
    print("Has username input:", page.locator('input[name="username"]').count())
    print("Has a-power:", page.locator("#a-power").count())
    browser.close()
