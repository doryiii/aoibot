import aiosqlite
import json

class Database:
    def __init__(self, db_path='conversations.db'):
        self.db_path = db_path
        self.conn = None

    @classmethod
    async def get(cls, db_path='conversations.db'):
        """Asynchronously creates and returns a connected Database instance."""
        print(f"Initializing DB connection to: {db_path}")
        db = Database(db_path)
        db.conn = await aiosqlite.connect(db.db_path)
        await db._create_table()
        return db

    async def _create_table(self):
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                history TEXT NOT NULL,
                bot_name TEXT NOT NULL,
                last_messages TEXT NOT NULL
            )
        """)
        await self.conn.commit()

    async def get_conversation(self, conversation_id):
        async with self.conn.execute("SELECT history, bot_name, last_messages FROM conversations WHERE id = ?", (conversation_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                history = json.loads(row[0])
                bot_name = row[1]
                last_messages = json.loads(row[2])
                return history, bot_name, last_messages
            return None

    async def save(self, conversation_id, history, bot_name, last_messages):
        await self.conn.execute(
            "INSERT OR REPLACE INTO conversations (id, history, bot_name, last_messages) VALUES (?, ?, ?, ?)",
            (conversation_id, json.dumps(history), bot_name, json.dumps(last_messages))
        )
        await self.conn.commit()

    async def delete(self, conversation_id):
        await self.conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.conn = None

# To use this, you would typically do this in your main application file:
#
# import asyncio
# from database import Database
#
# async def main():
#     db = await Database.get()
#     # now you can use db.get_conversation, db.save, etc.
#     await db.close()
#
# if __name__ == "__main__":
#     asyncio.run(main())
