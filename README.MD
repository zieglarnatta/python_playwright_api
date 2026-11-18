# Python Playwright API Shop

## Project authorship

- `shop.py`, `test_api.py`, and `test_db.py` were AI-generated.
- The Page Object Model (POM) and the `tests_ui_layout` UI tests were written by me.

## Set up and run the shop

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the shop dependencies:

```bash
pip install fastapi uvicorn "passlib[bcrypt]" "python-jose[cryptography]" pydantic python-multipart
```

Run the shop:

```bash
python3 shop.py
```

To turn Python deprecation warnings into errors:

```bash
python -W error::DeprecationWarning shop.py
```

## Manual QA smoke test

1. Open <http://localhost:8000>.
2. Register a user, log in, add items, and check out.
3. Inspect the database:

```bash
sqlite3 shop.db
```

```sql
.tables
SELECT * FROM orders;
SELECT * FROM order_items;
```

## API tests

Install the API test dependencies and run the tests:

```bash
pip install pytest requests
pytest -v test_api.py
```

## Pytest and Playwright user guide

### Install Playwright and record browser interactions

Install Microsoft Edge for Linux through Playwright:

```bash
playwright install msedge
```

Start the application, then run:

```bash
playwright codegen http://localhost:8000/
```

The Playwright inspector and a Chromium browser will open. Use the browser to record mouse clicks and data entry; Playwright generates the corresponding script in the inspector.

### Install `pytest-playwright` in PyCharm on Linux

In PyCharm, open **Settings → Python → All Interpreters**, then click **Python Packages** and install `pytest-playwright`.

Alternatively, click the Python Packages tool-window icon on the right-hand side (it looks like a box with a Python symbol) and install it there.

### Common pytest commands

Run tests with verbose output:

```bash
pytest -v
```

Run tests marked as smoke tests, or exclude those tests:

```bash
pytest -m smoke
pytest -m "not smoke"
```

Make sure `pytest.ini` is in the project root and defines the custom markers:

```ini
[pytest]
markers =
    smoke: marks smoke tests
    regression: regression tests
    integration: integration tests
```

Stop after the first failure, or stop after at most two failures:

```bash
pytest -x
pytest --maxfail=2
```

Run a specific test by function name, or run a specific test file:

```bash
pytest -k <test_function_name>
pytest <path/to/test_file.py>
```

Re-run only failed tests, or run all tests with failed tests first:

```bash
pytest --lf
pytest --ff
```

Pytest options can be combined:

```bash
pytest --ff -x -v
```

### HTML reports and parallel runs

Install the `pytest-reporter-html1` package, then generate an HTML report:

```bash
pytest --template=html1/index.html --report=report.html
```

Install `pytest-xdist` to run tests in parallel. Specify the number of workers, or let it choose automatically:

```bash
pytest -n <NUMCPUS>
pytest -n auto
```

