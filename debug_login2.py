from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    context = browser.new_context()

    captured = []

    def on_response(resp):
        if "login" in resp.url:
            captured.append((resp.status, resp.url))

    context.on("response", on_response)

    page = context.new_page()
    page.goto("http://localhost:8000/login/", wait_until="domcontentloaded")
    print("Cookies before:", context.cookies())
    page.fill('input[name="username"]', "teacher_qa")
    page.fill('input[name="password"]', "teacher_qa123")
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    print("URL after:", page.url)
    print("Responses:", captured)
    print("Cookies after:", context.cookies())
    print("Body:", page.locator("body").inner_text()[:200])
    browser.close()
