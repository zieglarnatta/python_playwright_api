import sqlite3
import uuid

import pytest
from fastapi import HTTPException

import shop


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(shop, "DATABASE_URL", None)
    monkeypatch.setattr(shop, "ACTIVE_DATABASE_URL", None)
    monkeypatch.setattr(shop, "DATABASE_SELECTED", False)
    monkeypatch.setattr(shop, "psycopg2", None)
    monkeypatch.setattr(shop, "DB_PATH", tmp_path / "shop.db")
    shop.init_db()
    connection = shop.connect_db()
    yield connection
    connection.close()


def test_guest_checkout_deducts_stock_and_keeps_order_private(isolated_db):
    owner = {"user_id": None, "guest_id": str(uuid.uuid4()), "user": None}
    product = shop.get_product(1, isolated_db)
    initial_stock = product["stock"]

    shop.cart_add(shop.CartItemIn(product_id=1, quantity=2), owner, isolated_db)
    shop.cart_add(shop.CartItemIn(product_id=1, quantity=1), owner, isolated_db)

    assert shop.cart_view(owner, isolated_db)["items"][0]["quantity"] == 3
    assert shop.get_product(1, isolated_db)["stock"] == initial_stock

    result = shop.checkout(owner, isolated_db)

    assert result["status"] == "PAID"
    assert shop.get_product(1, isolated_db)["stock"] == initial_stock - 3
    assert shop.cart_view(owner, isolated_db)["items"] == []
    assert shop.get_order(result["order_id"], owner, isolated_db)["guest_id"] == owner[
        "guest_id"
    ]

    other_guest = {"user_id": None, "guest_id": str(uuid.uuid4()), "user": None}
    with pytest.raises(HTTPException) as error:
        shop.get_order(result["order_id"], other_guest, isolated_db)
    assert error.value.status_code == 404


def test_authenticated_cart_merge_and_checkout(isolated_db):
    user = dict(
        isolated_db.execute(
            "SELECT * FROM users WHERE username = 'customer'"
        ).fetchone()
    )
    guest_id = str(uuid.uuid4())
    guest_owner = {"user_id": None, "guest_id": guest_id, "user": None}
    user_owner = {
        "user_id": user["id"],
        "guest_id": guest_id,
        "user": user,
    }
    initial_stock = shop.get_product(1, isolated_db)["stock"]

    shop.cart_add(shop.CartItemIn(product_id=1, quantity=1), guest_owner, isolated_db)
    shop.cart_add(shop.CartItemIn(product_id=1, quantity=1), user_owner, isolated_db)
    assert shop.cart_merge(guest_id, user, isolated_db)["merged"] == 1
    assert shop.cart_view(user_owner, isolated_db)["items"][0]["quantity"] == 2

    result = shop.checkout(user_owner, isolated_db)

    assert shop.get_product(1, isolated_db)["stock"] == initial_stock - 2
    order = shop.get_order(result["order_id"], user_owner, isolated_db)
    assert order["user_id"] == user["id"]
    assert order["guest_id"] is None


def test_seeded_customer_and_admin_accounts_exist(isolated_db):
    users = {
        row["username"]: row
        for row in isolated_db.execute(
            "SELECT username, password_hash, role FROM users"
        ).fetchall()
    }

    assert users["admin"]["role"] == "admin"
    assert shop.verify_password("admin1234", users["admin"]["password_hash"])
    assert users["customer"]["role"] == "customer"
    assert shop.verify_password(
        "customer1234", users["customer"]["password_hash"]
    )


def test_sqlite_order_migration_preserves_existing_orders(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer',
            created_at TEXT NOT NULL
        );
        CREATE TABLE orders (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            total REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        );
        INSERT INTO users (username, password_hash, created_at)
            VALUES ('existing', 'hash', '2026-01-01');
        INSERT INTO orders (id, user_id, total, status, created_at)
            VALUES ('existing-order', 1, 10, 'PAID', '2026-01-01');
        INSERT INTO order_items
            (order_id, product_id, product_name, price, quantity)
            VALUES ('existing-order', 1, 'Existing product', 10, 1);
        """
    )
    connection.commit()
    connection.close()

    monkeypatch.setattr(shop, "DATABASE_URL", None)
    monkeypatch.setattr(shop, "ACTIVE_DATABASE_URL", None)
    monkeypatch.setattr(shop, "DATABASE_SELECTED", False)
    monkeypatch.setattr(shop, "psycopg2", None)
    monkeypatch.setattr(shop, "DB_PATH", db_path)
    shop.init_db()

    connection = shop.connect_db()
    migrated_order = connection.execute(
        "SELECT id, user_id, guest_id FROM orders WHERE id = 'existing-order'"
    ).fetchone()
    order_columns = {
        row["name"]: row for row in connection.execute("PRAGMA table_info(orders)")
    }

    assert migrated_order["user_id"] == 1
    assert migrated_order["guest_id"] is None
    assert order_columns["user_id"]["notnull"] == 0
    assert "guest_id" in order_columns
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()
