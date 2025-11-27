# scripts/simulate_field_day.py
import requests
import random
import time
import sys

BASE_URL = "http://localhost:8000"

def generate_profile():
    return {
        "age": random.randint(18, 70),
        "gender": random.choice(["M", "F", "F", "F"]),
        "income": random.choice([45000, 80000, 120000, 250000, 320000, 600000]),
        "education_years": random.choice([0, 5, 8, 10, 12]),
        "rural": random.choice([0, 1]),
        "caste_marginalized": random.choice([0, 1])
    }

def run_simulation(n=50):
    print(f"🚀 Starting Field Simulation v1.3 ({n} citizens)...")
    
    for i in range(n):
        scheme = random.choice(["UJJ", "PMAY"])
        # Use simple numeric-suffix hash to ensure consistent testing
        hash_base = f"citizen_{i}_{random.randint(1000,9999)}"
        
        payload = {
            "citizen_hash": hash_base,
            "scheme_code": scheme,
            "source": "KIOSK_CHAT",
            "locale": "en",
            "session_id": f"sim_sess_{i}",
            "meta_duration_seconds": random.randint(20, 120),
            "profile": generate_profile(),
            "message_text": "check eligibility"
        }
        
        try:
            res = requests.post(f"{BASE_URL}/cases/", json=payload)
            if res.status_code == 201:
                data = res.json()
                # Server Logic: Even -> Treatment, Odd -> Control
                server_arm = "TREATMENT" if len(hash_base) % 2 == 0 else "CONTROL"
                
                res_str = "✅ Eligible"
                if data.get("audit_flag"): res_str = "⚠️ Review"
                if data.get("review_confidence") is None: res_str = "🙈 Blinded"
                
                print(f"[{i+1}/{n}] {scheme} | {server_arm} | {res_str}")
            else:
                print(f"[{i+1}/{n}] Error: {res.status_code}")
        except Exception as e:
            print(f"Connection Error: {e}")
            break
            
        time.sleep(0.05)

    print("\n✨ Simulation Complete.")

if __name__ == "__main__":
    try:
        requests.get(f"{BASE_URL}/")
    except:
        print("❌ Server not running!")
        sys.exit(1)
        
    run_simulation()