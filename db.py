import json
import os
import sqlite3
from typing import Any


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                user_phone TEXT,
                equipment_type TEXT,
                attachments TEXT,
                hours INTEGER,
                date TEXT,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT,
                order_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL DEFAULT 'equipment',
                title TEXT NOT NULL,
                description TEXT,
                price_per_hour INTEGER,
                photo TEXT,
                attachments_enabled INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        conn.close()
        self._seed_catalog_if_empty()

    def _seed_catalog_if_empty(self) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS count FROM catalog_items")
        count = int(cur.fetchone()["count"] or 0)
        if count == 0:
            defaults = [
                (
                    "equipment",
                    "Экскаватор-погрузчик",
                    "Hidromek HMK 102S, 2022 г.в.",
                    3500,
                    "assets/traktor.jpg",
                    1,
                ),
                (
                    "equipment",
                    "Автокран",
                    "Автокран вездеход «Клинцы» 25 т. 28 м.",
                    3500,
                    "assets/kran_2.jpg",
                    0,
                ),
                (
                    "equipment",
                    "Самосвал",
                    "Shacman X3000 30 тонн",
                    3000,
                    "assets/samosval_3.jpg",
                    0,
                ),
            ]
            cur.executemany(
                """
                INSERT INTO catalog_items (
                    item_type, title, description, price_per_hour, photo, attachments_enabled
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                defaults,
            )
            conn.commit()
        conn.close()

    def save_user(self, user_id: int, username: str | None, full_name: str) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
            """,
            (user_id, username, full_name),
        )
        conn.commit()
        conn.close()

    def create_order(self, data: dict[str, Any]) -> int:
        attachments = data.get("attachments")
        attachments_json = json.dumps(attachments, ensure_ascii=False) if attachments else None
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO orders (
                user_id, user_name, user_phone, equipment_type, attachments, hours, date, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("customer_user_id") or data.get("user_id"),
                data.get("user_name"),
                data.get("user_phone"),
                data.get("equipment_type"),
                attachments_json,
                data.get("hours"),
                data.get("date"),
                "new",
            ),
        )
        order_id = cur.lastrowid
        conn.commit()
        conn.close()
        return int(order_id)

    def create_catalog_item(self, data: dict[str, Any]) -> int:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO catalog_items (
                item_type, title, description, price_per_hour, photo, attachments_enabled, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                data.get("item_type", "equipment"),
                data.get("title"),
                data.get("description"),
                data.get("price_per_hour"),
                data.get("photo"),
                1 if data.get("attachments_enabled") else 0,
            ),
        )
        item_id = cur.lastrowid
        conn.commit()
        conn.close()
        return int(item_id)

    def list_catalog_items(self, active_only: bool = True) -> list[dict[str, Any]]:
        conn = self._connect()
        cur = conn.cursor()
        sql = "SELECT * FROM catalog_items"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY item_type, id"
        cur.execute(sql)
        rows = cur.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_catalog_item(self, item_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM catalog_items WHERE id = ?", (item_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def delete_catalog_item(self, item_id: int) -> bool:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("UPDATE catalog_items SET is_active = 0 WHERE id = ?", (item_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def get_order(self, order_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        result = dict(row)
        if result.get("attachments"):
            result["attachments"] = json.loads(result["attachments"])
        return result

    def update_order_status(self, order_id: int, status: str) -> bool:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        updated = cur.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def delete_order(self, order_id: int) -> bool:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def orders_stats(self) -> dict[str, int]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) AS new_count,
                SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) AS confirmed_count,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_count,
                SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_count,
                COUNT(*) AS total_count
            FROM orders
            """
        )
        row = cur.fetchone()
        conn.close()
        return {
            "new": int(row["new_count"] or 0),
            "confirmed": int(row["confirmed_count"] or 0),
            "completed": int(row["completed_count"] or 0),
            "cancelled": int(row["cancelled_count"] or 0),
            "total": int(row["total_count"] or 0),
        }

    def list_orders(self, limit: int = 30) -> list[dict[str, Any]]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_name, equipment_type, status, created_at FROM orders ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def log_admin_action(self, admin_id: int, action: str, order_id: int | None = None) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO admin_log (admin_id, action, order_id) VALUES (?, ?, ?)",
            (admin_id, action, order_id),
        )
        conn.commit()
        conn.close()
