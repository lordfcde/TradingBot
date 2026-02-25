import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime, timezone, timedelta

class DatabaseService:
    _pool = None

    @classmethod
    def get_pool(cls):
        if cls._pool is None:
            # Use environment variable DATABASE_URL
            db_url = os.environ.get("DATABASE_URL")
            if not db_url:
                print("⚠️ DATABASE_URL not set. Watchlist will not be saved to DB.")
                return None
            try:
                cls._pool = psycopg2.pool.SimpleConnectionPool(1, 10, db_url)
                if cls._pool:
                    print("✅ PostgreSQL connection pool created.")
                    cls.init_db()
            except Exception as e:
                print(f"❌ Error connecting to PostgreSQL: {e}")
        return cls._pool

    @classmethod
    def get_connection(cls):
        pool = cls.get_pool()
        if pool:
            try:
                return pool.getconn()
            except Exception as e:
                print(f"❌ Error getting DB connection: {e}")
        return None

    @classmethod
    def release_connection(cls, conn):
        if cls._pool and conn:
            cls._pool.putconn(conn)

    @classmethod
    def init_db(cls):
        conn = cls.get_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                # Table for active watchlist
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS watchlist (
                        symbol VARCHAR(10) PRIMARY KEY,
                        entry_time DOUBLE PRECISION NOT NULL,
                        display_time VARCHAR(50),
                        shark_data JSONB,
                        trinity_data JSONB,
                        signal_count INTEGER DEFAULT 1
                    );
                """)
                # Alter to add column for existing db
                cur.execute("""
                    ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS signal_count INTEGER DEFAULT 1;
                """)
                # Table for history
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS watchlist_history (
                        id SERIAL PRIMARY KEY,
                        date DATE NOT NULL,
                        symbol VARCHAR(10) NOT NULL,
                        UNIQUE(date, symbol)
                    );
                """)
                conn.commit()
                print("✅ Database tables verified.")
        except Exception as e:
            print(f"❌ Error initializing DB: {e}")
            conn.rollback()
        finally:
            cls.release_connection(conn)

    @classmethod
    def execute_query(cls, query, params=None, fetch=False):
        conn = cls.get_connection()
        if not conn:
            return None
        
        result = None
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                if fetch:
                    result = cur.fetchall()
                conn.commit()
        except Exception as e:
            print(f"❌ DB Query Error: {e} | Query: {query}")
            conn.rollback()
        finally:
            cls.release_connection(conn)
            
        return result
