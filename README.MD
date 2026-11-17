# Create a virtual environment

```
python3 -m venv venv
```
```
source venv/bin/activate
```

# Install dependencies
```
pip install fastapi uvicorn "passlib[bcrypt]" python-jose[cryptography] pydantic python-multipart
```

# Run the shop python code:

```
 python3 shop.py
```
or to check in case of depreciated python code:
```
 python -W error::DeprecationWarning shop.py
```


# How to Use It for QA Practice
## Manual Smoke Test
1) Open http://localhost:8000

2) Register a user → log in → add items → checkout

3) Inspect the DB directly:


```
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

# Swap to a Real Database (Postgres in Docker)
For authentic DB testing, replace the SQLite calls. Add a container:



```
docker run -d --name shopdb -e POSTGRES_PASSWORD=secret -e POSTGRES_DB=shop -p 5432:5432 postgres:16
pip install psycopg2-binary sqlalchemy
```

Then swap sqlite3.connect(DB_PATH) with SQLAlchemy create_engine("postgresql+psycopg2://postgres:secret@localhost:5432/shop"). All SQL above is ANSI-compatible except AUTOINCREMENT (use SERIAL) and ON CONFLICT (same syntax works in Postgres).

Resetting the lab:

```
rm shop.db          # wipe database
python -W error::DeprecationWarning shop.py  # re-seeds automatically
```