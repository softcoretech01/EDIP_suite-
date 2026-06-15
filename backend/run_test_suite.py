import requests
import json
import time

# General Questions List (20 Questions)
general_questions = [
    "What is an ERP system?",
    "What does ERP stand for?",
    "What is the difference between ERP and CRM?",
    "What is a Purchase Requisition (PR)?",
    "What is a Purchase Order (PO)?",
    "What is a Goods Receipt Note (GRN)?",
    "What is the purpose of Landed Cost in inventory management?",
    "Explain the order-to-cash process.",
    "Explain the procure-to-pay process.",
    "What is a General Ledger in ERP systems?",
    "What are Accounts Payable (AP) and Accounts Receivable (AR)?",
    "What is inventory valuation, and what are FIFO and LIFO methods?",
    "What is a bill of materials (BOM)?",
    "What is lead time in purchasing?",
    "What is safety stock?",
    "What is an invoice, and how does it differ from a purchase order?",
    "What is supply chain management (SCM) in the context of ERP?",
    "What is a credit limit for customers, and why is it important?",
    "What is a batch or lot number in inventory tracking?",
    "Explain the concept of material requirements planning (MRP)."
]

# ERP Company-Specific Questions List (20 Questions)
erp_questions = [
    "how many sales orders are in the system?",
    "show all customers",
    "show all suppliers",
    "how many items are active in the system?",
    "what is the highest value invoice?",
    "show top 5 items by ordered quantity in sales orders",
    "which items are currently in stock",
    "how many purchase orders are created?",
    "what is the total value of all purchase orders?",
    "how many goods receipt notes are generated?",
    "list the purchase requisitions with high priority",
    "what items are requested in PR-001?",
    "show all import purchase orders with status Ordered",
    "which items are in short stock?",
    "show the total refund amount for purchase returns",
    "what is the total value of all invoices generated?",
    "how many sales orders have not had invoices generated yet?",
    "list the delivery schedules for POs expected in the future",
    "show the total landed cost for local purchases",
    "what is the average margin percentage for inventory batches?"
]

API_URL = "http://localhost:8001/chat/ask"
AUTH_URL = "http://localhost:8001/auth/login"
CONNECTION_ID = 2
ACCESS_TOKEN = None

def run_test_question(question, category):
    payload = {
        "connection_id": CONNECTION_ID,
        "question": question,
        "view_mode": "dashboard",
        "session_id": "test-session"
    }
    headers = {
        "Content-Type": "application/json"
    }
    if ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    
    start_time = time.time()
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        elapsed = time.time() - start_time
        return {
            "question": question,
            "status_code": response.status_code,
            "elapsed_seconds": round(elapsed, 2),
            "response": response.json() if response.status_code == 200 else response.text
        }
    except Exception as e:
        return {
            "question": question,
            "status_code": None,
            "elapsed_seconds": round(time.time() - start_time, 2),
            "error": str(e)
        }

def main():
    global ACCESS_TOKEN
    print("==================================================")
    print("EDIP SUITE INTEGRATION TEST RUNNER")
    print("==================================================")
    
    print("\nAuthenticating login...")
    try:
        r = requests.post(AUTH_URL, json={
            "email": "admin@edip.com",
            "password": "admin123"
        })
        if r.status_code == 200:
            ACCESS_TOKEN = r.json().get("access_token")
            print("Authenticated successfully!")
        else:
            print(f"Auth failed: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Auth request error: {e}")

    # We will test 5 general and 5 erp questions
    sample_general = general_questions[:5]
    sample_erp = erp_questions[:5]
    
    results = []
    
    print("\n--- Running General ERP Knowledge Questions ---")
    for q in sample_general:
        print(f"Asking: '{q}'...")
        res = run_test_question(q, "General")
        results.append(("General", res))
        print(f"  Result: Code {res['status_code']} ({res['elapsed_seconds']}s)")
        
    print("\n--- Running Company-Specific ERP Data Questions ---")
    for q in sample_erp:
        print(f"Asking: '{q}'...")
        res = run_test_question(q, "Company Data")
        results.append(("Company Data", res))
        print(f"  Result: Code {res['status_code']} ({res['elapsed_seconds']}s)")

    print("\n=================== SUMMARY OF TESTING ===================")
    success_count = sum(1 for _, r in results if r['status_code'] == 200)
    print(f"Total Tested: {len(results)}")
    print(f"Successful (200 OK): {success_count}/{len(results)}")
    
    # Save full test report
    report = {
        "total_tested": len(results),
        "successful": success_count,
        "results": results
    }
    with open("test_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Test report saved to test_report.json")

if __name__ == "__main__":
    main()
