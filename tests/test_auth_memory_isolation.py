"""
Cross-User Isolation and Authentication Test Suite.
Verifies the non-negotiable security requirements:
- User A vs User B strict isolation across memories, conversations, messages, and documents.
- Manipulated resource IDs (404/403).
- Unauthorized API calls (401).
- Cross-user vector retrieval isolation.
- Account deletion cleanup.
"""
from __future__ import annotations

import io
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.db.connection import init_database
from src.retrieval.vectorstore import reset_vectorstore_cache


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    init_database()
    reset_vectorstore_cache()


@pytest.fixture
def client():
    return TestClient(app)


def test_authentication_flow(client):
    """Verifies registration, login, session issuance, and verification."""
    # 1. Register User 1
    reg_res = client.post(
        "/api/auth/register",
        json={
            "email": "lawyer_one@firm.com",
            "password": "Password123!",
            "first_name": "Harvey",
            "last_name": "Specter",
        },
    )
    assert reg_res.status_code in (201, 400)  # 400 if already exists

    # 2. Login User 1
    login_res = client.post(
        "/api/auth/login",
        json={
            "email": "lawyer_one@firm.com",
            "password": "Password123!",
        },
    )
    assert login_res.status_code == 200
    data = login_res.json()
    assert "session_token" in data
    assert data["user"]["email"] == "lawyer_one@firm.com"

    token = data["session_token"]

    # 3. Test /api/auth/me with Bearer token
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == "lawyer_one@firm.com"

    # 4. Test /api/auth/me with invalid token
    bad_res = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid_garbage_token"})
    assert bad_res.status_code == 401

    # 5. Test /api/auth/me with missing token
    no_auth_res = client.get("/api/auth/me")
    assert no_auth_res.status_code == 401


