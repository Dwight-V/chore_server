from datetime import datetime, timezone
import pytz

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import (
    create_engine,
    String,
    ForeignKey,
    DateTime,
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

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )


class UserOrder(Base):
    """
    Defines the arbitrary sequence of users.

    Example:

        position  user_id
        --------  -------
        1         3
        2         1
        3         2

    Means the sequence is:

        3 -> 1 -> 2 -> 3 -> ...
    """

    __tablename__ = "user_order"

    position: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        unique=True
    )


class SequenceEntry(Base):
    """
    Records each time a user is submitted.

    The ID represents the chronological entry number.
    """

    __tablename__ = "sequence_entries"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )


# Create tables if they don't exist
Base.metadata.create_all(engine)


# ============================================================
# PYDANTIC REQUEST/RESPONSE MODELS
# ============================================================

class UserCreate(BaseModel):
    name: str


class UserResponse(BaseModel):
    id: int
    name: str


class OrderRequest(BaseModel):
    order: list[int]


class OrderResponse(BaseModel):
    position: int
    user_id: int


class SequenceCreate(BaseModel):
    user_id: int


class SequenceResponse(BaseModel):
    id: int
    user_id: int
    timestamp: datetime


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="User Sequence API",
    description="API for users, arbitrary user ordering, and sequential submissions.",
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
    """
    Get all users.
    """

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
    """
    Get a single user by ID.
    """

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
    """
    Create a new user.
    """

    user = User(
        name=user_data.name
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


# ============================================================
# USER ORDER
# ============================================================

@app.get(
    "/order",
    response_model=list[OrderResponse]
)
def get_order(
    db: Session = Depends(get_db)
):
    """
    Get the current user sequence.

    Example:

        [
            {"position": 1, "user_id": 3},
            {"position": 2, "user_id": 1},
            {"position": 3, "user_id": 2}
        ]

    Means:

        3 -> 1 -> 2 -> 3 -> ...
    """

    return (
        db.query(UserOrder)
        .order_by(UserOrder.position)
        .all()
    )


@app.put(
    "/order",
    response_model=list[OrderResponse]
)
def set_order(
    order_data: OrderRequest,
    db: Session = Depends(get_db)
):
    """
    Completely replace the current user sequence.

    Example request:

        {
            "order": [3, 1, 2]
        }
    """

    user_ids = order_data.order

    if len(user_ids) == 0:
        raise HTTPException(
            status_code=400,
            detail="Order cannot be empty"
        )

    # Make sure there are no duplicate IDs
    if len(user_ids) != len(set(user_ids)):
        raise HTTPException(
            status_code=400,
            detail="User IDs cannot be duplicated"
        )

    # Make sure all users exist
    users = (
        db.query(User)
        .filter(User.id.in_(user_ids))
        .all()
    )

    existing_ids = {user.id for user in users}

    missing_ids = set(user_ids) - existing_ids

    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Users not found: {sorted(missing_ids)}"
        )

    # Remove old order
    db.query(UserOrder).delete()

    # Create new order
    for position, user_id in enumerate(user_ids, start=1):
        db.add(
            UserOrder(
                position=position,
                user_id=user_id
            )
        )

    db.commit()

    return (
        db.query(UserOrder)
        .order_by(UserOrder.position)
        .all()
    )


# ============================================================
# SEQUENCE
# ============================================================

@app.get(
    "/sequence",
    response_model=list[SequenceResponse]
)
def get_sequence(
    db: Session = Depends(get_db)
):
    """
    Get the complete sequence history.
    """

    return (
        db.query(SequenceEntry)
        .order_by(SequenceEntry.id)
        .all()
    )


@app.get(
    "/sequence/recent",
    response_model=SequenceResponse
)
def get_recent_sequence(
    db: Session = Depends(get_db)
):
    """
    Get the most recent sequence entry.
    """

    entry = (
        db.query(SequenceEntry)
        .order_by(SequenceEntry.id.desc())
        .first()
    )

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="No sequence entries exist"
        )

    return entry


@app.get(
    "/sequence/next"
)
def get_next_user(
    db: Session = Depends(get_db)
):
    """
    Determine which user is allowed to be submitted next.
    """

    # Get the configured order
    ordered_users = (
        db.query(UserOrder)
        .order_by(UserOrder.position)
        .all()
    )

    if not ordered_users:
        raise HTTPException(
            status_code=400,
            detail="User order has not been configured"
        )

    # Get the most recent submission
    last_entry = (
        db.query(SequenceEntry)
        .order_by(SequenceEntry.id.desc())
        .first()
    )

    # Nothing has been submitted yet.
    # The first user in the order is next.
    if last_entry is None:
        next_user = ordered_users[0]

    else:
        # Find the position of the last submitted user
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
                detail="Last user is no longer in the configured order"
            )

        # Find the next position
        next_position = current_position.position + 1

        # Wrap around
        if next_position > len(ordered_users):
            next_position = 1

        next_user = ordered_users[next_position - 1]

    return {
        "next_user_id": next_user.user_id,
        "position": next_user.position
    }


@app.post(
    "/sequence",
    response_model=SequenceResponse,
    status_code=201
)
def add_sequence_entry(
    sequence_data: SequenceCreate,
    db: Session = Depends(get_db)
):
    """
    Add a sequence entry.

    The supplied user_id MUST be the next user
    according to the configured user order.
    """

    user_id = sequence_data.user_id

    # --------------------------------------------------------
    # Make sure the user exists
    # --------------------------------------------------------

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # --------------------------------------------------------
    # Get configured order
    # --------------------------------------------------------

    ordered_users = (
        db.query(UserOrder)
        .order_by(UserOrder.position)
        .all()
    )

    if not ordered_users:
        raise HTTPException(
            status_code=400,
            detail="User order has not been configured"
        )

    # --------------------------------------------------------
    # Determine the expected user
    # --------------------------------------------------------

    last_entry = (
        db.query(SequenceEntry)
        .order_by(SequenceEntry.id.desc())
        .first()
    )

    if last_entry is None:

        # First submission
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
                detail="Last user is no longer in the configured order"
            )

        next_position = current_position.position + 1

        # Wrap around to beginning
        if next_position > len(ordered_users):
            next_position = 1

        expected_user = ordered_users[next_position - 1]

    # --------------------------------------------------------
    # Validate sequence
    # --------------------------------------------------------

    if user_id != expected_user.user_id:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Wrong user in sequence",
                "expected_user_id": expected_user.user_id,
                "received_user_id": user_id
            }
        )

    # --------------------------------------------------------
    # Create entry
    # --------------------------------------------------------

    entry = SequenceEntry(
        user_id=user_id,
        timestamp=datetime.now(pytz.timezone("America/New_York"))
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry