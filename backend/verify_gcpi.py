from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

print("Testing GCPI Hexgrid...")
response = client.get("/api/gcpi/hexgrid")
print("Hexgrid status:", response.status_code)
if response.status_code == 200:
    data = response.json()
    print("Success:", data["success"])
    print("Number of hexes:", len(data["data"]))
    if len(data["data"]) > 0:
        print("First hex sample:", data["data"][0])

print("\nTesting GCPI Hotspots...")
response = client.get("/api/gcpi/hotspots")
print("Hotspots status:", response.status_code)
if response.status_code == 200:
    data = response.json()
    print("Number of hotspots:", len(data["data"]))

print("\nTesting GCPI Full...")
response = client.get("/api/gcpi/full")
print("Full status:", response.status_code)
if response.status_code == 200:
    data = response.json()
    print("Stats:", data["data"]["stats"])
