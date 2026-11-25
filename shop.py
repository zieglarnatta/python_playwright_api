"""
shop.py — Shop Test Lab v3.4

Adds data-testid attributes throughout the frontend for automation testing.
Every interactive element, container, and state indicator has a stable testid.

Backend identical to v3.3.

Run:
    rm -f shop.db         # only if you had a pre-v3 schema
    python shop.py
Then open http://localhost:8000
Docs at http://localhost:8000/docs
"""

import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import uvicorn
from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

try:
    import psycopg2
    from psycopg2.extras import DictCursor
except ImportError:
    psycopg2 = None
    DictCursor = None

# ----------------------------- CONFIG ---------------------------------------
DB_PATH = Path(__file__).parent / "shop.db"
DATABASE_URL = os.getenv("DATABASE_URL")
DOCKER_DATABASE_URL = (
    "postgresql://shop:shop_dev_password@localhost:5432/shop"
)
ACTIVE_DATABASE_URL: Optional[str] = None
DATABASE_SELECTED = False
SECRET_KEY = "test-secret-do-not-use-in-prod"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
GUEST_COOKIE = "guest_id"
GUEST_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)
INTEGRITY_ERRORS = [sqlite3.IntegrityError]
if psycopg2 is not None:
    INTEGRITY_ERRORS.append(psycopg2.IntegrityError)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ----------------------------- DATABASE -------------------------------------
def select_database():
    global ACTIVE_DATABASE_URL, DATABASE_SELECTED
    if DATABASE_SELECTED:
        return

    DATABASE_SELECTED = True
    if DATABASE_URL:
        ACTIVE_DATABASE_URL = DATABASE_URL
        return

    if psycopg2 is None:
        print(
            "[database] psycopg2 is not installed; using SQLite. "
            "Install psycopg2-binary to auto-detect Docker PostgreSQL."
        )
        return

    try:
        probe = psycopg2.connect(DOCKER_DATABASE_URL, connect_timeout=2)
    except psycopg2.OperationalError as error:
        print(
            "[database] Docker PostgreSQL is unavailable "
            f"({error}); using SQLite at {DB_PATH}."
        )
        return

    probe.close()
    ACTIVE_DATABASE_URL = DOCKER_DATABASE_URL
    print("[database] Docker PostgreSQL detected; using its shop database.")


class DatabaseConnection:
    def __init__(self, connection, is_postgres=False):
        self.connection = connection
        self.is_postgres = is_postgres

    def execute(self, query, parameters=()):
        cursor = self.cursor()
        if (
            self.is_postgres
            and query.strip().upper() == "BEGIN"
            and self.connection.get_transaction_status()
            == psycopg2.extensions.TRANSACTION_STATUS_INTRANS
        ):
            return cursor
        cursor.execute(self._adapt_query(query), parameters)
        return cursor

    def executemany(self, query, parameters):
        cursor = self.cursor()
        cursor.executemany(self._adapt_query(query), parameters)
        return cursor

    def executescript(self, script):
        if not self.is_postgres:
            return self.connection.executescript(script)
        cursor = self.cursor()
        for statement in script.split(";"):
            if statement.strip():
                cursor.execute(statement)

    def cursor(self):
        if self.is_postgres:
            return self.connection.cursor(cursor_factory=DictCursor)
        return self.connection.cursor()

    def _adapt_query(self, query):
        return query.replace("?", "%s") if self.is_postgres else query

    def __getattr__(self, name):
        return getattr(self.connection, name)


def connect_db():
    select_database()
    if ACTIVE_DATABASE_URL:
        if psycopg2 is None:
            raise RuntimeError(
                "DATABASE_URL is set, but psycopg2 is not installed. "
                "Install it with: python3 -m pip install psycopg2-binary"
            )
        return DatabaseConnection(
            psycopg2.connect(ACTIVE_DATABASE_URL), is_postgres=True
        )

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return DatabaseConnection(connection)


def database_description():
    select_database()
    return "PostgreSQL" if ACTIVE_DATABASE_URL else str(DB_PATH)


