import sqlite3
import json

class Database:
    def __init__(self, db_path='conversations.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.create_table()

    def create_table(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    history TEXT NOT NULL,
                    bot_name TEXT NOT NULL,
                    last_messages TEXT NOT NULL
                )
            """)

    def get(self, conversation_id):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT history, bot_name, last_messages FROM conversations WHERE id = ?", (conversation_id,))
            row = cursor.fetchone()
            if row:
                history = json.loads(row[0])
                bot_name = row[1]
                last_messages = json.loads(row[2])
                return history, bot_name, last_messages
            return None

    def save(self, conversation_id, history, bot_name, last_messages):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO conversations (id, history, bot_name, last_messages) VALUES (?, ?, ?, ?)",
                (conversation_id, json.dumps(history), bot_name, json.dumps(last_messages))
            )

    def delete(self, conversation_id):
        with self.conn:
            self.conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

db = Database()
