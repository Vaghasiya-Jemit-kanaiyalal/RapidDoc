import sys
import os
import io
import json
from fastapi.testclient import TestClient
from bson import ObjectId

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, r"c:\Users\umran\Desktop\RapidDoc_SGP")

from RapidDoc.backend.app.main import app
from RapidDoc.backend.app.database import db_conn
from RapidDoc.backend.app.config import settings

client = TestClient(app)

def print_result(title, status_ok, details=""):
    badge = "✅ PASS" if status_ok else "❌ FAIL"
    print(f"[{badge}] {title} {details}")

def run_all_backend_tests():
    print("=" * 60)
    print("🚀 RapidDoc Comprehensive Backend & API Test Suite")
    print("=" * 60)

    # 1. Health / Root Check
    try:
        res = client.get("/")
        print_result("Root Endpoint ('/')", res.status_code == 200, f"Status: {res.status_code}")
    except Exception as e:
        print_result("Root Endpoint ('/')", False, str(e))

    # 2. Database connectivity
    db_available = False
    try:
        db = db_conn.get_db()
        db_available = True
        print_result("MongoDB Connection Check", True, f"Connected to DB: {db.name}")
    except ConnectionError as e:
        print_result("MongoDB Connection Check", False, f"MongoDB not running locally: {e}")

    # 3. Auth Flow
    token = None
    test_email = f"test_user_sgp_{os.getpid()}@rapiddoc.ai"
    test_password = "SecurePassword123!"
    
    if db_available:
        # Test Register
        reg_res = client.post("/api/auth/register", json={
            "email": test_email,
            "password": test_password,
            "name": "Test User SGP"
        })
        print_result("Auth: Register User", reg_res.status_code in (200, 201), f"Status: {reg_res.status_code}")
        
        # Test Duplicate Register
        dup_res = client.post("/api/auth/register", json={
            "email": test_email,
            "password": test_password,
            "name": "Test User SGP"
        })
        print_result("Auth: Reject Duplicate Email", dup_res.status_code == 400, f"Status: {dup_res.status_code}")

        # Test Login
        login_res = client.post("/api/auth/login", json={
            "email": test_email,
            "password": test_password
        })
        if login_res.status_code == 200:
            token = login_res.json().get("access_token")
            print_result("Auth: Login & JWT Token Issue", token is not None, f"Token: {token[:20]}...")
        else:
            print_result("Auth: Login & JWT Token Issue", False, f"Status: {login_res.status_code}")

        # Test Current User Info
        if token:
            headers = {"Authorization": f"Bearer {token}"}
            me_res = client.get("/api/auth/me", headers=headers)
            print_result("Auth: Verify Token (/api/auth/me)", me_res.status_code == 200, f"User: {me_res.json().get('email')}")

    # 4. Unauthorized Access Prevention
    unauth_res = client.get("/api/documents")
    print_result("Security: Reject Unauthenticated Request", unauth_res.status_code == 401, f"Status: {unauth_res.status_code}")

    # 5. Document Management & Processing
    if db_available and token:
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test Invalid File Type Upload
        bad_file = ("bad_script.exe", b"binary content", "application/octet-stream")
        bad_up = client.post("/api/documents/upload", headers=headers, files={"file": bad_file})
        print_result("Validation: Reject Invalid File Type (.exe)", bad_up.status_code == 400, f"Status: {bad_up.status_code}")

        # Test DOCX Upload
        real_docx_path = r"c:\Users\umran\Desktop\RapidDoc_SGP\WR_1 (1).docx"
        if os.path.exists(real_docx_path):
            with open(real_docx_path, "rb") as f:
                docx_bytes = f.read()
            
            docx_file = ("WR_1.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            up_res = client.post("/api/documents/upload", headers=headers, files={"file": docx_file})
            
            if up_res.status_code == 200:
                doc_data = up_res.json()
                doc_id = doc_data["id"]
                print_result("Document: Upload DOCX", True, f"Doc ID: {doc_id}, Images: {doc_data.get('images_count')}")

                # Test Get Content
                cnt_res = client.get(f"/api/documents/{doc_id}/content", headers=headers)
                print_result("Document: Get Content", cnt_res.status_code == 200, f"Paragraphs: {len(cnt_res.json().get('content', []))}")

                # Test Headers & Footers
                hf_res = client.get(f"/api/documents/{doc_id}/headers-footers", headers=headers)
                print_result("Document: Get Headers/Footers", hf_res.status_code == 200, f"Data: {hf_res.json()}")

                # Test AI Command Endpoint
                cmd_res = client.post(f"/api/documents/{doc_id}/ai-command", headers=headers, json={
                    "command": "Change the header to RapidDoc SGP Final Report"
                })
                print_result("AI: Execute Command on Document", cmd_res.status_code == 200, f"Result: {cmd_res.json().get('action')}")

                # Test Rewrite Endpoint
                rw_res = client.post(f"/api/documents/{doc_id}/rewrite", headers=headers, json={
                    "instruction": "Make this more formal",
                    "text": "hey whats up let us finalize the presentation ASAP"
                })
                print_result("AI: Document Rewrite Endpoint", rw_res.status_code == 200, f"Rewritten: {rw_res.json().get('rewritten_text')}")

                # Test Pipeline Stage Update
                pipe_res = client.post(f"/api/documents/{doc_id}/pipeline", headers=headers, json={
                    "pipeline_stage": 3,
                    "pipeline_status": "In Review",
                    "completion_percent": 75
                })
                print_result("Document: Update Pipeline Progress", pipe_res.status_code == 200, f"Stage: {pipe_res.json().get('pipeline_stage')}")

                # Clean up uploaded doc from DB
                db.documents.delete_one({"_id": ObjectId(doc_id)})
                db.users.delete_one({"email": test_email})
            else:
                print_result("Document: Upload DOCX", False, f"Status: {up_res.status_code}")

    print("=" * 60)
    print("🎉 Backend Test Suite Completed!")
    print("=" * 60)

if __name__ == "__main__":
    run_all_backend_tests()
