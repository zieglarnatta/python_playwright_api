import pytest
from pytest_playwright.pytest_playwright import playwright

from playwright.sync_api import Playwright

# BASE_URL = "http://localhost:8000"
#
# @pytest.fixture(scope="session")
# def base_url():
#     return BASE_URL

@pytest.fixture
def set_up(page):
    # browser = playwright.chromium.launch(headless=True)
    # browser = playwright.firefox.launch(headless=False)
    # browser = playwright.chromium.launch(channel="msedge", headless=False, slow_mo=500)
    # slowmo is only to slow it down, 500 ms between each action especially for debug
    # browser = playwright.chromium.launch(channel="msedge", headless=True)
    # browser = playwright.webkit.launch(headless=False)
    # context = browser.new_context()
    # page = context.new_page()

# def set_up(playwright: Playwright): ///# by using the 'page' rather than
#     playwright: Playwright, it eliminates the hard coded browser settings, and defaults to headless
#     Need to use --channel and --headed in the command line to render the browser
#     # browser = playwright.chromium.launch(headless=True)
#     # browser = playwright.firefox.launch(headless=False)
#     # browser = playwright.chromium.launch(channel="msedge", headless=False, slow_mo=500)
#     # slowmo is only to slow it down, 500 ms between each action especially for debug
#     browser = playwright.chromium.launch(channel="msedge", headless=True)
#     # browser = playwright.webkit.launch(headless=False)
#     context = browser.new_context()
#     page = context.new_page()

    page.set_default_timeout(15000) # to set whole test timeout to 15 seconds, however
    # expect (assertion) has its own 5000 ms timeout which ignores this general timeout
    # page.pause() # good for debugging
    # page.goto(BASE_URL)
    page.goto("")
    # page.wait_for_load_state("networkidle")
    # page.wait_for_load_state("domcontentloaded")
    page.wait_for_load_state("load")

    yield page

# @pytest.fixture()
# def login_set_up(page):