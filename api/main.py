from datetime import datetime

import pytz

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import (
    create_engine,
    String,
    ForeignKey,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
)


# ============================================================
# DATABASE
# ============================================================

DATABASE_URL = "sqlite:////app/data/app.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


class Base(DeclarativeBase):
    pass


def get_db():
    with Session(engine) as db:
        yield db


# ============================================================
# DATABASE MODELS
# ============================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )


class Sequence(Base):
    """
    A named sequence.

    Example:

        id = 1
        name = "Morning"

    A sequence can contain its own independent
    ordering of users.
    """

    __tablename__ = "sequences"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True
    )


class SequenceOrder(Base):
    """
    Defines the user order for a particular sequence.

    Example:

        sequence_id  position  user_id
        -----------  --------  -------
        1            1         3
        1            2         1
        1            3         2

    Means sequence 1 is:

        3 -> 1 -> 2 -> 3 -> ...
    """

    __tablename__ = "sequence_orders"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    sequence_id: Mapped[int] = mapped_column(
        ForeignKey("sequences.id"),
        nullable=False
    )

    position: Mapped[int] = mapped_column(
        nullable=False
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "sequence_id",
            "position"
        ),
        UniqueConstraint(
            "sequence_id",
            "user_id"
        ),
    )


class SequenceEntry(Base):
    """
    Records each time a user is submitted
    for a particular sequence.
    """

    __tablename__ = "sequence_entries"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    sequence_id: Mapped[int] = mapped_column(
        ForeignKey("sequences.id"),
        nullable=False
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )


Base.metadata.create_all(engine)


# ============================================================
# PYDANTIC MODELS
# ============================================================

class UserCreate(BaseModel):
    name: str


class UserResponse(BaseModel):
    id: int
    name: str


class SequenceCreate(BaseModel):
    name: str


class SequenceResponse(BaseModel):
    id: int
    name: str


class OrderRequest(BaseModel):
    order: list[int]


class OrderResponse(BaseModel):
    position: int
    user_id: int


class SequenceCreateEntry(BaseModel):
    user_id: int


class SequenceEntryResponse(BaseModel):
    id: int
    sequence_id: int
    user_id: int
    timestamp: datetime


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="User Sequence API",
    description="API for users and user-created sequences."
)


# ============================================================
# BASIC
# ============================================================

@app.get("/")
def root():
    return {
        "message": "User Sequence API is running"
    }


# ============================================================
# USERS
# ============================================================

@app.get(
    "/users",
    response_model=list[UserResponse]
)
def get_users(
    db: Session = Depends(get_db)
):
    return (
        db.query(User)
        .order_by(User.id)
        .all()
    )


