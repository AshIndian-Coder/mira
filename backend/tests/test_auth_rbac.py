import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import hash_password, verify_password, create_access_token
from app.core.seed import seed_default_users_and_cpses
from app.core.database import SessionLocal
from app.models.user import User
from app import store
from app.api.v1.mappings import MAPPINGS
from app.api.v1.audit import AUDIT_EVENTS

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db():
    seed_default_users_and_cpses()
    db = SessionLocal()
    db.query(User).filter(User.email.notin_([
        "admin@mira.gov.in",
        "steward@mira.gov.in",
        "reviewer@mira.gov.in",
        "auditor@mira.gov.in",
    ])).delete(synchronize_session=False)
    db.commit()
    db.close()
    yield


def test_password_hashing_and_verification():
    plain = "SecurePassword@123"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_login_success():
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@mira.gov.in", "password": "Admin@123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "admin@mira.gov.in"
    assert data["user"]["role"] == "admin"


def test_login_invalid_password():
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@mira.gov.in", "password": "WrongPassword"},
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


def test_login_nonexistent_user():
    response = client.post(
        "/api/auth/login",
        json={"email": "nonexistent@mira.gov.in", "password": "AnyPassword"},
    )
    assert response.status_code == 401


def test_login_inactive_user():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "inactive@mira.gov.in").first()
        if not user:
            user = User(
                email="inactive@mira.gov.in",
                password_hash=hash_password("Pass@123"),
                full_name="Inactive User",
                role="reviewer",
                is_active=False,
            )
            db.add(user)
            db.commit()
        else:
            user.is_active = False
            db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/auth/login",
        json={"email": "inactive@mira.gov.in", "password": "Pass@123"},
    )
    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"]


def test_protected_route_missing_token():
    response = client.get("/api/materials")
    assert response.status_code == 401


def test_protected_route_invalid_token():
    response = client.get(
        "/api/materials",
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    assert response.status_code == 401


def test_auth_me_endpoint():
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "reviewer@mira.gov.in", "password": "Reviewer@123"},
    )
    token = login_resp.json()["access_token"]

    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    user_info = me_resp.json()
    assert user_info["email"] == "reviewer@mira.gov.in"
    assert user_info["role"] == "reviewer"


def test_token_refresh():
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "auditor@mira.gov.in", "password": "Auditor@123"},
    )
    token = login_resp.json()["access_token"]

    refresh_resp = client.post(
        "/api/auth/refresh",
        json={"access_token": token},
    )
    assert refresh_resp.status_code == 200
    new_data = refresh_resp.json()
    assert "access_token" in new_data
    assert new_data["user"]["email"] == "auditor@mira.gov.in"


def test_rbac_permissions():
    # 1. Login as Reviewer
    rev_login = client.post(
        "/api/auth/login",
        json={"email": "reviewer@mira.gov.in", "password": "Reviewer@123"},
    )
    rev_token = rev_login.json()["access_token"]
    rev_headers = {"Authorization": f"Bearer {rev_token}"}

    # 2. Reviewer cannot upload data (403)
    upload_resp = client.post(
        "/api/materials/upload",
        headers=rev_headers,
        files={"file": ("test.csv", b"cpse,material_code,description\nNTPC,C1,Desc", "text/csv")},
    )
    assert upload_resp.status_code == 403

    # 3. Reviewer cannot view audit trail (403)
    audit_resp = client.get("/api/audit", headers=rev_headers)
    assert audit_resp.status_code == 403

    # 4. Login as Data Steward
    steward_login = client.post(
        "/api/auth/login",
        json={"email": "steward@mira.gov.in", "password": "Steward@123"},
    )
    steward_token = steward_login.json()["access_token"]
    steward_headers = {"Authorization": f"Bearer {steward_token}"}

    # 5. Steward can upload data (200)
    csv_content = """cpse,material_code,description,category,material_grade
NTPC,NTPC-V1,SS 304 GATE VALVE 2 IN 150 LB,Valve,SS304
BHEL,BHEL-V1,SS 304 GATE VALVE 2 IN 300 LB,Valve,SS304
"""
    upload_resp = client.post(
        "/api/materials/upload",
        headers=steward_headers,
        files={"file": ("test.csv", csv_content, "text/csv")},
    )
    assert upload_resp.status_code == 200

    # 6. Steward can run matching
    batch_resp = client.post(
        "/api/matching/run-batch",
        headers=steward_headers,
        json={"overwrite": True},
    )
    assert batch_resp.status_code == 200

    # 7. Reviewer can view review queue and submit review action
    queue_resp = client.get("/api/review/queue", headers=rev_headers)
    assert queue_resp.status_code == 200
    queue_data = queue_resp.json()
    assert queue_data["total_pending"] >= 1
    candidate_id = queue_data["queue"][0]["id"]

    action_resp = client.post(
        f"/api/review/queue/{candidate_id}/action",
        headers=rev_headers,
        json={"action": "APPROVE", "reviewer_comments": "Looks good by technical reviewer"},
    )
    assert action_resp.status_code == 200
    assert action_resp.json()["candidate"]["reviewer_id"] == "reviewer@mira.gov.in"

    # 8. Login as Auditor -> Can view audit trail and verify actor attribution
    auditor_login = client.post(
        "/api/auth/login",
        json={"email": "auditor@mira.gov.in", "password": "Auditor@123"},
    )
    auditor_token = auditor_login.json()["access_token"]
    auditor_headers = {"Authorization": f"Bearer {auditor_token}"}

    audit_resp = client.get("/api/audit", headers=auditor_headers)
    assert audit_resp.status_code == 200
    events = audit_resp.json()["events"]
    assert any(e["actor"] == "reviewer@mira.gov.in" for e in events)

    # 9. Admin can manage users
    admin_login = client.post(
        "/api/auth/login",
        json={"email": "admin@mira.gov.in", "password": "Admin@123"},
    )
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    users_resp = client.get("/api/users", headers=admin_headers)
    assert users_resp.status_code == 200
    assert users_resp.json()["total"] >= 4

    # 10. Non-admin cannot list users
    forbidden_users = client.get("/api/users", headers=rev_headers)
    assert forbidden_users.status_code == 403