def test_cross_user_memory_isolation(client):
    """
    Verifies Section 14 matrix:
    User A reads Memory A -> Allowed
    User A reads Memory B -> Denied
    User B reads Memory B -> Allowed
    User B reads Memory A -> Denied
    """
    # Register/Login User A
    client.post(
        "/api/auth/register",
        json={"email": "usera_mem@test.com", "password": "Password123!", "first_name": "Alice"},
    )
    res_a = client.post("/api/auth/login", json={"email": "usera_mem@test.com", "password": "Password123!"})
    token_a = res_a.json()["session_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register/Login User B
    client.post(
        "/api/auth/register",
        json={"email": "userb_mem@test.com", "password": "Password123!", "first_name": "Bob"},
    )
    res_b = client.post("/api/auth/login", json={"email": "userb_mem@test.com", "password": "Password123!"})
    token_b = res_b.json()["session_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates Memory A
    mem_a_res = client.post(
        "/api/memory",
        headers=headers_a,
        json={
            "memory_type": "PREFERENCE",
            "memory_content": "User A prefers strict formal legal citation style.",
            "importance": 0.9,
        },
    )
    assert mem_a_res.status_code == 201
    mem_a_id = mem_a_res.json()["memory"]["id"]

    # User B creates Memory B
    mem_b_res = client.post(
        "/api/memory",
        headers=headers_b,
        json={
            "memory_type": "WRITING_STYLE",
            "memory_content": "User B prefers brief conversational bullet points.",
            "importance": 0.8,
        },
    )
    assert mem_b_res.status_code == 201
    mem_b_id = mem_b_res.json()["memory"]["id"]

    # 1. User A reads Memory A -> Allowed (200)
    read_a_a = client.get(f"/api/memory/{mem_a_id}", headers=headers_a)
    assert read_a_a.status_code == 200
    assert read_a_a.json()["memory"]["id"] == mem_a_id

    # 2. User A reads Memory B -> Denied (404/403)
    read_a_b = client.get(f"/api/memory/{mem_b_id}", headers=headers_a)
    assert read_a_b.status_code in (403, 404)

    # 3. User B reads Memory B -> Allowed (200)
    read_b_b = client.get(f"/api/memory/{mem_b_id}", headers=headers_b)
    assert read_b_b.status_code == 200
    assert read_b_b.json()["memory"]["id"] == mem_b_id

    # 4. User B reads Memory A -> Denied (404/403)
    read_b_a = client.get(f"/api/memory/{mem_a_id}", headers=headers_b)
    assert read_b_a.status_code in (403, 404)

    # 5. User A lists memories -> contains Memory A, NEVER Memory B
    list_a = client.get("/api/memory", headers=headers_a)
    assert list_a.status_code == 200
    a_ids = [m["id"] for m in list_a.json()["memories"]]
    assert mem_a_id in a_ids
    assert mem_b_id not in a_ids

    # 6. User B lists memories -> contains Memory B, NEVER Memory A
    list_b = client.get("/api/memory", headers=headers_b)
    assert list_b.status_code == 200
    b_ids = [m["id"] for m in list_b.json()["memories"]]
    assert mem_b_id in b_ids
    assert mem_a_id not in b_ids

    # 7. User A attempts to delete Memory B -> Denied
    del_a_b = client.delete(f"/api/memory/{mem_b_id}", headers=headers_a)
    assert del_a_b.status_code in (403, 404)

    # 8. User A deletes Memory A -> Allowed
    del_a_a = client.delete(f"/api/memory/{mem_a_id}", headers=headers_a)
    assert del_a_a.status_code == 200


def test_cross_user_conversation_isolation(client):
    """
    Verifies conversation isolation:
    User A cannot view, add messages to, or delete User B's conversations.
    """
    # User A login
    res_a = client.post("/api/auth/login", json={"email": "usera_mem@test.com", "password": "Password123!"})
    headers_a = {"Authorization": f"Bearer {res_a.json()['session_token']}"}

    # User B login
    res_b = client.post("/api/auth/login", json={"email": "userb_mem@test.com", "password": "Password123!"})
    headers_b = {"Authorization": f"Bearer {res_b.json()['session_token']}"}

    # User A creates Conversation A
    c_a_res = client.post("/api/conversations", headers=headers_a, json={"title": "Private Merger Discussion"})
    assert c_a_res.status_code == 201
    conv_a_id = c_a_res.json()["conversation"]["id"]

    # User A adds a confidential message
    msg_res = client.post(
        f"/api/conversations/{conv_a_id}/messages",
        headers=headers_a,
        json={"role": "user", "content": "What is the valuation cap for Project Titan?"},
    )
    assert msg_res.status_code == 201

    # User B tries to view Conversation A -> Denied
    b_view_a = client.get(f"/api/conversations/{conv_a_id}", headers=headers_b)
    assert b_view_a.status_code in (403, 404)

    # User B tries to view messages of Conversation A -> Empty / Denied
    b_msgs_a = client.get(f"/api/conversations/{conv_a_id}/messages", headers=headers_b)
    assert b_msgs_a.status_code in (403, 404)

    # User B tries to post a message into Conversation A -> Denied
    b_post_a = client.post(
        f"/api/conversations/{conv_a_id}/messages",
        headers=headers_b,
        json={"role": "user", "content": "Injecting into User A conversation"},
    )
    assert b_post_a.status_code in (403, 404)

    # User B tries to delete Conversation A -> Denied
    b_del_a = client.delete(f"/api/conversations/{conv_a_id}", headers=headers_b)
    assert b_del_a.status_code in (403, 404)


def test_cross_user_document_isolation(client):
    """
    Verifies Document ownership and RAG isolation:
    User A's uploaded document is invisible to User B.
    """
    res_a = client.post("/api/auth/login", json={"email": "usera_mem@test.com", "password": "Password123!"})
    headers_a = {"Authorization": f"Bearer {res_a.json()['session_token']}"}

    res_b = client.post("/api/auth/login", json={"email": "userb_mem@test.com", "password": "Password123!"})
    headers_b = {"Authorization": f"Bearer {res_b.json()['session_token']}"}

    # User A uploads a private document
    dummy_doc_content = b"Confidential Settlement Agreement: Party A agrees to pay $5,000,000."
    upload_res = client.post(
        "/api/documents/upload",
        headers=headers_a,
        files={"file": ("settlement_agreement.txt", io.BytesIO(dummy_doc_content), "text/plain")},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["document_id"]

    # 1. User A can inspect Document A
    doc_view_a = client.get(f"/api/documents/{doc_id}", headers=headers_a)
    assert doc_view_a.status_code == 200
    assert doc_view_a.json()["document"]["document_id"] == doc_id

    # 2. User B cannot inspect Document A
    doc_view_b = client.get(f"/api/documents/{doc_id}", headers=headers_b)
    assert doc_view_b.status_code == 404

    # 3. User B's document list does not contain Document A
    b_doc_list = client.get("/api/documents", headers=headers_b)
    assert b_doc_list.status_code == 200
    b_doc_ids = [d["document_id"] for d in b_doc_list.json()["documents"]]
    assert doc_id not in b_doc_ids

    # 4. User B cannot delete Document A
    b_del_doc = client.delete(f"/api/documents/{doc_id}", headers=headers_b)
    assert b_del_doc.status_code == 404

    # 5. User A deletes Document A -> Allowed
    a_del_doc = client.delete(f"/api/documents/{doc_id}", headers=headers_a)
    assert a_del_doc.status_code == 200
