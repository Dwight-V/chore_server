from datetime import datetime, time
from pathlib import Path

import pytz

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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

APP_TIMEZONE = pytz.timezone("America/New_York")

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

class SequenceWindow(Base):
    __tablename__ = "sequence_windows"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    sequence_id: Mapped[int] = mapped_column(
        ForeignKey("sequences.id"),
        nullable=False
    )

    start_day: Mapped[int] = mapped_column(
        nullable=False
    )

    start_time: Mapped[time] = mapped_column(
        nullable=False
    )

    end_day: Mapped[int] = mapped_column(
        nullable=False
    )

    end_time: Mapped[time] = mapped_column(
        nullable=False
    )

    next_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )


Base.metadata.create_all(engine)

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def timestamp_matches_window(
    timestamp: datetime,
    window: SequenceWindow,
) -> bool:
    """
    Check whether timestamp falls inside a recurring weekly window.

    Weekdays:
        Monday = 0
        ...
        Sunday = 6

    The interval is [start, end), so the start is inclusive
    and the end is exclusive.
    """

    current = (
        timestamp.weekday() * 24 * 60
        + timestamp.hour * 60
        + timestamp.minute
        + timestamp.second / 60
    )

    start = (
        window.start_day * 24 * 60
        + window.start_time.hour * 60
        + window.start_time.minute
        + window.start_time.second / 60
    )

    end = (
        window.end_day * 24 * 60
        + window.end_time.hour * 60
        + window.end_time.minute
        + window.end_time.second / 60
    )

    # Same point means a full-week window.
    if start == end:
        return True

    # Normal interval, e.g. Monday 08:00 -> Wednesday 17:00
    if start < end:
        return start <= current < end

    # Wraps around Sunday -> Monday
    # e.g. Sunday 22:00 -> Monday 02:00
    return current >= start or current < end

def calculate_next_user(sequence_id: int, db: Session) -> SequenceOrder:
    """
    Determine the next user for a sequence.

    Priority:
    1. If the most recent entry falls inside a SequenceWindow,
       that window's next_user_id is used.
    2. Otherwise, follow the normal SequenceOrder.
    """

    # Get sequence order
    ordered_users = (
        db.query(SequenceOrder)
        .filter(SequenceOrder.sequence_id == sequence_id)
        .order_by(SequenceOrder.position)
        .all()
    )

    if not ordered_users:
        raise HTTPException(
            status_code=400,
            detail="Sequence has no users"
        )

    # Get most recent entry
    last_entry = (
        db.query(SequenceEntry)
        .filter(SequenceEntry.sequence_id == sequence_id)
        .order_by(SequenceEntry.id.desc())
        .first()
    )

    # No entries yet -> normal first user
    if last_entry is None:
        return ordered_users[0]

    # Check conditional windows

    # SQLite/SQLAlchemy may return a naive datetime.
    # The application timestamps entries in America/New_York.
    timestamp = last_entry.timestamp

    if timestamp.tzinfo is None:
        timestamp = APP_TIMEZONE.localize(timestamp)
    else:
        timestamp = timestamp.astimezone(APP_TIMEZONE)

    matching_windows = (
        db.query(SequenceWindow)
        .filter(SequenceWindow.sequence_id == sequence_id)
        .all()
    )

    for window in matching_windows:
        if timestamp_matches_window(timestamp, window):
            target = next(
                (
                    order
                    for order in ordered_users
                    if order.user_id == window.next_user_id
                ),
                None
            )

            if target is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Window points to user {window.next_user_id}, "
                        "who is not in this sequence"
                    )
                )

            return target

    # No matching window -> normal sequence progression
    current_position = next(
        (
            order.position
            for order in ordered_users
            if order.user_id == last_entry.user_id
        ),
        None
    )

    if current_position is None:
        raise HTTPException(
            status_code=400,
            detail="Last entry user is not in this sequence"
        )

    next_position = current_position + 1

    if next_position >= len(ordered_users):
        next_position = 0

    return ordered_users[next_position]

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
    name: str
    timestamp: datetime

class SequenceWindowCreate(BaseModel):
    start_day: int
    start_time: time
    end_day: int
    end_time: time
    next_user_id: int

# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="User Sequence API",
    description="API for users and user-created sequences."
)

# ============================================================
# WEBPAGE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static",
)

@app.get("/")
async def home():
    return FileResponse(BASE_DIR / "static" / "index.html")

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

    entries = (
        db.query(SequenceEntry, User)
        .join(User, SequenceEntry.user_id == User.id)
        .filter(
            SequenceEntry.sequence_id == sequence_id
        )
        .order_by(SequenceEntry.id)
        .all()
    )

    return [
        {
            "id": entry.id,
            "sequence_id": entry.sequence_id,
            "user_id": entry.user_id,
            "name": user.name,
            "timestamp": entry.timestamp,
        }
        for entry, user in entries
    ]

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

    user = db.get(User, entry.user_id)

    return {
        "id": entry.id,
        "sequence_id": entry.sequence_id,
        "user_id": entry.user_id,
        "name": user.name,
        "timestamp": entry.timestamp,
    }

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

    The calculation is handled by the shared calculate_next_user()
    function, which checks conditional windows first and then falls
    back to the normal sequence order.
    """

    sequence = db.get(Sequence, sequence_id)

    if sequence is None:
        raise HTTPException(
            status_code=404,
            detail="Sequence not found"
        )

    next_order = calculate_next_user(sequence_id, db)

    user = db.get(User, next_order.user_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Next user not found"
        )

    return {
        "user_id": user.id,
        "name": user.name,
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

    The supplied user MUST be the user returned by
    calculate_next_user().
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

    # Determine the expected user using the shared calculation.
    # This guarantees POST and GET /next use identical logic.
    expected_order = calculate_next_user(sequence_id, db)

    if user_id != expected_order.user_id:
        raise HTTPException(
            status_code=409,
            detail=f"Expected user {expected_order.user_id}"
        )

    # Create the entry.
    entry = SequenceEntry(
        sequence_id=sequence_id,
        user_id=user_id,
        timestamp=datetime.now(APP_TIMEZONE)
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return {
        "id": entry.id,
        "sequence_id": entry.sequence_id,
        "user_id": entry.user_id,
        "name": user.name,
        "timestamp": entry.timestamp,
    }

@app.post("/sequences/{sequence_id}/windows")
def create_sequence_window(
    sequence_id: int,
    window_data: SequenceWindowCreate,
    db: Session = Depends(get_db)
):
    sequence = db.get(Sequence, sequence_id)

    if sequence is None:
        raise HTTPException(
            status_code=404,
            detail="Sequence not found"
        )

    user = db.get(User, window_data.next_user_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    if not 0 <= window_data.start_day <= 6:
        raise HTTPException(
            status_code=400,
            detail="start_day must be between 0 and 6"
        )

    if not 0 <= window_data.end_day <= 6:
        raise HTTPException(
            status_code=400,
            detail="end_day must be between 0 and 6"
        )

    window = SequenceWindow(
        sequence_id=sequence_id,
        start_day=window_data.start_day,
        start_time=window_data.start_time,
        end_day=window_data.end_day,
        end_time=window_data.end_time,
        next_user_id=window_data.next_user_id,
    )

    db.add(window)
    db.commit()
    db.refresh(window)

    return {
        "id": window.id,
        "sequence_id": window.sequence_id,
        "start_day": window.start_day,
        "start_time": window.start_time,
        "end_day": window.end_day,
        "end_time": window.end_time,
        "next_user_id": user.id,
        "name": user.name,
    }