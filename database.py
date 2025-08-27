import sqlite3
import json

class Database:
    def __init__(self, db_conn):
        self.conn = db_conn
        self._create_table()

    @classmethod
    def get(cls, db_path):
        """Creates and returns a connected Database instance."""
        print(f"Initializing DB connection to: {db_path}")
        return Database(sqlite3.connect(db_path))

    def _create_table(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    extra_prompt TEXT NOT NULL,
                    history TEXT NOT NULL,
                    bot_name TEXT NOT NULL,
                    last_messages TEXT NOT NULL
                )
            """)

    def get_conversation(self, conversation_id):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT prompt, extra_prompt, history, bot_name, last_messages "
                "FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            row = cursor.fetchone()
            if row:
                prompt = row[0]
                extra_prompt = row[1]
                history = json.loads(row[2])
                bot_name = row[3]
                last_messages = json.loads(row[4])
                return prompt, extra_prompt, history, bot_name, last_messages
            return None

    def save(
        self, conversation_id, prompt, extra_prompt,
        history, bot_name, last_messages
    ):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO conversations "
                "(id, prompt, extra_prompt, history, bot_name, last_messages) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    conversation_id, prompt, extra_prompt, json.dumps(history),
                    bot_name, json.dumps(last_messages)
                ),
            )

    def delete(self, conversation_id):
        with self.conn:
            self.conn.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,),
            )
