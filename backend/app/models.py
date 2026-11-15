"""SQLAlchemy ORM models for batches, images, results (docs/data_model.md)."""
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Batch(Base):
    __tablename__ = "batches"

    batch_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="created")
    finalized: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)
    total_images: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    images: Mapped[list["Image"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class Image(Base):
    __tablename__ = "images"

    image_id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.batch_id"), index=True)
    original_name: Mapped[str] = mapped_column(String)
    stored_path: Mapped[str] = mapped_column(String)
    thumbnail_path: Mapped[str] = mapped_column(String)
    file_size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String, index=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    upload_order: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="uploaded", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    claimed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)

    batch: Mapped[Batch] = relationship(back_populates="images")
    result: Mapped["Result | None"] = relationship(back_populates="image", cascade="all, delete-orphan", uselist=False)


class Result(Base):
    __tablename__ = "results"

    image_id: Mapped[str] = mapped_column(ForeignKey("images.image_id"), primary_key=True)
    status: Mapped[str] = mapped_column(String, index=True)
    primary_flag: Mapped[str | None] = mapped_column(String, nullable=True)
    flag_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    awb: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    awb_suggestion: Mapped[str | None] = mapped_column(String, nullable=True)
    awb_source: Mapped[str | None] = mapped_column(String, nullable=True)
    awb_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    length_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    width_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    dimensions_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    courier: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[str] = mapped_column(Text, default="{}")  # JSON blob
    pipeline_version: Mapped[str] = mapped_column(String, default="")
    processing_ms: Mapped[int] = mapped_column(Integer, default=0)
    processed_at: Mapped[str] = mapped_column(String)

    image: Mapped[Image] = relationship(back_populates="result")