See the [Playwright Python test-runner documentation](https://playwright.dev/python/docs/test-runners) for additional options, including:

- `--headed`: run tests with a visible browser.
- `--browser`: choose `chromium`, `firefox`, or `webkit`; can be specified multiple times.
- `--browser-channel`: choose a browser channel.
- `--slowmo`: slow down browser actions.
- `--device`: emulate a device.
- `--video`: record video (`on`, `off`, or `retain-on-failure`).
- `--screenshot`: capture screenshots (`on`, `off`, or `only-on-failure`).
- `--base-url`: set the base URL for tests.

### Example Playwright test runs

Run tests on WebKit, Firefox, and Chromium, with up to two failures, automatic worker selection, and an HTML report:

```bash
pytest --maxfail=2 --browser webkit --browser firefox --browser chromium -n auto \
  --template=html1/index.html --report=report.html
```

Capture screenshots on failure and slow the browser actions:

```bash
pytest --maxfail=2 --slowmo=400 -n auto \
  --template=html1/index.html --report=report.html \
  --screenshot=only-on-failure
```

Retain videos on failure and capture screenshots on failure:

```bash
pytest --maxfail=2 -n auto \
  --template=html1/index.html --report=report.html \
  --video=retain-on-failure --screenshot=only-on-failure
```

Emulate an iPhone 11 with a visible browser:

```bash
pytest --maxfail=2 --headed --device="iPhone 11" --slowmo=400 -n auto \
  --template=html1/index.html --report=report.html \
  --video=retain-on-failure
```

Set the application's base URL and collect video and screenshots on failure:

```bash
pytest --maxfail=2 -n auto --base-url http://localhost:8000 \
  --template=html1/index.html --report=report.html \
  --video=retain-on-failure --screenshot=only-on-failure
```

## Ideas for QA practice

- **Authentication:** assert 401 responses for missing, expired, or invalid tokens.
- **Boundaries:** try quantity zero, negative stock, and nonexistent product IDs.
- **Race conditions:** attempt two concurrent checkouts for the last item in stock.
- **Database integrity:** verify that order-item totals match the order total and that stock is decremented.
- **Front-end end-to-end testing:** use Playwright or Selenium against <http://localhost:8000>.

## cURL cheat sheet

Set the API base URL:

```bash
BASE=http://localhost:8000
```

Public GET requests:

```bash
curl -i "$BASE/health"
curl -i "$BASE/api/products"
```

HEAD (metadata only) and OPTIONS (discover allowed methods):

```bash
curl -I "$BASE/api/products/1"
curl -i -X OPTIONS "$BASE/api/products"
```

Register and log in as a customer:

```bash
curl -s -X POST "$BASE/api/register" -H 'Content-Type: application/json' \
  -d '{"username":"qa_cust","password":"pass1234"}'
CUST=$(curl -s -X POST "$BASE/api/login" -H 'Content-Type: application/json' \
  -d '{"username":"qa_cust","password":"pass1234"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

Log in as an admin:

```bash
ADMIN=$(curl -s -X POST "$BASE/api/login" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin1234"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

Use the token returned by login in the `Authorization` header for authenticated requests:

```bash
# Create a product (admin)
curl -i -X POST "$BASE/api/products" -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test Widget","description":"created via POST","price":9.99,"stock":10}'

# Replace a product (admin)
curl -i -X PUT "$BASE/api/products/1" -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Renamed Keyboard","description":"full replace","price":99.99,"stock":20}'

# Partially update a product (admin)
curl -i -X PATCH "$BASE/api/products/1" -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d '{"price":79.99}'

# Delete a product (admin)
curl -i -X DELETE "$BASE/api/products/1" -H "Authorization: Bearer $ADMIN"
```

Check that customers cannot create or delete products (these requests should return 403):

```bash
curl -i -X DELETE "$BASE/api/products/2" -H "Authorization: Bearer $CUST"
curl -i -X POST "$BASE/api/products" -H "Authorization: Bearer $CUST" \
  -H 'Content-Type: application/json' \
  -d '{"name":"x","price":1,"stock":1}'
```

Cart operations:

```bash
curl -i -X POST "$BASE/api/cart/add" -H "Authorization: Bearer $CUST" \
  -H 'Content-Type: application/json' -d '{"product_id":2,"quantity":1}'
curl -i -X PUT "$BASE/api/cart/item/2" -H "Authorization: Bearer $CUST" \
  -H 'Content-Type: application/json' -d '{"product_id":2,"quantity":3}'
curl -i -X DELETE "$BASE/api/cart/item/2" -H "Authorization: Bearer $CUST"
curl -i -X DELETE "$BASE/api/cart" -H "Authorization: Bearer $CUST"
```

Checkout and retrieve or delete an order:

```bash
curl -i -X POST "$BASE/api/cart/add" -H "Authorization: Bearer $CUST" \
  -H 'Content-Type: application/json' -d '{"product_id":3,"quantity":1}'
ORDER=$(curl -s -X POST "$BASE/api/checkout" -H "Authorization: Bearer $CUST" \
  | python -c 'import sys,json;print(json.load(sys.stdin)["order_id"])')
curl -i "$BASE/api/orders/$ORDER" -H "Authorization: Bearer $CUST"
curl -i -X DELETE "$BASE/api/orders/$ORDER" -H "Authorization: Bearer $CUST"
```

## Swap to PostgreSQL in Docker

For database testing with PostgreSQL, start a container and install the database libraries:

```bash
docker run -d --name shopdb -e POSTGRES_PASSWORD=secret -e POSTGRES_DB=shop \
  -p 5432:5432 postgres:16
pip install psycopg2-binary sqlalchemy
```

Replace `sqlite3.connect(DB_PATH)` with a SQLAlchemy engine configured for PostgreSQL, for example `create_engine("postgresql://user:password@localhost:5432/shop")`. Most SQL statements above are ANSI-compatible; PostgreSQL uses `SERIAL` instead of `AUTOINCREMENT`, while `ON CONFLICT` syntax is supported.

## Reset the lab

Remove the SQLite database and run the app to seed it again:

```bash
rm shop.db
python -W error::DeprecationWarning shop.py
```
