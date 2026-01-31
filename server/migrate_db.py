"""
Database migration script to create Chat and Message tables
Run this after updating the models
"""
import asyncio
from app.core.database.database import create_db_and_tables

async def migrate():
    """Create database tables"""
    print("Creating database tables...")
    await create_db_and_tables()
    print("Database tables created successfully!")

if __name__ == "__main__":
    asyncio.run(migrate())
