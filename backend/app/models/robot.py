from datetime import datetime

from sqlalchemy import Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class Robot(Base):
    __tablename__ = "robots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    robot_id: Mapped[str] = mapped_column(String, unique=True, index=True)

    battery: Mapped[float] = mapped_column(Float, default=100.0)
    temperature: Mapped[float] = mapped_column(Float, default=35.0)
    x: Mapped[float] = mapped_column(Float, default=0.0)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    speed: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="IDLE")

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Robot {self.robot_id} status={self.status}>"
