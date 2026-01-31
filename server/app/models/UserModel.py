from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy.orm import relationship, Mapped

from app.models.BaseDatabase import Base

class User(SQLAlchemyBaseUserTableUUID, Base):
    pass