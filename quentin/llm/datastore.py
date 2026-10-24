from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Any, List

class ModelPerformanceDataStore:
    """
    一个简单的 SQLite 数据存储，用于记录和查询模型性能。
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialize_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _initialize_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS model_performance (
                    model_name TEXT,
                    task_domain TEXT,
                    success INTEGER,
                    latency_sec REAL,
                    cost REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def record_performance(
        self,
        model_name: str,
        task_domain: str,
        success: bool,
        latency_sec: float,
        cost: float | None,
    ):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO model_performance (model_name, task_domain, success, latency_sec, cost)
                VALUES (?, ?, ?, ?, ?)
                """,
                (model_name, task_domain, 1 if success else 0, latency_sec, cost),
            )
            conn.commit()

    def get_stats(self, model_name: str, task_domain: str | None = None) -> Dict[str, Any]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if task_domain:
                cursor.execute(
                    """
                    SELECT COUNT(*), AVG(success), AVG(latency_sec), AVG(cost)
                    FROM model_performance
                    WHERE model_name = ? AND task_domain = ?
                    """,
                    (model_name, task_domain),
                )
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*), AVG(success), AVG(latency_sec), AVG(cost)
                    FROM model_performance
                    WHERE model_name = ?
                    """,
                    (model_name,),
                )
            
            row = cursor.fetchone()
            if row and row[0] > 0:
                return {
                    "calls": row[0],
                    "success_rate": row[1],
                    "avg_latency_sec": row[2],
                    "avg_cost": row[3],
                }
        return {
            "calls": 0,
            "success_rate": 0.0,
            "avg_latency_sec": 0.0,
            "avg_cost": None,
        }

    def get_all_model_stats(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT model_name, COUNT(*), AVG(success), AVG(latency_sec), AVG(cost)
                FROM model_performance
                GROUP BY model_name
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "model_name": row[0],
                    "calls": row[1],
                    "success_rate": row[2],
                    "avg_latency_sec": row[3],
                    "avg_cost": row[4],
                }
                for row in rows
            ]
