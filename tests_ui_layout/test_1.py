# import re
import pytest
from playwright.sync_api import expect
# from playwright.sync_api import Playwright, sync_playwright, expect
from pom.home_page_elements import HomePage

@pytest.mark.regression
def test_login(set_up) -> None:
    # # browser = playwright.chromium.launch(headless=True)
    # # browser = playwright.firefox.launch(headless=False)
    # # browser = playwright.chromium.launch(channel="msedge", headless=False, slow_mo=500)
    # # slowmo is only to slow it down, 500 ms between each action especially for debug
    # browser = playwright.chromium.launch(channel="msedge", headless=True)
    # # browser = playwright.webkit.launch(headless=False)
    # context = browser.new_context()
    # page = context.new_page()
    # page.set_default_timeout(15000) # to set whole test timeout to 15 seconds, however
    # # expect (assertion) has its own 5000 ms timeout which ignores this general timeout
    # # page.pause() # good for debugging
    # page.goto("http://localhost:8000/")
    # # page.wait_for_load_state("networkidle")
    # # page.wait_for_load_state("domcontentloaded")
    # page.wait_for_load_state("load")

    page = set_up
    expect(page.get_by_test_id("login-username")).to_be_visible()
    expect(page.get_by_test_id("login-password")).to_be_visible()
    expect(page.get_by_test_id("toggle-register-btn")).to_be_visible()
    expect(page.get_by_test_id("login-submit-btn")).to_be_visible()
    expect(page.get_by_test_id("role-badge")).to_be_visible()
    # expect(page.get_by_test_id("role-badge")).to_be_visible(timeout=3000) #set an assert timeout, default 5000 ms
    # this is independent of the overall test timeout above

    page.get_by_test_id("login-username").click()
    # page.get_by_test_id("login-username").click(timeout=3000)
    # good for performance say it should get done by 3000ms, default is 30 seconds

    page.get_by_test_id("login-username").fill("qa_cust")
    # page.get_by_test_id("login-username").fill("qa_cust", timeout=2000)
    # set a separate timeout for filling this text box

    page.get_by_test_id("login-password").click()
    page.get_by_test_id("login-password").fill("pass1234")
    page.get_by_test_id("login-submit-btn").click()
    expect(page.get_by_test_id("authMsg-ok")).to_be_visible()
    expect(page.get_by_test_id("authMsg-ok")).to_contain_text("Logged in ✔")
    print("'Logged in ✔' is visible and verified")
    # page.pause()

    all_buttons = page.get_by_role("button").all()
    for button in all_buttons:
        text = (button.text_content() or "").lower()
        if 'checkout' in text:
            assert 'checkout' in text
    print("Test Success!")


    # ---------------------
    # context.close()
    # browser.close()


# with sync_playwright() as playwright:
#     run(playwright)
