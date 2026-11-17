import pytest
from playwright.sync_api import Playwright, expect, sync_playwright
from pom.home_page_elements import HomePage

@pytest.mark.regression
def test_login(set_up) -> None:

    page = set_up
    expect(page.get_by_test_id("login-username")).to_be_visible()
    expect(page.get_by_test_id("login-password")).to_be_visible()
    expect(page.get_by_test_id("toggle-register-btn")).to_be_visible()
    expect(page.get_by_test_id("login-submit-btn")).to_be_visible()
    expect(page.get_by_test_id("role-badge")).to_be_visible()

    page.get_by_test_id("login-username").click()

    page.get_by_test_id("login-username").fill("qa_cust")

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

@pytest.mark.regression
# def test_noise_cancel_verbiage(playwright: Playwright):
    # browser = playwright.chromium.launch(headless=False, slow_mo=1000)
    # browser = playwright.chromium.launch(headless=True)
    # page = browser.new_page()
    # page.goto("http://localhost:8000/")
    # home_page = HomePage(page)
    #  taking all above out to use the conftest
def test_noise_cancel_verbiage(set_up) -> None:
    page = set_up
    home_page = HomePage(page)
    expect(home_page.celebrate_header).to_be_visible()
    print("Noise cancel headphones verbiage passed!")
    expect(home_page.celebrate_body).to_be_visible()
    print("Detailed  verbiage present & passed!")


# @pytest.mark.skip(reason="Not Ready")
@pytest.mark.regression
# def test_noise_cancel_verbiage_2(playwright: Playwright):
#     # browser = playwright.chromium.launch(headless=False, slow_mo=1000)
#     browser = playwright.chromium.launch(headless=True)
#     page = browser.new_page()
#     page.goto("http://localhost:8000/")
#     home_page = HomePage(page)
    #  taking all above out to use the conftest
def test_noise_cancel_verbiage_2(set_up) -> None:
    page = set_up
    home_page = HomePage(page)

    page.get_by_test_id("login-submit-btn").click()
    expect(page.get_by_test_id("authMsg-ok")).to_contain_text("Logged in")
    expect(home_page.celebrate_header).to_be_visible()
    expect(home_page.celebrate_body).to_be_visible()

@pytest.mark.xfail(reason="Purposely checking for Missing Check Mark should fail")
# def test_noise_cancel_verbiage_3(playwright: Playwright):
#     # browser = playwright.chromium.launch(headless=False, slow_mo=1000)
#     browser = playwright.chromium.launch(headless=True)
#     page = browser.new_page()
#     page.goto("http://localhost:8000/")
#     home_page = HomePage(page)
    #  taking all above out to use the conftest
def test_noise_cancel_verbiage_3(set_up) -> None:
    page = set_up
    home_page = HomePage(page)

    expect(page.get_by_test_id("authMsg-ok")).to_contain_text("Logged in")
    expect(home_page.celebrate_header).to_be_visible()
    expect(home_page.celebrate_body).to_be_visible()

    # print("Test complete!")
#
# with sync_playwright() as playwright:
#     test_noise_cancel_verbiage(playwright)