@app.get(
    "/users/{user_id}",
    response_model=UserResponse
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return user


@app.post(
    "/users",
    response_model=UserResponse,
    status_code=201
)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    user = User(
        name=user_data.name
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


# ============================================================
# SEQUENCES
# ============================================================

@app.post(
    "/sequences",
    response_model=SequenceResponse,
    status_code=201
)
def create_sequence(
    sequence_data: SequenceCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new sequence.

    Example:

        POST /sequences

        {
            "name": "Morning"
        }
    """

    existing = (
        db.query(Sequence)
        .filter(Sequence.name == sequence_data.name)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="A sequence with this name already exists"
        )

    sequence = Sequence(
        name=sequence_data.name
    )

    db.add(sequence)
    db.commit()
    db.refresh(sequence)

    return sequence


@app.get(
    "/sequences",
    response_model=list[SequenceResponse]
)
def get_sequences(
    db: Session = Depends(get_db)
):
    """
    Get all available sequences.
    """

    return (
        db.query(Sequence)
        .order_by(Sequence.id)
        .all()
    )


@app.get(
    "/sequences/{sequence_id}",
    response_model=SequenceResponse
)
def get_sequence(
    sequence_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a single sequence.
    """

    sequence = db.get(Sequence, sequence_id)

    if sequence is None:
        raise HTTPException(
            status_code=404,
            detail="Sequence not found"
        )

    return sequence


# ============================================================
# SEQUENCE ORDER
# ============================================================

@app.get(
    "/sequences/{sequence_id}/order",
    response_model=list[OrderResponse]
)
def get_sequence_order(
    sequence_id: int,
    db: Session = Depends(get_db)
):
    """
    Get the user order for a sequence.
    """

    sequence = db.get(Sequence, sequence_id)

    if sequence is None:
        raise HTTPException(
            status_code=404,
            detail="Sequence not found"
        )

    return (
        db.query(SequenceOrder)
        .filter(
            SequenceOrder.sequence_id == sequence_id
        )
        .order_by(SequenceOrder.position)
        .all()
    )


@app.put(
    "/sequences/{sequence_id}/order",
    response_model=list[OrderResponse]
)
def set_sequence_order(
    sequence_id: int,
    order_data: OrderRequest,
    db: Session = Depends(get_db)
):
    """
    Completely replace the order for one sequence.

    Example:

        PUT /sequences/1/order

        {
            "order": [3, 1, 2]
        }
    """

    sequence = db.get(Sequence, sequence_id)

    if sequence is None:
        raise HTTPException(
            status_code=404,
            detail="Sequence not found"
        )

    user_ids = order_data.order

    if len(user_ids) == 0:
        raise HTTPException(
            status_code=400,
            detail="Order cannot be empty"
        )

    if len(user_ids) != len(set(user_ids)):
        raise HTTPException(
            status_code=400,
            detail="User IDs cannot be duplicated"
        )

    users = (
        db.query(User)
        .filter(User.id.in_(user_ids))
        .all()
    )

    existing_ids = {
        user.id for user in users
    }

    missing_ids = set(user_ids) - existing_ids

    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Users not found: {sorted(missing_ids)}"
        )

    # Remove the existing order ONLY for this sequence.
    (
        db.query(SequenceOrder)
        .filter(
            SequenceOrder.sequence_id == sequence_id
        )
        .delete()
    )

    # Create the new order.
    for position, user_id in enumerate(
        user_ids,
        start=1
    ):
        db.add(
            SequenceOrder(
                sequence_id=sequence_id,
                position=position,
                user_id=user_id
            )
        )

    db.commit()

    return (
        db.query(SequenceOrder)
        .filter(
            SequenceOrder.sequence_id == sequence_id
        )
        .order_by(SequenceOrder.position)
        .all()
    )


# ============================================================
# SEQUENCE HISTORY
# ============================================================

@app.get(
    "/sequences/{sequence_id}/entries",
    response_model=list[SequenceEntryResponse]
)
def get_sequence_entries(
    sequence_id: int,
    db: Session = Depends(get_db)
):
    """
    Get the submission history for one sequence.
    """

    sequence = db.get(Sequence, sequence_id)

    if sequence is None:
        raise HTTPException(
            status_code=404,
            detail="Sequence not found"
        )

    return (
        db.query(SequenceEntry)
        .filter(
            SequenceEntry.sequence_id == sequence_id
        )
        .order_by(SequenceEntry.id)
        .all()
    )


@app.get(
    "/sequences/{sequence_id}/entries/recent",
    response_model=SequenceEntryResponse
)
def get_recent_sequence_entry(
    sequence_id: int,
    db: Session = Depends(get_db)
):
    """
    Get the most recent submission for one sequence.
    """

    sequence = db.get(Sequence, sequence_id)

    if sequence is None:
        raise HTTPException(
            status_code=404,
            detail="Sequence not found"
        )

    entry = (
        db.query(SequenceEntry)
        .filter(
            SequenceEntry.sequence_id == sequence_id
        )
        .order_by(SequenceEntry.id.desc())
        .first()
    )

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="No sequence entries exist"
        )

    return entry


# ============================================================
# NEXT USER
# ============================================================

@app.get(
    "/sequences/{sequence_id}/next"
)
def get_next_user(
    sequence_id: int,
    db: Session = Depends(get_db)
):
    """
    Determine which user is next for this sequence.
    """

    sequence = db.get(Sequence, sequence_id)

    if sequence is None:
        raise HTTPException(
            status_code=404,
            detail="Sequence not found"
        )

    ordered_users = (
        db.query(SequenceOrder)
        .filter(
            SequenceOrder.sequence_id == sequence_id
        )
        .order_by(SequenceOrder.position)
        .all()
    )

    if not ordered_users:
        raise HTTPException(
            status_code=400,
            detail="Sequence order has not been configured"
        )

    last_entry = (
        db.query(SequenceEntry)
        .filter(
            SequenceEntry.sequence_id == sequence_id
        )
        .order_by(SequenceEntry.id.desc())
        .first()
    )

    # Nothing has been submitted for this sequence.
    if last_entry is None:
        next_user = ordered_users[0]

    else:
        current_position = next(
            (
                item
                for item in ordered_users
                if item.user_id == last_entry.user_id
            ),
            None
        )

        if current_position is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Last user is no longer "
                    "in the sequence order"
                )
            )

        next_position = (
            current_position.position + 1
        )

        # Wrap around.
        if next_position > len(ordered_users):
            next_position = 1

        next_user = ordered_users[
            next_position - 1
        ]

    user = db.get(User, next_user.user_id)

    return {
        "sequence_id": sequence_id,
        "next_user_id": next_user.user_id,
        "position": next_user.position,
        "name": user.name
    }


# ============================================================
# ADD SEQUENCE ENTRY
# ============================================================

@app.post(
    "/sequences/{sequence_id}/entries",
    response_model=SequenceEntryResponse,
    status_code=201
)
def add_sequence_entry(
    sequence_id: int,
    sequence_data: SequenceCreateEntry,
    db: Session = Depends(get_db)
):
    """
    Submit a user to a particular sequence.

    The supplied user MUST be the next user
    according to that sequence's configured order.
    """

    sequence = db.get(Sequence, sequence_id)

    if sequence is None:
        raise HTTPException(
            status_code=404,
            detail="Sequence not found"
        )

    user_id = sequence_data.user_id

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    ordered_users = (
        db.query(SequenceOrder)
        .filter(
            SequenceOrder.sequence_id == sequence_id
        )
        .order_by(SequenceOrder.position)
        .all()
    )

    if not ordered_users:
        raise HTTPException(
            status_code=400,
            detail="Sequence order has not been configured"
        )

    # Get the most recent entry for THIS sequence.
    last_entry = (
        db.query(SequenceEntry)
        .filter(
            SequenceEntry.sequence_id == sequence_id
        )
        .order_by(SequenceEntry.id.desc())
        .first()
    )

    if last_entry is None:

        # First submission for this sequence.
        expected_user = ordered_users[0]

    else:

        current_position = next(
            (
                item
                for item in ordered_users
                if item.user_id == last_entry.user_id
            ),
            None
        )

        if current_position is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Last user is no longer "
                    "in the sequence order"
                )
            )

        next_position = (
            current_position.position + 1
        )

        # Wrap around.
        if next_position > len(ordered_users):
            next_position = 1

        expected_user = ordered_users[
            next_position - 1
        ]

    # Validate sequence.
    if user_id != expected_user.user_id:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Wrong user in sequence",
                "expected_user_id": expected_user.user_id,
                "received_user_id": user_id
            }
        )

    entry = SequenceEntry(
        sequence_id=sequence_id,
        user_id=user_id,
        timestamp=datetime.now(
            pytz.timezone("America/New_York")
        )
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry