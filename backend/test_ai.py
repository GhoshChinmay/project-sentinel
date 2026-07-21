# test_ai.py
from nlp_engine import analyzer

print("--- PROJECT SENTINEL AI TEST ---\n")

# Test 1: A normal conversation
normal_call = "Hey mom, I am running late from the office. I will transfer the rent money tomorrow."
result1 = analyzer.analyze_transcript(normal_call)
print(f"Normal Call Result: {result1['status']} ({result1['confidence']})")

# Test 2: A Digital Arrest Scam
scam_call = "Hello, this is officer Sharma from CBI. A parcel with your Aadhar has been seized with drugs. Do not disconnect the call, you are under digital arrest."
result2 = analyzer.analyze_transcript(scam_call)
print(f"Scam Call Result: {result2['status']} ({result2['confidence']})")