import pytest
import httpx


BASE_URL = "http://localhost"


@pytest.fixture(scope="session")
def client():
    with httpx.Client(
        base_url=BASE_URL,
        timeout=10.0
    ) as client:
        yield client


def create_user(client, name):
    response = client.post(
        "/users",
        json={"name": name}
    )

    assert response.status_code == 201

    return response.json()


def create_sequence(client, name):
    response = client.post(
        "/sequences",
        json={"name": name}
    )

    assert response.status_code == 201

    return response.json()


# ============================================================
# BASIC API
# ============================================================

def test_root(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "User Sequence API is running"


# ============================================================
# USERS
# ============================================================

def test_create_user(client):
    user = create_user(
        client,
        "Regression User"
    )

    assert user["name"] == "Regression User"
    assert "id" in user


def test_get_user(client):
    user = create_user(
        client,
        "Get User Test"
    )

    response = client.get(
        f"/users/{user['id']}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == user["id"]
    assert data["name"] == "Get User Test"


def test_get_missing_user(client):
    response = client.get("/users/999999999")

    assert response.status_code == 404


# ============================================================
# SEQUENCES
# ============================================================

def test_create_sequence(client):
    sequence = create_sequence(
        client,
        "Regression Sequence"
    )

    assert sequence["name"] == "Regression Sequence"
    assert "id" in sequence


def test_get_sequences(client):
    create_sequence(
        client,
        "Sequence List Test"
    )

    response = client.get("/sequences")

    assert response.status_code == 200

    sequences = response.json()

    assert isinstance(sequences, list)
    assert any(
        s["name"] == "Sequence List Test"
        for s in sequences
    )


def test_get_sequence(client):
    sequence = create_sequence(
        client,
        "Get Sequence Test"
    )

    response = client.get(
        f"/sequences/{sequence['id']}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == sequence["id"]
    assert data["name"] == "Get Sequence Test"


def test_get_missing_sequence(client):
    response = client.get(
        "/sequences/999999999"
    )

    assert response.status_code == 404


def test_duplicate_sequence_name(client):
    create_sequence(
        client,
        "Duplicate Sequence"
    )

    response = client.post(
        "/sequences",
        json={
            "name": "Duplicate Sequence"
        }
    )

    assert response.status_code == 409


# ============================================================
# SEQUENCE ORDER
# ============================================================

def test_set_sequence_order(client):
    user1 = create_user(client, "Order Alice")
    user2 = create_user(client, "Order Bob")
    user3 = create_user(client, "Order Charlie")

    sequence = create_sequence(
        client,
        "Order Test Sequence"
    )

    response = client.put(
        f"/sequences/{sequence['id']}/order",
        json={
            "order": [
                user1["id"],
                user2["id"],
                user3["id"]
            ]
        }
    )

    assert response.status_code == 200

    order = response.json()

    assert len(order) == 3

    assert order[0]["position"] == 1
    assert order[0]["user_id"] == user1["id"]

    assert order[1]["position"] == 2
    assert order[1]["user_id"] == user2["id"]

    assert order[2]["position"] == 3
    assert order[2]["user_id"] == user3["id"]


def test_get_sequence_order(client):
    user1 = create_user(client, "Get Order Alice")
    user2 = create_user(client, "Get Order Bob")

    sequence = create_sequence(
        client,
        "Get Order Sequence"
    )

    client.put(
        f"/sequences/{sequence['id']}/order",
        json={
            "order": [
                user2["id"],
                user1["id"]
            ]
        }
    )

    response = client.get(
        f"/sequences/{sequence['id']}/order"
    )

    assert response.status_code == 200

    order = response.json()

    assert order[0]["user_id"] == user2["id"]
    assert order[1]["user_id"] == user1["id"]


def test_order_cannot_contain_duplicate_users(client):
    user = create_user(
        client,
        "Duplicate Order User"
    )

    sequence = create_sequence(
        client,
        "Duplicate Order Sequence"
    )

    response = client.put(
        f"/sequences/{sequence['id']}/order",
        json={
            "order": [
                user["id"],
                user["id"]
            ]
        }
    )

    assert response.status_code == 400


def test_order_cannot_contain_missing_user(client):
    sequence = create_sequence(
        client,
        "Missing User Order Sequence"
    )

    response = client.put(
        f"/sequences/{sequence['id']}/order",
        json={
            "order": [999999999]
        }
    )

    assert response.status_code == 404


# ============================================================
# NEXT USER
# ============================================================

def test_first_next_user(client):
    user1 = create_user(
        client,
        "Next Alice"
    )

    user2 = create_user(
        client,
        "Next Bob"
    )

    sequence = create_sequence(
        client,
        "Next User Sequence"
    )

    client.put(
        f"/sequences/{sequence['id']}/order",
        json={
            "order": [
                user1["id"],
                user2["id"]
            ]
        }
    )

    response = client.get(
        f"/sequences/{sequence['id']}/next"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["next_user_id"] == user1["id"]
    assert data["name"] == "Next Alice"
    assert data["position"] == 1


def test_next_user_advances(client):
    user1 = create_user(
        client,
        "Advance Alice"
    )

    user2 = create_user(
        client,
        "Advance Bob"
    )

    sequence = create_sequence(
        client,
        "Advance Sequence"
    )

    client.put(
        f"/sequences/{sequence['id']}/order",
        json={
            "order": [
                user1["id"],
                user2["id"]
            ]
        }
    )

    # First user
    response = client.post(
        f"/sequences/{sequence['id']}/entries",
        json={
            "user_id": user1["id"]
        }
    )

    assert response.status_code == 201

    # Next should be second user
    response = client.get(
        f"/sequences/{sequence['id']}/next"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["next_user_id"] == user2["id"]
    assert data["name"] == "Advance Bob"


def test_sequence_wraps_around(client):
    user1 = create_user(
        client,
        "Wrap Alice"
    )

    user2 = create_user(
        client,
        "Wrap Bob"
    )

    sequence = create_sequence(
        client,
        "Wrap Sequence"
    )

    client.put(
        f"/sequences/{sequence['id']}/order",
        json={
            "order": [
                user1["id"],
                user2["id"]
            ]
        }
    )

    # Alice
    response = client.post(
        f"/sequences/{sequence['id']}/entries",
        json={"user_id": user1["id"]}
    )

    assert response.status_code == 201

    # Bob
    response = client.post(
        f"/sequences/{sequence['id']}/entries",
        json={"user_id": user2["id"]}
    )

    assert response.status_code == 201

    # Should wrap back to Alice
    response = client.get(
        f"/sequences/{sequence['id']}/next"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["next_user_id"] == user1["id"]
    assert data["name"] == "Wrap Alice"


# ============================================================
# ENTRIES
# ============================================================

def test_first_entry(client):
    user1 = create_user(
        client,
        "Entry Alice"
    )

    user2 = create_user(
        client,
        "Entry Bob"
    )

    sequence = create_sequence(
        client,
        "Entry Sequence"
    )

    client.put(
        f"/sequences/{sequence['id']}/order",
        json={
            "order": [
                user1["id"],
                user2["id"]
            ]
        }
    )

    response = client.post(
        f"/sequences/{sequence['id']}/entries",
        json={
            "user_id": user1["id"]
        }
    )

    assert response.status_code == 201

    data = response.json()

    assert data["sequence_id"] == sequence["id"]
    assert data["user_id"] == user1["id"]
    assert data["timestamp"] is not None


def test_wrong_user_rejected(client):
    user1 = create_user(
        client,
        "Wrong Alice"
    )

    user2 = create_user(
        client,
        "Wrong Bob"
    )

    sequence = create_sequence(
        client,
        "Wrong User Sequence"
    )

    client.put(
        f"/sequences/{sequence['id']}/order",
        json={
            "order": [
                user1["id"],
                user2["id"]
            ]
        }
    )

    # Bob tries to go first.
    response = client.post(
        f"/sequences/{sequence['id']}/entries",
        json={
            "user_id": user2["id"]
        }
    )

    assert response.status_code == 409

    data = response.json()

    assert data["detail"]["expected_user_id"] == user1["id"]


def test_recent_entry_includes_name(client):
    user1 = create_user(
        client,
        "Recent Alice"
    )

    user2 = create_user(
        client,
        "Recent Bob"
    )

    sequence = create_sequence(
        client,
        "Recent Sequence"
    )

    client.put(
        f"/sequences/{sequence['id']}/order",
        json={
            "order": [
                user1["id"],
                user2["id"]
            ]
        }
    )

    client.post(
        f"/sequences/{sequence['id']}/entries",
        json={
            "user_id": user1["id"]
        }
    )

    response = client.get(
        f"/sequences/{sequence['id']}/entries/recent"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["sequence_id"] == sequence["id"]
    assert data["user_id"] == user1["id"]

    # Regression test for the change you just requested.
    assert data["name"] == "Recent Alice"

    assert data["timestamp"] is not None


def test_entries_are_returned(client):
    user1 = create_user(
        client,
        "History Alice"
    )

    user2 = create_user(
        client,
        "History Bob"
    )

    sequence = create_sequence(
        client,
        "History Sequence"
    )

    client.put(
        f"/sequences/{sequence['id']}/order",
        json={
            "order": [
                user1["id"],
                user2["id"]
            ]
        }
    )

    client.post(
        f"/sequences/{sequence['id']}/entries",
        json={
            "user_id": user1["id"]
        }
    )

    client.post(
        f"/sequences/{sequence['id']}/entries",
        json={
            "user_id": user2["id"]
        }
    )

    response = client.get(
        f"/sequences/{sequence['id']}/entries"
    )

    assert response.status_code == 200

    entries = response.json()

    assert len(entries) >= 2

    assert entries[-2]["user_id"] == user1["id"]
    assert entries[-1]["user_id"] == user2["id"]


# ============================================================
# MULTIPLE SEQUENCES
# ============================================================

def test_sequences_are_independent(client):
    alice = create_user(
        client,
        "Independent Alice"
    )

    bob = create_user(
        client,
        "Independent Bob"
    )

    charlie = create_user(
        client,
        "Independent Charlie"
    )

    sequence1 = create_sequence(
        client,
        "Independent Sequence One"
    )

    sequence2 = create_sequence(
        client,
        "Independent Sequence Two"
    )

    # Sequence 1:
    # Alice -> Bob -> Charlie
    client.put(
        f"/sequences/{sequence1['id']}/order",
        json={
            "order": [
                alice["id"],
                bob["id"],
                charlie["id"]
            ]
        }
    )

    # Sequence 2:
    # Charlie -> Bob -> Alice
    client.put(
        f"/sequences/{sequence2['id']}/order",
        json={
            "order": [
                charlie["id"],
                bob["id"],
                alice["id"]
            ]
        }
    )

    # First entry in sequence 1.
    response = client.post(
        f"/sequences/{sequence1['id']}/entries",
        json={
            "user_id": alice["id"]
        }
    )

    assert response.status_code == 201

    # Sequence 1 should now expect Bob.
    response = client.get(
        f"/sequences/{sequence1['id']}/next"
    )

    assert response.json()["next_user_id"] == bob["id"]

    # Sequence 2 has never been used,
    # so it should still expect Charlie.
    response = client.get(
        f"/sequences/{sequence2['id']}/next"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["next_user_id"] == charlie["id"]
    assert data["name"] == "Independent Charlie"


def test_changing_one_sequence_does_not_change_another(client):
    alice = create_user(
        client,
        "Isolation Alice"
    )

    bob = create_user(
        client,
        "Isolation Bob"
    )

    sequence1 = create_sequence(
        client,
        "Isolation Sequence One"
    )

    sequence2 = create_sequence(
        client,
        "Isolation Sequence Two"
    )

    client.put(
        f"/sequences/{sequence1['id']}/order",
        json={
            "order": [
                alice["id"],
                bob["id"]
            ]
        }
    )

    client.put(
        f"/sequences/{sequence2['id']}/order",
        json={
            "order": [
                bob["id"],
                alice["id"]
            ]
        }
    )

    # Change sequence 1.
    client.put(
        f"/sequences/{sequence1['id']}/order",
        json={
            "order": [
                bob["id"],
                alice["id"]
            ]
        }
    )

    # Sequence 2 should still have its own order.
    response = client.get(
        f"/sequences/{sequence2['id']}/order"
    )

    assert response.status_code == 200

    order = response.json()

    assert order[0]["user_id"] == bob["id"]
    assert order[1]["user_id"] == alice["id"]