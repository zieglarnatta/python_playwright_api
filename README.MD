# Choose and start the database before launching the app

With `psycopg2-binary` installed, `shop.py` checks for the project's Docker
PostgreSQL database at `localhost:5432` when it starts. If it can connect, it
uses PostgreSQL automatically; otherwise, it logs the fallback and uses the
local `shop.db` SQLite file. To use Docker PostgreSQL as your default,
install/start Docker and start the database **before** starting `shop.py`.

### Install Docker first

On Ubuntu/Debian, install Docker Engine and Compose, then start the service:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Sign out and back in (or run `newgrp docker`) for the group change to apply.
The `docker` group grants root-equivalent privileges. On macOS or Windows,
install and launch Docker Desktop from
https://www.docker.com/products/docker-desktop/.

Quick start for Docker PostgreSQL:

1. From the project directory, start the database and wait for it to be ready:

   ```bash
   docker compose up -d
   docker compose ps
   docker compose exec db pg_isready -U shop -d shop
   ```

2. Create/activate the Python virtual environment as described below, then
   install the PostgreSQL driver:
   
   ### Create a virtual environment

   ```bash
   python3 -m venv .venv
   ```
   ```
   source .venv/bin/activate
   ```
   ```
   python3 -m pip install psycopg2-binary
   ```

3. Run `python3 shop.py`. No `DATABASE_URL` is needed for this Compose setup;
   the app detects the Docker database automatically.

If you do not want to install or start Docker, just run the app: it uses
SQLite. To explicitly connect to a different PostgreSQL database, set
`DATABASE_URL` before starting the app; an explicitly configured URL is used
instead of automatic detection.

# Install dependencies
```
python3 -m pip install --upgrade pip
python3 -m pip install fastapi uvicorn "passlib[bcrypt]" python-jose[cryptography] pydantic python-multipart
python3 -m pip install playwright pytest pytest-playwright pytest-reporter-html1
```

Install the Playwright browser binaries:

```
playwright install
```

Check that the installed packages are compatible:

```
python3 -m pip check
python3 -m pip show playwright pytest pytest-playwright pytest-reporter-html1
```
# Run the shop python code:

```
 python3 shop.py
```
or to check in case of depreciated python code:
```
 python -W error::DeprecationWarning shop.py
```

# Run pytest and generate an HTML1 report

Run all tests:

```
python3 -m pytest -v
```

Run the Playwright UI tests:

```
python3 -m pytest tests_ui_layout -v
```

Generate an HTML1 report:

```
python3 -m pytest --template=html1/index.html --report=report.html
```

# How to Use It for QA Practice
## Manual Smoke Test
1) Open http://localhost:8000

2) Register a user → log in → add items → checkout

3) Inspect the database selected by the app. For Docker PostgreSQL:

```bash
docker compose exec db psql -U shop -d shop
```
For Docker PostgreSQL:


To verify the app’s tables and sample data exist:
```bash
docker compose exec db psql -U shop -d shop -c "SELECT COUNT(*) FROM products;"
````
For SQLite (when Docker PostgreSQL is not being used):

```bash
sqlite3 shop.db
sqlite> .tables
sqlite> SELECT * FROM orders;
sqlite> SELECT * FROM order_items;
```

# API testing:


```
pip install pytest requests
pytest test_api.py -v
```

## Ideas to Practice
* Auth: assert 401 on missing/expired/invalid token

* Boundaries: quantity=0, negative stock, nonexistent product IDs

* Race conditions: two concurrent checkouts on last stock item

* DB integrity: verify order_items sum == orders.total; verify stock decremented

* Front-end E2E: drive it with Playwright/Selenium against http://localhost:8000


# cURL cheat sheet: test every verb:

```
BASE=http://localhost:8000
```

# --- Public GET ---
```
curl -i $BASE/health
curl -i $BASE/api/products
```

# --- HEAD (metadata only, no body) ---
```
curl -I $BASE/api/products/1
```

# --- OPTIONS (discover allowed methods) ---
```
curl -i -X OPTIONS $BASE/api/products
```

# --- Auth: get a customer token ---
```
curl -s -X POST $BASE/api/register -H 'Content-Type: application/json' \
  -d '{"username":"qa_cust","password":"pass1234"}'
CUST=$(curl -s -X POST $BASE/api/login -H 'Content-Type: application/json' \
  -d '{"username":"qa_cust","password":"pass1234"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

# --- Auth: get an admin token ---
```
ADMIN=$(curl -s -X POST $BASE/api/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin1234"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

# --- POST create (admin) ---
```
curl -i -X POST $BASE/api/products -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test Widget","description":"created via POST","price":9.99,"stock":10}'
```

# --- PUT full replace (admin) ---
```
curl -i -X PUT $BASE/api/products/1 -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Renamed Keyboard","description":"full replace","price":99.99,"stock":20}'
```

# --- PATCH partial (admin) ---
```
curl -i -X PATCH $BASE/api/products/1 -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d '{"price": 79.99}'
```
# --- DELETE (admin) ---
```
curl -i -X DELETE $BASE/api/products/1 -H "Authorization: Bearer $ADMIN"
```

# --- 403 checks: customer can't create/delete products ---
```
curl -i -X DELETE $BASE/api/products/2 -H "Authorization: Bearer $CUST"     # 403
curl -i -X POST   $BASE/api/products -H "Authorization: Bearer $CUST" \
  -H 'Content-Type: application/json' -d '{"name":"x","price":1,"stock":1}'   # 403
```

# --- Cart: POST add / PUT set qty / DELETE item / DELETE cart ---
```
curl -i -X POST   $BASE/api/cart/add      -H "Authorization: Bearer $CUST" \
  -H 'Content-Type: application/json' -d '{"product_id":2,"quantity":1}'
curl -i -X PUT    $BASE/api/cart/item/2   -H "Authorization: Bearer $CUST" \
  -H 'Content-Type: application/json' -d '{"product_id":2,"quantity":3}'
curl -i -X DELETE $BASE/api/cart/item/2   -H "Authorization: Bearer $CUST"
curl -i -X DELETE $BASE/api/cart          -H "Authorization: Bearer $CUST"
```

# --- Checkout + order DELETE ---
```curl -i -X POST $BASE/api/cart/add -H "Authorization: Bearer $CUST" \
  -H 'Content-Type: application/json' -d '{"product_id":3,"quantity":1}'
ORDER=$(curl -s -X POST $BASE/api/checkout -H "Authorization: Bearer $CUST" \
  | python -c 'import sys,json;print(json.load(sys.stdin)["order_id"])')
curl -i $BASE/api/orders/$ORDER -H "Authorization: Bearer $CUST"
curl -i -X DELETE $BASE/api/orders/$ORDER -H "Authorization: Bearer $CUST"
```

<!-- Superseded PostgreSQL instructions:
For authentic DB testing, install Docker and start Docker before using a PostgreSQL container.

On Debian/Ubuntu:

```
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and back in after adding your user to the `docker` group. On macOS or Windows, install Docker Desktop instead and start it.

Activate the Python virtual environment, install the database dependencies, and add a PostgreSQL container:

```
source .venv/bin/activate
python3 -m pip install psycopg2-binary sqlalchemy
docker run -d --name shopdb -e POSTGRES_PASSWORD=secret -e POSTGRES_DB=shop -p 5432:5432 postgres:16
```

Then swap sqlite3.connect(DB_PATH) with SQLAlchemy create_engine("postgresql+psycopg2://postgres:secret@localhost:5432/shop"). All SQL above is ANSI-compatible except AUTOINCREMENT (use SERIAL) and ON CONFLICT (same syntax works in Postgres).

Resetting the lab:

```
rm shop.db          # wipe database
python -W error::DeprecationWarning shop.py  # re-seeds automatically
```
-->

# Use PostgreSQL in Docker

The Python app runs on your computer; only the database runs in Docker. With
`psycopg2-binary` installed, `shop.py` automatically uses this PostgreSQL
database whenever it is reachable at startup. Otherwise it falls back to
SQLite. PostgreSQL tables and sample data are created when the app starts for
the first time.

## 1. Install and start Docker

### Ubuntu / Debian

Install Docker Engine and the Compose plugin from your distribution packages:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
```

Allow your account to run Docker commands without `sudo` (the `docker` group
grants root-equivalent access). Then sign out and back in, or run `newgrp docker`
in the current terminal:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker run --rm hello-world
docker compose version
```

If your distribution does not provide `docker-compose-v2`, install Docker
Engine and the Compose plugin using Docker's official installation instructions:
https://docs.docker.com/engine/install/

### macOS / Windows

1. Install Docker Desktop from https://www.docker.com/products/docker-desktop/.
2. Launch Docker Desktop and wait for it to report that the engine is running.
   On Windows, use Linux containers (the default with the WSL 2 backend).
3. In a terminal, verify the installation:

```bash
docker version
docker compose version
```

## 2. Start the PostgreSQL container

From the project directory (the directory containing `compose.yaml`), start the
database:

```bash
docker compose up -d
docker compose ps
```

Wait until the `db` service reports `healthy`. You can check readiness directly:

```bash
docker compose exec db pg_isready -U shop -d shop
```

The Compose setup creates database `shop`, user `shop`, and a named persistent
volume. Its local development password is `shop_dev_password`; do not reuse
these settings for a publicly accessible or production database. PostgreSQL is
published to port `5432` on your computer.

## 3. Install the PostgreSQL driver and launch the app

Activate the Python environment created earlier and install the PostgreSQL
driver. The Compose database is detected automatically; no connection URL is
required:

```bash
source .venv/bin/activate
python3 -m pip install psycopg2-binary
python3 shop.py
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`, install the
driver, and launch the app:

```powershell
python -m pip install psycopg2-binary
python shop.py
```

Open http://localhost:8000. The app creates its tables and seed data
automatically when it starts. The sample admin credentials are `admin` /
`admin1234`. To use another PostgreSQL server, set `DATABASE_URL` before
launching; that explicit setting takes precedence over Docker auto-detection.

To inspect PostgreSQL in another terminal:

```bash
docker compose exec db psql -U shop -d shop
```

At the `shop=#` prompt, useful commands include `\dt` to list tables and
`SELECT * FROM products;` to see the sample inventory. Exit with `\q`.

To stop the database without deleting its data:

```bash
docker compose stop
```

Start it again later with `docker compose start`, then launch `shop.py`; it will
detect PostgreSQL automatically.

## 4. Reset the PostgreSQL database

To return the Docker database to its original empty state, stop the app with
Ctrl+C, then remove the Compose database and its persistent volume:

```bash
docker compose down -v
docker compose up -d
docker compose ps
```

**This deletes all PostgreSQL data in this Compose project**, including
registered users, orders, carts, and product changes. Once `db` is healthy,
launch `shop.py` again. Startup recreates the schema, admin account, and
original sample products. This does not delete or reset the SQLite `shop.db`
file.

To reset the SQLite database instead, stop the app and remove `shop.db`, then
start `python3 shop.py` again. The tables and sample data are recreated on
startup.