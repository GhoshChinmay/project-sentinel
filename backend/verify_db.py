import os
from database import SessionLocal
from models import Incident

def inspect_latest_incidents():
    db = SessionLocal()
    try:
        # Retrieve the 5 most recent incidents logged in the database
        latest_incidents = db.query(Incident).order_by(Incident.timestamp.desc()).limit(5).all()
        
        print("\n==================================================")
        print("    🔎 SENTINEL SQLITE DATABASE ACTIVE LOGS      ")
        print("==================================================")
        
        if not latest_incidents:
            print("No incidents found in the database. Run seed_data.py first!")
            return
            
        for idx, incident in enumerate(latest_incidents, 1):
            print(f"\n[{idx}] INCIDENT ID: {incident.id}")
            print(f"    Type:       {incident.type}")
            print(f"    Status:     {incident.status.upper()}")
            print(f"    Location:   {incident.district} ({incident.lat}, {incident.lng})")
            print(f"    Time Logged:{incident.timestamp}")
            print(f"    Confidence: {incident.confidence}")
            print(f"    Details:    {incident.raw_payload_json[:120]}...")
            print("-" * 50)
            
    except Exception as e:
        print(f"Database Read Error: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    inspect_latest_incidents()