def get_db():
    conn = connect_db()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    conn = connect_db()
    schema = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS carts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guest_id TEXT,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            UNIQUE(user_id, product_id),
            UNIQUE(guest_id, product_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            total REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        );
        """
    if ACTIVE_DATABASE_URL:
        schema = schema.replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
        )
    conn.executescript(schema)

    if conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone() is None:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("admin", hash_password("admin1234"), "admin", utcnow_iso()),
        )

    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        now = utcnow_iso()
        conn.executemany(
            "INSERT INTO products (name, description, price, stock, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("Mechanical Keyboard", "RGB, brown switches", 89.99, 25, now, now),
                ("Wireless Mouse", "Ergonomic, silent click", 24.50, 100, now, now),
                ("USB-C Hub", "7-in-1, 4K HDMI", 39.99, 40, now, now),
                ("Laptop Stand", "Aluminum, adjustable", 29.95, 60, now, now),
                ("Noise-Cancel Headphones", "Over-ear, 30h battery", 199.00, 15, now, now),
            ],
        )
    conn.commit()
    conn.close()


# ----------------------------- SCHEMAS --------------------------------------
class RegisterIn(BaseModel):
    username: str
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class CartItemIn(BaseModel):
    product_id: int
    quantity: int = 1


class ProductReplaceIn(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    price: float = Field(..., gt=0)
    stock: int = Field(..., ge=0)


class ProductPatchIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    stock: Optional[int] = Field(None, ge=0)


# ----------------------------- AUTH HELPERS ---------------------------------
def create_token(user_id: int, username: str, role: str) -> str:
    expire = utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(user_id), "username": username, "role": role, "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: DatabaseConnection = Depends(get_db),
):
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise cred_exc
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise cred_exc
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise cred_exc
    return dict(row)


def require_admin(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin privileges required")
    return user


def get_cart_owner(
    request: Request,
    response: Response,
    token: Optional[str] = Depends(oauth2_scheme),
    guest_id: Optional[str] = Cookie(None),
    db: DatabaseConnection = Depends(get_db),
):
    user = None
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            row = db.execute(
                "SELECT * FROM users WHERE id = ?", (int(payload.get("sub")),)
            ).fetchone()
            if row:
                user = dict(row)
        except (JWTError, TypeError, ValueError):
            user = None

    if user:
        return {"user_id": user["id"], "guest_id": None, "user": user}

    if not guest_id:
        guest_id = str(uuid.uuid4())
        response.set_cookie(
            GUEST_COOKIE,
            guest_id,
            max_age=GUEST_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
    return {"user_id": None, "guest_id": guest_id, "user": None}


def cart_owner_column(owner) -> tuple[str, tuple]:
    if owner["user_id"] is not None:
        return "user_id", (owner["user_id"],)
    return "guest_id", (owner["guest_id"],)


# ----------------------------- LIFESPAN -------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.started_at = utcnow()
    print(f"[startup] DB ready: {database_description()}")
    yield
    print("[shutdown] bye")


# ----------------------------- APP ------------------------------------------
app = FastAPI(title="Shop Test Lab", version="3.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Meta ----------
@app.get("/health")
def health(request: Request):
    started = getattr(request.app.state, "started_at", None)
    uptime = (utcnow() - started).total_seconds() if started else None
    return {
        "status": "ok",
        "uptime_seconds": round(uptime, 2) if uptime is not None else None,
    }


@app.options("/api/products")
def options_products(response: Response):
    response.headers["Allow"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD"
    return {}


# ---------- Auth ----------
@app.post("/api/register", status_code=201)
def register(body: RegisterIn, db: DatabaseConnection = Depends(get_db)):
    if len(body.username) < 3 or len(body.password) < 4:
        raise HTTPException(400, "Username >=3 chars, password >=4 chars")
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?) RETURNING id",
            (body.username, hash_password(body.password), "customer", utcnow_iso()),
        )
        user_id = cur.fetchone()[0]
        db.commit()
    except tuple(INTEGRITY_ERRORS):
        raise HTTPException(409, "Username already exists")
    return {"id": user_id, "username": body.username, "role": "customer"}


@app.post("/api/login")
def login(body: LoginIn, db: DatabaseConnection = Depends(get_db)):
    row = db.execute(
        "SELECT * FROM users WHERE username = ?", (body.username,)
    ).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(row["id"], row["username"], row["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": row["id"],
        "role": row["role"],
    }


@app.get("/api/me")
def me(user=Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


# ---------- Products ----------
@app.get("/api/products")
def list_products(db: DatabaseConnection = Depends(get_db)):
    rows = db.execute("SELECT * FROM products ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/products/{product_id}")
def get_product(product_id: int, db: DatabaseConnection = Depends(get_db)):
    row = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Product not found")
    return dict(row)


@app.post("/api/products", status_code=201)
def create_product(
    body: ProductReplaceIn,
    admin=Depends(require_admin),
    db: DatabaseConnection = Depends(get_db),
):
    now = utcnow_iso()
    cur = db.execute(
        "INSERT INTO products (name, description, price, stock, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
        (body.name, body.description, body.price, body.stock, now, now),
    )
    product_id = cur.fetchone()[0]
    db.commit()
    row = db.execute(
        "SELECT * FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    return dict(row)


@app.put("/api/products/{product_id}")
def replace_product(
    product_id: int,
    body: ProductReplaceIn,
    admin=Depends(require_admin),
    db: DatabaseConnection = Depends(get_db),
):
    exists = db.execute(
        "SELECT id FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    if not exists:
        raise HTTPException(404, "Product not found")
    db.execute(
        "UPDATE products SET name = ?, description = ?, price = ?, stock = ?, updated_at = ? WHERE id = ?",
        (body.name, body.description, body.price, body.stock, utcnow_iso(), product_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return dict(row)


@app.patch("/api/products/{product_id}")
def patch_product(
    product_id: int,
    body: ProductPatchIn,
    admin=Depends(require_admin),
    db: DatabaseConnection = Depends(get_db),
):
    row = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Product not found")

    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "No fields to update")

    allowed = {"name", "description", "price", "stock"}
    fields = [k for k in data if k in allowed]
    if not fields:
        raise HTTPException(400, "No updatable fields provided")

    sets = ", ".join(f"{f} = ?" for f in fields) + ", updated_at = ?"
    values = [data[f] for f in fields] + [utcnow_iso(), product_id]
    db.execute(f"UPDATE products SET {sets} WHERE id = ?", values)
    db.commit()
    row = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return dict(row)


@app.delete("/api/products/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    admin=Depends(require_admin),
    db: DatabaseConnection = Depends(get_db),
):
    exists = db.execute(
        "SELECT id FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    if not exists:
        raise HTTPException(404, "Product not found")
    db.execute("DELETE FROM products WHERE id = ?", (product_id,))
    db.commit()
    return Response(status_code=204)


# ---------- Cart ----------
@app.post("/api/cart/add")
def cart_add(
    body: CartItemIn,
    owner=Depends(get_cart_owner),
    db: DatabaseConnection = Depends(get_db),
):
    if body.quantity < 1:
        raise HTTPException(400, "quantity must be >= 1")
    prod = db.execute(
        "SELECT * FROM products WHERE id = ?", (body.product_id,)
    ).fetchone()
    if not prod:
        raise HTTPException(404, "Product not found")
    if prod["stock"] < body.quantity:
        raise HTTPException(400, f"Only {prod['stock']} in stock")

    if owner["user_id"] is not None:
        db.execute(
            """INSERT INTO carts (user_id, product_id, quantity) VALUES (?, ?, ?)
               ON CONFLICT(user_id, product_id)
               DO UPDATE SET quantity = quantity + excluded.quantity""",
            (owner["user_id"], body.product_id, body.quantity),
        )
    else:
        db.execute(
            """INSERT INTO carts (guest_id, product_id, quantity) VALUES (?, ?, ?)
               ON CONFLICT(guest_id, product_id)
               DO UPDATE SET quantity = quantity + excluded.quantity""",
            (owner["guest_id"], body.product_id, body.quantity),
        )
    db.commit()
    return {"status": "ok"}


@app.get("/api/cart")
def cart_view(
    owner=Depends(get_cart_owner), db: DatabaseConnection = Depends(get_db)
):
    col, params = cart_owner_column(owner)
    rows = db.execute(
        f"""SELECT c.product_id, p.name, p.price, c.quantity
            FROM carts c JOIN products p ON p.id = c.product_id
            WHERE c.{col} = ?""",
        params,
    ).fetchall()
    items = [dict(r) for r in rows]
    total = round(sum(i["price"] * i["quantity"] for i in items), 2)
    return {"items": items, "total": total}


@app.put("/api/cart/item/{product_id}")
def cart_set_quantity(
    product_id: int,
    body: CartItemIn,
    owner=Depends(get_cart_owner),
    db: DatabaseConnection = Depends(get_db),
):
    if body.quantity < 1:
        raise HTTPException(400, "quantity must be >= 1")
    prod = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not prod:
        raise HTTPException(404, "Product not found")
    if prod["stock"] < body.quantity:
        raise HTTPException(400, f"Only {prod['stock']} in stock")

    col, params = cart_owner_column(owner)
    cur = db.execute(
        f"UPDATE carts SET quantity = ? WHERE {col} = ? AND product_id = ?",
        (body.quantity, *params, product_id),
    )
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Item not in cart")
    return {"status": "ok", "product_id": product_id, "quantity": body.quantity}


@app.delete("/api/cart/item/{product_id}", status_code=204)
def cart_delete_item(
    product_id: int,
    owner=Depends(get_cart_owner),
    db: DatabaseConnection = Depends(get_db),
):
    col, params = cart_owner_column(owner)
    cur = db.execute(
        f"DELETE FROM carts WHERE {col} = ? AND product_id = ?",
        (*params, product_id),
    )
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Item not in cart")
    return Response(status_code=204)


@app.delete("/api/cart", status_code=204)
def cart_clear(
    owner=Depends(get_cart_owner), db: DatabaseConnection = Depends(get_db)
):
    col, params = cart_owner_column(owner)
    db.execute(f"DELETE FROM carts WHERE {col} = ?", params)
    db.commit()
    return Response(status_code=204)


@app.post("/api/cart/merge")
def cart_merge(
    guest_id: Optional[str] = Cookie(None),
    user=Depends(get_current_user),
    db: DatabaseConnection = Depends(get_db),
):
    if not guest_id:
        return {"merged": 0}
    rows = db.execute(
        "SELECT product_id, quantity FROM carts WHERE guest_id = ?", (guest_id,)
    ).fetchall()
    for r in rows:
        db.execute(
            """INSERT INTO carts (user_id, product_id, quantity) VALUES (?, ?, ?)
               ON CONFLICT(user_id, product_id)
               DO UPDATE SET quantity = quantity + excluded.quantity""",
            (user["id"], r["product_id"], r["quantity"]),
        )
    db.execute("DELETE FROM carts WHERE guest_id = ?", (guest_id,))
    db.commit()
    return {"merged": len(rows)}


# ---------- Checkout ----------
@app.post("/api/checkout")
def checkout(user=Depends(get_current_user), db: DatabaseConnection = Depends(get_db)):
    items = db.execute(
        """SELECT c.product_id, p.name, p.price, p.stock, c.quantity
           FROM carts c JOIN products p ON p.id = c.product_id
           WHERE c.user_id = ?""",
        (user["id"],),
    ).fetchall()
    if not items:
        raise HTTPException(400, "Cart is empty")

    for it in items:
        if it["stock"] < it["quantity"]:
            raise HTTPException(400, f"Insufficient stock for {it['name']}")

    total = round(sum(it["price"] * it["quantity"] for it in items), 2)
    order_id = str(uuid.uuid4())
    now = utcnow_iso()

    try:
        db.execute("BEGIN")
        db.execute(
            "INSERT INTO orders (id, user_id, total, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (order_id, user["id"], total, "PAID", now),
        )
        for it in items:
            db.execute(
                "INSERT INTO order_items (order_id, product_id, product_name, price, quantity) VALUES (?, ?, ?, ?, ?)",
                (order_id, it["product_id"], it["name"], it["price"], it["quantity"]),
            )
            db.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?",
                (it["quantity"], it["product_id"]),
            )
        db.execute("DELETE FROM carts WHERE user_id = ?", (user["id"],))
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Checkout failed")

    return {"order_id": order_id, "total": total, "status": "PAID"}


# ---------- Orders ----------
@app.get("/api/orders")
def list_orders(user=Depends(get_current_user), db: DatabaseConnection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    orders = []
    for o in rows:
        items = db.execute(
            "SELECT product_id, product_name, price, quantity FROM order_items WHERE order_id = ?",
            (o["id"],),
        ).fetchall()
        d = dict(o)
        d["items"] = [dict(i) for i in items]
        orders.append(d)
    return orders


@app.get("/api/orders/{order_id}")
def get_order(
    order_id: str, user=Depends(get_current_user), db: DatabaseConnection = Depends(get_db)
):
    o = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not o or (o["user_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(404, "Order not found")
    items = db.execute(
        "SELECT product_id, product_name, price, quantity FROM order_items WHERE order_id = ?",
        (order_id,),
    ).fetchall()
    d = dict(o)
    d["items"] = [dict(i) for i in items]
    return d


@app.delete("/api/orders/{order_id}", status_code=204)
def delete_order(
    order_id: str, user=Depends(get_current_user), db: DatabaseConnection = Depends(get_db)
):
    o = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not o or (o["user_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(404, "Order not found")
    try:
        db.execute("BEGIN")
        items = db.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)
        ).fetchall()
        for it in items:
            db.execute(
                "UPDATE products SET stock = stock + ? WHERE id = ?",
                (it["quantity"], it["product_id"]),
            )
        db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Cancel failed")
    return Response(status_code=204)


# ----------------------------- FRONTEND -------------------------------------
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Shop Test Lab v3.4</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; margin: 0; background: #f4f6f8; color: #222; }
  header { background: #1f2937; color: white; padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; }
  header h1 { margin: 0; font-size: 20px; }
  header .user { font-size: 14px; display: flex; align-items: center; gap: 10px; }
  .badge { background: #2563eb; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 600; }
  .badge.admin { background: #dc2626; }
  .badge.guest { background: #6b7280; }
  .container { max-width: 1080px; margin: 24px auto; padding: 0 16px; }
  .grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
  .card { background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 20px; }
  .product { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #eee; gap: 12px; }
  .product:last-child { border-bottom: none; }
  .actions { display: flex; gap: 6px; flex-shrink: 0; }
  button { background: #2563eb; color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-weight: 600; }
  button:hover { background: #1d4ed8; }
  button.secondary { background: #6b7280; }
  button.secondary:hover { background: #4b5563; }
  button.danger { background: #dc2626; }
  button.danger:hover { background: #b91c1c; }
  button.small { padding: 4px 10px; font-size: 13px; }
  input, textarea { padding: 8px 10px; border: 1px solid #ccc; border-radius: 6px; width: 100%; margin-bottom: 8px; font-family: inherit; }
  textarea { resize: vertical; min-height: 48px; }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .cart-item { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px dashed #ddd; font-size: 14px; }
  .cart-total { font-weight: bold; margin-top: 10px; text-align: right; }
  .auth-tabs { display: flex; gap: 8px; margin-bottom: 12px; }
  .auth-tabs button { flex: 1; }
  .hidden { display: none !important; }
  .msg { padding: 8px; border-radius: 6px; margin-top: 8px; font-size: 14px; }
  .msg.ok { background: #d1fae5; color: #065f46; }
  .msg.err { background: #fee2e2; color: #991b1b; }
  .muted { color: #6b7280; font-size: 13px; }
  .admin-panel { background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; padding: 12px; margin-bottom: 16px; }
  .admin-panel h3 { margin: 0 0 10px 0; color: #9a3412; font-size: 15px; }
  .editing { background: #fefce8; border-left: 3px solid #eab308; padding-left: 8px; }
  .inline-edit { display: grid; grid-template-columns: 2fr 3fr 1fr 1fr auto auto; gap: 6px; align-items: center; width: 100%; }
  .inline-edit input { margin: 0; padding: 4px 8px; }
</style>
</head>
<body data-testid="app-root">

<!-- ================= HEADER ================= -->
<header data-testid="app-header">
  <h1 data-testid="app-title">🛒 Shop Test Lab v3.4</h1>

  <!-- Session indicator: renders differently per role.
       data-session-state carries the machine-readable state. -->
  <div class="user"
       id="userBox"
       data-testid="user-box"
       data-session-state="guest"></div>
</header>

<div class="container">
  <div class="grid">

    <!-- ================= PRODUCTS PANEL ================= -->
    <div class="card" data-testid="products-card">
      <h2 id="productsHeading" data-testid="products-heading">Products</h2>

      <!-- Admin-only: add product form -->
      <div id="adminPanel"
           class="admin-panel hidden"
           data-testid="admin-panel"
           data-visible="false">
        <h3>➕ Add New Product (Admin)</h3>
        <input id="npName"
               data-testid="admin-new-product-name"
               placeholder="Product name (required)" />
        <textarea id="npDesc"
                  data-testid="admin-new-product-description"
                  placeholder="Description (optional)"></textarea>
        <div class="row">
          <input id="npPrice"
                 data-testid="admin-new-product-price"
                 type="number" step="0.01" min="0.01"
                 placeholder="Price (e.g. 19.99)" />
          <input id="npStock"
                 data-testid="admin-new-product-stock"
                 type="number" min="0" step="1"
                 placeholder="Stock quantity" />
        </div>
        <button data-testid="admin-create-product-btn" onclick="createProduct()">Create Product</button>
        <button data-testid="admin-clear-product-form-btn" class="secondary" onclick="clearProductForm()">Clear</button>
        <div id="npMsg" data-testid="admin-create-msg"></div>
      </div>

      <!-- Product list: each row gets product-row-<id> -->
      <div id="products" data-testid="product-list"></div>
    </div>

    <!-- ================= RIGHT COLUMN ================= -->
    <div>

      <!-- AUTH CARD -->
      <div class="card"
           id="authCard"
           data-testid="auth-card"
           data-auth-mode="login">
        <div id="guestHint"
             class="muted"
             data-testid="guest-hint"
             style="margin-bottom:10px;">
          Browsing as guest. Your cart is saved to a cookie.
        </div>

        <div class="auth-tabs" id="authTabs" data-testid="auth-tabs">
          <button data-testid="toggle-register-btn"
                  onclick="toggleAuthMode()"
                  id="tabRegister"
                  class="secondary">Register</button>
        </div>

        <div id="loginForm" data-testid="login-form">
          <input id="loginUser" data-testid="login-username" placeholder="username" />
          <input id="loginPass" data-testid="login-password" type="password" placeholder="password" />
          <button data-testid="login-submit-btn" onclick="doLogin()" style="width:100%;">Login</button>
        </div>

        <div id="registerForm" class="hidden" data-testid="register-form">
          <input id="regUser" data-testid="register-username" placeholder="username" />
          <input id="regPass" data-testid="register-password" type="password" placeholder="password" />
          <button data-testid="register-submit-btn" onclick="doRegister()" style="width:100%;">Create Account</button>
        </div>

        <div id="authMsg" data-testid="auth-msg"></div>
      </div>

      <!-- CART CARD (hidden for admins) -->
      <div class="card"
           id="cartCard"
           data-testid="cart-card"
           data-visible="true">
        <h2>Cart</h2>
        <div id="cartItems" data-testid="cart-items"></div>
        <div class="cart-total" id="cartTotal" data-testid="cart-total">Total: $0.00</div>
        <button id="checkoutBtn"
                data-testid="checkout-btn"
                data-enabled="false"
                style="margin-top:10px; width:100%;"
                onclick="checkout()">Checkout</button>
        <div id="cartMsg" data-testid="cart-msg"></div>
      </div>

      <!-- ORDERS CARD -->
      <div class="card hidden" id="ordersCard" data-testid="orders-card" data-visible="false">
        <h2>My Orders</h2>
        <div id="orders" data-testid="orders-list"></div>
      </div>

    </div>
  </div>
</div>

<script>
let token = localStorage.getItem("token") || null;
let user  = null;              // {id, username, role}
let editingId = null;
let authMode = "login";

function authHeaders(extra = {}) {
  const h = { ...extra };
  if (token) h["Authorization"] = "Bearer " + token;
  return h;
}
function jsonHeaders() {
  return authHeaders({ "Content-Type": "application/json" });
}

// ---- Auth mode toggle ---------------------------------------------------
function toggleAuthMode() {
  authMode = authMode === "login" ? "register" : "login";
  const isRegister = authMode === "register";

  document.getElementById("loginForm").classList.toggle("hidden", isRegister);
  document.getElementById("registerForm").classList.toggle("hidden", !isRegister);

  const btn = document.getElementById("tabRegister");
  btn.textContent = isRegister ? "← Back to Login" : "Register";
  btn.classList.toggle("secondary", !isRegister);

  // testid reflects the mode
  document.getElementById("authCard").dataset.authMode = authMode;
}

function resetAuthMode() {
  authMode = "login";
  document.getElementById("loginForm").classList.remove("hidden");
  document.getElementById("registerForm").classList.add("hidden");
  const btn = document.getElementById("tabRegister");
  if (btn) {
    btn.textContent = "Register";
    btn.classList.add("secondary");
  }
  document.getElementById("authCard").dataset.authMode = "login";
}

function setMsg(elId, text, ok = true) {
  const el = document.getElementById(elId);
  el.innerHTML = `<div class="msg ${ok?'ok':'err'}" data-testid="${elId}-${ok?'ok':'err'}">${text}</div>`;
}

// ---- Session UI ---------------------------------------------------------
function isAdmin()    { return user && user.role === "admin"; }
function isLoggedIn() { return !!user; }

function renderUserBox() {
  const box = document.getElementById("userBox");
  if (user) {
    const badgeClass = user.role === "admin" ? "badge admin" : "badge";
    box.dataset.sessionState = user.role;   // "admin" | "customer"
    box.innerHTML = `
      <span data-testid="session-username">${user.username}</span>
      <span class="${badgeClass}" data-testid="role-badge" data-role="${user.role}">${user.role}</span>
      <button class="secondary"
              data-testid="logout-btn"
              onclick="logout()">Logout</button>
    `;
  } else {
    box.dataset.sessionState = "guest";
    box.innerHTML = `<span class="badge guest" data-testid="role-badge" data-role="guest">guest</span>`;
  }
}

function applyRoleUI() {
  const loggedIn = isLoggedIn();
  const admin = isAdmin();

  resetAuthMode();

  document.getElementById("authTabs").classList.toggle("hidden", loggedIn);
  document.getElementById("loginForm").classList.toggle("hidden", loggedIn);
  document.getElementById("registerForm").classList.add("hidden");
  document.getElementById("guestHint").classList.toggle("hidden", loggedIn);

  document.getElementById("ordersCard").classList.toggle("hidden", !loggedIn);
  document.getElementById("ordersCard").dataset.visible = String(loggedIn);

  document.getElementById("cartCard").classList.toggle("hidden", admin);
  document.getElementById("cartCard").dataset.visible = String(!admin);

  document.getElementById("adminPanel").classList.toggle("hidden", !admin);
  document.getElementById("adminPanel").dataset.visible = String(admin);

  document.getElementById("productsHeading").textContent =
    admin ? "Inventory (Admin)" : "Products";
}

// ---- Auth actions -------------------------------------------------------
async function doRegister() {
  const u = regUser.value.trim(), p = regPass.value;
  const r = await fetch("/api/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: u, password: p })
  });
  const j = await r.json();
  setMsg("authMsg", r.ok ? "Registered! Now log in." : (j.detail || "Error"), r.ok);
  if (r.ok) {
    resetAuthMode();
    document.getElementById("loginUser").value = u;
  }
}

async function doLogin() {
  const u = loginUser.value.trim(), p = loginPass.value;
  const r = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: u, password: p })
  });
  const j = await r.json();
  if (!r.ok) { setMsg("authMsg", j.detail || "Login failed", false); return; }
  token = j.access_token;
  localStorage.setItem("token", token);

  await fetch("/api/cart/merge", { method: "POST", headers: authHeaders() });

  await loadMe();
  setMsg("authMsg", "Logged in ✔", true);
  await loadProducts();
  await loadCart();
  if (user) loadOrders();
}

function logout() {
  token = null; user = null; editingId = null;
  localStorage.removeItem("token");
  renderUserBox();
  applyRoleUI();
  loadProducts();
  loadCart();
  document.getElementById("orders").innerHTML = "";
}

async function loadMe() {
  if (!token) { user = null; renderUserBox(); applyRoleUI(); return; }
  const r = await fetch("/api/me", { headers: authHeaders() });
  if (!r.ok) { user = null; token = null; localStorage.removeItem("token"); }
  else user = await r.json();
  renderUserBox();
  applyRoleUI();
}

// ---- Products -----------------------------------------------------------
async function loadProducts() {
  const r = await fetch("/api/products");
  const items = await r.json();
  const admin = isAdmin();

  const container = document.getElementById("products");
  if (!items.length) {
    container.innerHTML = "<div class='muted' data-testid='products-empty'>No products.</div>";
    return;
  }

  container.innerHTML = items.map(p => {
    if (admin) {
      if (editingId === p.id) {
        return `
          <div class="product editing"
               data-testid="product-row-${p.id}"
               data-editing="true">
            <div class="inline-edit">
              <input id="eName-${p.id}"  data-testid="edit-name-${p.id}"  value="${escapeAttr(p.name)}"  placeholder="name" />
              <input id="eDesc-${p.id}"  data-testid="edit-desc-${p.id}"  value="${escapeAttr(p.description || '')}" placeholder="description" />
              <input id="ePrice-${p.id}" data-testid="edit-price-${p.id}" type="number" step="0.01" min="0.01" value="${p.price}" />
              <input id="eStock-${p.id}" data-testid="edit-stock-${p.id}" type="number" min="0" step="1" value="${p.stock}" />
              <button class="small"            data-testid="save-edit-${p.id}"   onclick="saveEdit(${p.id})">Save</button>
              <button class="small secondary"  data-testid="cancel-edit-${p.id}" onclick="cancelEdit()">Cancel</button>
            </div>
          </div>`;
      }
      return `
        <div class="product"
             data-testid="product-row-${p.id}"
             data-product-id="${p.id}"
             data-editing="false">
          <div>
            <div><strong data-testid="product-name-${p.id}">${escapeHtml(p.name)}</strong></div>
            <div class="muted" data-testid="product-meta-${p.id}">
              ${escapeHtml(p.description || '')} — $${p.price.toFixed(2)} — stock: ${p.stock}
            </div>
          </div>
          <div class="actions">
            <button class="small secondary"
                    data-testid="edit-product-${p.id}"
                    onclick="startEdit(${p.id})">Edit</button>
            <button class="small danger"
                    data-testid="delete-product-${p.id}"
                    onclick="deleteProduct(${p.id})">Delete</button>
          </div>
        </div>`;
    }
    return `
      <div class="product"
           data-testid="product-row-${p.id}"
           data-product-id="${p.id}">
        <div>
          <div><strong data-testid="product-name-${p.id}">${escapeHtml(p.name)}</strong></div>
          <div class="muted" data-testid="product-meta-${p.id}">
            ${escapeHtml(p.description || '')} — $${p.price.toFixed(2)} — stock: ${p.stock}
          </div>
        </div>
        <div class="actions">
          <button data-testid="add-to-cart-${p.id}"
                  onclick="addToCart(${p.id})">Add to Cart</button>
        </div>
      </div>`;
  }).join("");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

// ---- Admin: create / edit / delete --------------------------------------
function clearProductForm() {
  document.getElementById("npName").value = "";
  document.getElementById("npDesc").value = "";
  document.getElementById("npPrice").value = "";
  document.getElementById("npStock").value = "";
  document.getElementById("npMsg").innerHTML = "";
}

async function createProduct() {
  const name = document.getElementById("npName").value.trim();
  const description = document.getElementById("npDesc").value.trim();
  const price = parseFloat(document.getElementById("npPrice").value);
  const stock = parseInt(document.getElementById("npStock").value, 10);

  if (!name) { setMsg("npMsg", "Name is required", false); return; }
  if (!(price > 0)) { setMsg("npMsg", "Price must be > 0", false); return; }
  if (!(stock >= 0)) { setMsg("npMsg", "Stock must be >= 0", false); return; }

  const r = await fetch("/api/products", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ name, description, price, stock })
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { setMsg("npMsg", j.detail || "Create failed", false); return; }
  setMsg("npMsg", `Created "${j.name}" (#${j.id})`, true);
  clearProductForm();
  loadProducts();
}

function startEdit(id) { editingId = id; loadProducts(); }
function cancelEdit() { editingId = null; loadProducts(); }

async function saveEdit(id) {
  const name = document.getElementById("eName-" + id).value.trim();
  const description = document.getElementById("eDesc-" + id).value.trim();
  const price = parseFloat(document.getElementById("ePrice-" + id).value);
  const stock = parseInt(document.getElementById("eStock-" + id).value, 10);

  if (!name) { alert("Name required"); return; }
  if (!(price > 0)) { alert("Price must be > 0"); return; }
  if (!(stock >= 0)) { alert("Stock must be >= 0"); return; }

  const r = await fetch("/api/products/" + id, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify({ name, description, price, stock })
  });
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    alert(j.detail || "Update failed");
    return;
  }
  editingId = null;
  loadProducts();
}

async function deleteProduct(productId) {
  if (!confirm("Delete this product?")) return;
  const r = await fetch("/api/products/" + productId, {
    method: "DELETE",
    headers: authHeaders()
  });
  if (r.status === 204) {
    loadProducts();
  } else {
    const j = await r.json().catch(() => ({}));
    alert(j.detail || "Delete failed");
  }
}

// ---- Cart ---------------------------------------------------------------
async function addToCart(productId) {
  const r = await fetch("/api/cart/add", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ product_id: productId, quantity: 1 })
  });
  const j = await r.json();
  if (!r.ok) { alert(j.detail || "Error"); return; }
  loadCart();
}

async function loadCart() {
  if (isAdmin()) return;

  const r = await fetch("/api/cart", { headers: authHeaders() });
  const j = await r.json();

  document.getElementById("cartItems").innerHTML = j.items.length
    ? j.items.map(i => `
        <div class="cart-item"
             data-testid="cart-row-${i.product_id}"
             data-product-id="${i.product_id}"
             data-quantity="${i.quantity}">
          <span data-testid="cart-item-name-${i.product_id}">${escapeHtml(i.name)} × ${i.quantity}</span>
          <span>
            <span data-testid="cart-item-subtotal-${i.product_id}">$${(i.price * i.quantity).toFixed(2)}</span>
            <button class="secondary small"
                    data-testid="cart-remove-${i.product_id}"
                    style="margin-left:6px;"
                    onclick="removeItem(${i.product_id})">✕</button>
          </span>
        </div>`).join("")
    : "<div class='muted' data-testid='cart-empty'>Empty</div>";

  document.getElementById("cartTotal").textContent = "Total: $" + j.total.toFixed(2);
  document.getElementById("cartTotal").dataset.total = j.total.toFixed(2);

  const co = document.getElementById("checkoutBtn");
  const loggedIn = isLoggedIn();
  co.disabled = !loggedIn;
  co.dataset.enabled = String(loggedIn);
  co.textContent = loggedIn ? "Checkout" : "Log in to checkout";
  co.style.opacity = loggedIn ? "1" : "0.6";
  co.style.cursor = loggedIn ? "pointer" : "not-allowed";
}

async function removeItem(productId) {
  const r = await fetch("/api/cart/item/" + productId, {
    method: "DELETE",
    headers: authHeaders()
  });
  if (!r.ok && r.status !== 204) {
    const j = await r.json().catch(() => ({}));
    alert(j.detail || "Remove failed");
  }
  loadCart();
}

async function checkout() {
  const r = await fetch("/api/checkout", { method: "POST", headers: authHeaders() });
  const j = await r.json();
  if (!r.ok) { setMsg("cartMsg", j.detail || "Checkout failed", false); return; }
  setMsg("cartMsg", `Order ${j.order_id.slice(0,8)}… placed for $${j.total}`, true);
  loadCart(); loadProducts(); loadOrders();
}

async function loadOrders() {
  if (!user) return;
  const r = await fetch("/api/orders", { headers: authHeaders() });
  const orders = await r.json();
  document.getElementById("orders").innerHTML = orders.length
    ? orders.map(o => `
        <div style="border-bottom:1px solid #eee; padding:8px 0;"
             data-testid="order-row-${o.id}"
             data-order-id="${o.id}">
          <div data-testid="order-summary-${o.id}">
            <strong>${o.id.slice(0,8)}…</strong> — $${o.total.toFixed(2)} — ${o.status}
          </div>
          <div class="muted" data-testid="order-items-${o.id}">
            ${o.items.map(i => `${escapeHtml(i.product_name)} ×${i.quantity}`).join(", ")}
          </div>
        </div>`).join("")
    : "<div class='muted' data-testid='orders-empty'>No orders yet</div>";
}

// ---- Init ---------------------------------------------------------------
(async function init() {
  await loadMe();
  await loadProducts();
  await loadCart();
  if (user) loadOrders();
})();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


# ----------------------------- ENTRYPOINT -----------------------------------
if __name__ == "__main__":
    print(f"Database: {database_description()}")
    print("Server: http://localhost:8000  |  Docs: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)