from dotenv import dotenv_values, load_dotenv
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.ext.asyncio import create_async_engine
from fastapi_mail import ConnectionConfig
from sqlalchemy.orm import sessionmaker

load_dotenv()

config = dotenv_values(".env")
BASE_URL = config.get("BASE_URL")
BASE_FILE_PATH = config.get("BASE_FILE_PATH")
DATABASE_URL = config.get("DATABASE_URL")
SECRET = config.get("SECRET")
MAX_LIMIT = config.get("MAX_LIMIT", 100)
ORIGINS = config.get("ORIGINS").split(',')
COLLECTION_NAME = config.get("COLLECTION_NAME", "default")
COOKIE_SECURE = str(config.get("COOKIE_SECURE", "false")).lower() == "true"
COOKIE_SAMESITE = config.get("COOKIE_SAMESITE", "lax")

engine = create_async_engine(DATABASE_URL)


MAIL_USERNAME=str(config.get("MAIL_USERNAME"))
MAIL_PASSWORD=str(config.get("MAIL_PASSWORD"))
MAIL_FROM=str(config.get("MAIL_FROM"))
# MAIN_FROM_NAME=str(config.get("MAIN_FROM_NAME"))
MAIL_PORT=int(config.get("MAIL_PORT", 1025))
MAIL_SERVER=str(config.get("MAIL_SERVER", "127.0.0.1"))
MAIL_STARTTLS=bool(config.get("MAIL_STARTTLS", True))
MAIL_SSL_TLS=bool(config.get("MAIL_SSL_TLS", False))
USE_CREDENTIALS=bool(config.get("USE_CREDENTIALS", True))
VALIDATE_CERTS=bool(config.get("VALIDATE_CERTS", True))
GOOGLE_CLIENT_ID = config.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = config.get("GOOGLE_CLIENT_SECRET")
GOOGLE_SCOPE = config.get("GOOGLE_SCOPE")
GOOGLE_CALENDAR_SCOPES = config.get("GOOGLE_CALENDAR_SCOPES")
GOOGLE_CALENDAR_REDIRECT_URI = config.get("GOOGLE_CALENDAR_REDIRECT_URI")

email_conf =ConnectionConfig(
    MAIL_USERNAME=MAIL_USERNAME,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_FROM=MAIL_FROM,
    # MAIN_FROM_NAME=MAIN_FROM_NAME,
    MAIL_PORT=MAIL_PORT,
    MAIL_SERVER=MAIL_SERVER,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=USE_CREDENTIALS,
)
api_key = config.get("OPENAI_API_KEY")
GROQ_API_KEY = config.get("GROQ_API_KEY")

if COLLECTION_NAME == "":
    COLLECTION_NAME = "default"

# DATASET_DATABASE_URL = config.get("DATASET_DATABASE_URL")

# dataset_engine = create_engine(DATASET_DATABASE_URL)

# def get_database_engine():
#     return dataset_engine

# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=dataset_engine)

# def get_dataset_db():
    # db = SessionLocal()
    # try:
    #     yield db
    # finally:
    #     db.close()

# def initialize_tables_dataset():
#     """
#     Initialize the TABLE_SCHEMA meta table for storing schema analysis.
#     Creates the table if it does not exist.
#     """
#     conn = None
#     try:
#         conn = dataset_engine.connect()
#         conn.execute(text("""
#             CREATE TABLE IF NOT EXISTS TABLE_SCHEMA (
#                 table_name TEXT PRIMARY KEY,
#                 analysis JSONB,
#                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#                 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#             )
#         """))
#         conn.commit()
#     except Exception as e:
#         print(f"Error during table initialization: {e}")
#         raise
#     finally:
#         if conn:
            # conn.close()