def test_admin_user_management_lifecycle():
    # 1. Admin login
    admin_login = client.post(
        "/api/auth/login",
        json={"email": "admin@mira.gov.in", "password": "Admin@123"},
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = admin_login.json()["user"]["id"]

    # 2. List CPSEs
    cpses_resp = client.get("/api/users/cpses", headers=admin_headers)
    assert cpses_resp.status_code == 200
    cpses = cpses_resp.json()
    assert len(cpses) >= 5
    assert any(c["short_code"] == "IOCL" for c in cpses)
    iocl_id = next(c["id"] for c in cpses if c["short_code"] == "IOCL")

    # 3. Create a new user
    new_user_payload = {
        "email": "new_engineer@mira.gov.in",
        "password": "Engineer@123",
        "full_name": "Lead Piping Engineer",
        "role": "reviewer",
        "cpse_id": iocl_id,
    }
    create_resp = client.post("/api/users", headers=admin_headers, json=new_user_payload)
    assert create_resp.status_code == 201
    created_user = create_resp.json()
    assert created_user["email"] == "new_engineer@mira.gov.in"
    assert created_user["role"] == "reviewer"
    assert created_user["cpse_short_code"] == "IOCL"
    assert created_user["is_active"] is True
    new_user_id = created_user["id"]

    # 4. Duplicate creation returns 409
    dup_resp = client.post("/api/users", headers=admin_headers, json=new_user_payload)
    assert dup_resp.status_code == 409

    # 5. New user logs in successfully
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "new_engineer@mira.gov.in", "password": "Engineer@123"},
    )
    assert login_resp.status_code == 200
    new_token = login_resp.json()["access_token"]
    assert login_resp.json()["user"]["role"] == "reviewer"

    # 6. Admin updates the user's role and details
    update_resp = client.put(
        f"/api/users/{new_user_id}",
        headers=admin_headers,
        json={"full_name": "Chief Materials Officer", "role": "data_steward"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["full_name"] == "Chief Materials Officer"
    assert update_resp.json()["role"] == "data_steward"

    # 7. Self-deactivation prevention
    self_deact_resp = client.delete(f"/api/users/{admin_id}", headers=admin_headers)
    assert self_deact_resp.status_code == 400
    assert "Cannot deactivate your own administrator account" in self_deact_resp.json()["detail"]

    # 8. Deactivate the new user
    deact_resp = client.delete(f"/api/users/{new_user_id}", headers=admin_headers)
    assert deact_resp.status_code == 200
    assert deact_resp.json()["is_active"] is False

    # 9. Deactivated user cannot authenticate (returns 403 Forbidden)
    blocked_login = client.post(
        "/api/auth/login",
        json={"email": "new_engineer@mira.gov.in", "password": "Engineer@123"},
    )
    assert blocked_login.status_code == 403
    assert "User account is deactivated" in blocked_login.json()["detail"]


def test_public_routes():
    # Health check is public
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"
