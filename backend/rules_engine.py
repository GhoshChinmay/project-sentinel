import re

class ThreatRulesEngine:
    def __init__(self):
        # 1. Authority Hook (English + Devanagari)
        self.authority_spoofs = r"\b(cbi|rbi|customs|fedex|police|narcotics|trai|supreme court|telecom|cyber crime|सीबीआई|आरबीआई|पुलिस|कस्टम|कस्टम्स|सुप्रीम कोर्ट)\b"
        
        # 2. Crime Implication (English + Devanagari)
        self.crime_implications = r"\b(money laundering|illegal parcel|mdma|drugs|human trafficking|terrorist|smuggling|arrest warrant|इलीगल पैकेज|पार्सल|ड्रग्स|मनी लॉन्ड्रिंग|गैरकानूनी|वारंट)\b"
        
        # 3. Isolation & Coercion Command (English + Devanagari)
        self.coercion_tactics = r"\b(digital arrest|skype|anydesk|teamviewer|do not tell|isolate|secret|warrant|don't cut|separate room|separate block|video call|camera on|वीडियो कॉल|कमरे में जाकर बंद|गिरफ्तार|अरेस्ट|फोन मत काटना|किसी को मत बताना)\b"
        
        # 4. Financial & "Safe Account" Execution (English + Devanagari)
        # Note: Broadened 'transfer' and 'account' to catch highly disjointed speech-to-text translations
        self.financial_traps = r"\b(safe account|verify your funds|crypto|rtgs|neft|transfer|bank account|pay|send money|account|secretariat audit|refund.*minutes|ट्रांसफर|अकाउंट का डिटेल|पैसे|अकाउंट वेरिफिकेशन)\b"
        
        # 5. PII Weaponization (Spear-Vishing)
        self.pii_reading = r"\b(aadhar|aadhar card|pan card|date of birth is|account ending in|आधार कार्ड|पैन कार्ड|डिटेल्स|आधार नंबर)\b"
        
        # 6. Victim Submission/Fear (Psychology Analysis)
        self.victim_fear = r"\b(please sir|i didn't do|how much|i am scared|i swear|mistake|i didn't order|मुझे नहीं पता|मैंने कुछ नहीं किया|प्लीज सर|माफ़ कर दो)\b"
        
        # Known safe conversational contexts
        self.safe_contexts = r"\b(mom|dad|brother|sister|grocery|groceries|dinner|lunch|school fee|tuition|celebrating|movie|mummy|papa|bhai|मम्मी|पापा|भाई|दोस्त)\b"

    def evaluate_transcript(self, text: str) -> dict:
        text_lower = text.lower()
        
        # 1. Check for safe short-circuits
        has_safe_context = bool(re.search(self.safe_contexts, text_lower))
        
        # 2. Evaluate all threat layers
        has_auth = bool(re.search(self.authority_spoofs, text_lower))
        has_crime = bool(re.search(self.crime_implications, text_lower))
        has_coercion = bool(re.search(self.coercion_tactics, text_lower))
        has_fin = bool(re.search(self.financial_traps, text_lower))
        has_pii = bool(re.search(self.pii_reading, text_lower))
        has_fear = bool(re.search(self.victim_fear, text_lower))
        
        threat_score = 0
        markers = []
        
        # LAYER 1: The Threat Sequence (Instant Critical)
        if has_auth and has_crime and has_coercion:
            threat_score += 5
            markers.append("Full Digital Arrest Sequence (Auth+Crime+Isolation)")
        else:
            if has_auth:
                threat_score += 1
                markers.append("Spoofed Authority")
            if has_coercion:
                threat_score += 2  # Coercion is heavily weighted
                markers.append("Coercive Isolation")
            if has_crime:
                threat_score += 1
                markers.append("Crime Implication")
                
        # LAYER 3: PII Weaponization
        if has_pii and (has_auth or has_crime):
            threat_score += 2
            markers.append("PII Weaponization (Spear-Vishing)")
            
        # LAYER 4: Safe Account Trap
        if has_fin:
            threat_score += 3
            markers.append("Government 'Safe Account' / Transfer Trap")
            
        # LAYER 2: Victim Psychology
        if has_fear and (has_auth or has_coercion):
            threat_score += 2
            markers.append("Victim Fear/Submission Detected")

        # If it has safe keywords and NO severe threats, short-circuit it
        is_safe_override = has_safe_context and threat_score < 3

        return {
            "threat_score": threat_score,
            "markers": markers,
            "is_safe_override": is_safe_override
        }

rule_guardrails = ThreatRulesEngine()