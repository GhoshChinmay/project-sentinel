import json
import os
from dotenv import load_dotenv
from groq import Groq

# Import our custom deterministic rules engine
from rules_engine import rule_guardrails

# Load environment variables from .env file
load_dotenv()

class LocalSentimentEngine:
    """
    Lightweight Edge AI Transformer running locally on the CPU.
    Analyzes raw emotions and maps them to the V.A.D (Valence, Arousal, Dominance) scale
    before sending the data to the Cloud LLM.
    """
    def __init__(self):
        self.enabled = False
        try:
            from transformers import pipeline
            import warnings
            warnings.filterwarnings("ignore")

            print("🚀 Loading Local Edge Transformer (DistilBERT) for V.A.D. calculation...")
            # We use a highly compressed, fast emotion model perfect for CPU inference
            self.classifier = pipeline("text-classification", model="bhadresh-savani/distilbert-base-uncased-emotion", top_k=1)
            self.enabled = True
            print("Edge Transformer loaded successfully on CPU.")
        except ImportError:
            print("'transformers' library not found. Running V.A.D. in Edge-Heuristic mode. (Run 'pip install transformers torch' for deep AI sentiment)")
        except Exception as e:
            print(f"Failed to load HuggingFace model: {e}. Running in Edge-Heuristic mode.")

    def analyze_vad(self, text: str) -> dict:
        # Default Baseline (Neutral)
        vad = {"valence": 5, "arousal": 5, "dominance": 5, "emotion": "neutral"}

        if not self.enabled:
            # Fallback heuristic if transformers aren't installed yet
            text_lower = text.lower()
            if any(word in text_lower for word in ["police", "arrest", "cbi", "customs", "money", "transfer", "now"]):
                vad = {"valence": 2, "arousal": 8, "dominance": 9, "emotion": "anger/aggressive"}
            elif any(word in text_lower for word in ["please", "scared", "didn't do", "sir"]):
                vad = {"valence": 2, "arousal": 9, "dominance": 1, "emotion": "fear/submissive"}
            elif any(word in text_lower for word in ["mummy", "papa", "yaar", "dost", "bhai"]):
                vad = {"valence": 8, "arousal": 4, "dominance": 5, "emotion": "joy/familiar"}
            return vad

        try:
            # Predict emotion using the local CPU model (limit context for speed)
            result = self.classifier(text[:512])
            emotion = result[0][0]['label'].lower()  # type: ignore[index]
            vad["emotion"] = emotion

            # Mathematical translation to V.A.D (1-10 scale)
            if emotion == "anger": # The Scammer (Aggressor)
                vad.update({"valence": 2, "arousal": 8, "dominance": 9})
            elif emotion == "fear": # The Victim (Panicking)
                vad.update({"valence": 2, "arousal": 9, "dominance": 1})
            elif emotion in ["joy", "love"]: # Safe/Casual Family
                vad.update({"valence": 8, "arousal": 5, "dominance": 5})
            elif emotion == "sadness":
                vad.update({"valence": 3, "arousal": 4, "dominance": 2})
            elif emotion == "surprise":
                vad.update({"valence": 6, "arousal": 7, "dominance": 5})
        except Exception:
            pass

        return vad

class ScamClassifier:
    def __init__(self):
        # --- INITIALIZE GROQ SDK (graceful degradation if key is missing) ---
        # Merge note: the backend must boot even before a GROQ_API_KEY is supplied,
        # so that the other three pillars (currency, graph, GCPI) stay available.
        # When no key is present we run DETERMINISTIC-ONLY (rules + local V.A.D.);
        # when a key IS present the cloud pipeline below is completely unchanged.
        api_key = os.getenv("GROQ_API_KEY")
        self.client = None
        self.fast_model_name = None

        if not api_key:
            print("⚠️  WARNING: GROQ_API_KEY is not set in backend/.env. "
                  "Digital-Arrest NLP will run in DETERMINISTIC-ONLY mode "
                  "(rules + local V.A.D., no cloud LLM).")
        else:
            try:
                self.client = Groq(api_key=api_key)
                # True Dynamic NLP Model Hunter
                self.fast_model_name = self._get_active_text_model()
            except Exception as e:
                print(f"⚠️  Groq initialization failed ({e}). "
                      "Falling back to DETERMINISTIC-ONLY NLP mode.")
                self.client = None
                self.fast_model_name = None

        # Initialize our Local CPU V.A.D. Engine (runs fully offline)
        self.vad_engine = LocalSentimentEngine()

    def _get_active_text_model(self):
        """
        Dynamically finds the best free-tier text model currently active on Groq.
        Contains absolutely NO hardcoded fallbacks to prevent deprecation crashes.
        """
        try:
            print("Scanning Groq API for active NLP text models...")
            models_list = self.client.models.list()
            available_models = [m.id.lower() for m in models_list.data]

            # Filter out vision, audio, and heavily restricted enterprise models
            text_models = [
                m for m in available_models
                if "vision" not in m
                and "whisper" not in m
                and "vl" not in m
                and "120b" not in m
                and "90b" not in m
            ]

            if not text_models:
                raise RuntimeError("No suitable text models found in the active Groq catalog.")

            # Priority Search Strategy: Try to find a balanced open-weight model
            preferred_keywords = ["llama-3.3", "llama-3", "llama", "mixtral", "gemma"]

            for keyword in preferred_keywords:
                for model in text_models:
                    if keyword in model:
                        print(f"Auto-Locked onto active text model: {model}")
                        return model

            selected_model = text_models[0]
            print(f"Auto-Locked onto available text model: {selected_model}")
            return selected_model

        except Exception as e:
            raise RuntimeError(f"Failed to fetch models from Groq API: {str(e)}. Check your API key and connection.")

    def _parse_json_safe(self, text):
        """Safely extract JSON from LLM output, bypassing Groq 400 strict validation errors."""
        try:
            if not text or not text.strip():
                raise ValueError("LLM returned an empty response. (Possible timeout)")

            text = text.strip()

            # Aggressively strip markdown wrappers if the model hallucinated them
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]

            if text.endswith("```"):
                text = text[:-3]

            text = text.strip()

            start = text.find('{')
            end = text.rfind('}')

            if start != -1 and end != -1:
                clean_json = text[start:end+1]
                return json.loads(clean_json)

            return json.loads(text)
        except Exception as e:
            print(f"RAW LLM OUTPUT CAPTURED BEFORE CRASH:\n{text}\n")
            raise ValueError(f"Failed to parse LLM JSON: {e}")

    # 🛑 WHISPER HAS BEEN PERMANENTLY REMOVED FROM THIS PIPELINE.
    # The React app now handles STT natively using the Browser's built-in engine,
    # routing completely around the 429 Rate Limits!

    def analyze_transcript(self, text_transcript: str) -> dict:
        """
        Takes a live stream of text in multiple regional languages, runs local CPU V.A.D. math,
        applies deterministic hard-overrides, and feeds everything to the Cloud LLM.
        """
        if not text_transcript or len(text_transcript.strip()) < 10:
            return {"status": "safe", "confidence": "0%", "details": "Audio too short to analyze."}

        # --- PHASE 1: DETERMINISTIC PRE-FILTER & IMMUNE SYSTEM ---
        rule_eval = rule_guardrails.evaluate_transcript(text_transcript)
        if rule_eval["is_safe_override"]:
            print("🛡️ Guardrail Active: Short-circuited to SAFE. Bypassing LLM.")
            return {
                "status": "safe",
                "confidence": "99%",
                "details": "Verified safe conversational context. No threats detected."
            }

        # --- PHASE 2: LOCAL CPU EDGE SENSOR (V.A.D. Matrix) ---
        vad_metrics = self.vad_engine.analyze_vad(text_transcript)

        # --- OFFLINE MODE: no cloud LLM available (no GROQ_API_KEY) ---
        # Decide purely from the deterministic rules engine + local V.A.D. so the
        # pipeline still returns a meaningful verdict (the rule hard-override still fires).
        if not self.client:
            score = rule_eval["threat_score"]
            if score >= 3:
                status, confidence = "critical", min(99, 90 + score)
            elif score > 0 or vad_metrics["dominance"] >= 8:
                status, confidence = "warning", 70
            else:
                status, confidence = "safe", 60
            markers = ', '.join(rule_eval["markers"]) if rule_eval["markers"] else "None"
            return {
                "status": status,
                "confidence": f"{confidence}%",
                "confidence_score": confidence,
                "caller_sentiment": vad_metrics["emotion"],
                "victim_sentiment": vad_metrics["emotion"],
                "details": (f"[Deterministic mode — no GROQ_API_KEY set] Threat markers: {markers}. "
                            f"Add GROQ_API_KEY to backend/.env for full cloud psychological analysis."),
            }

        # --- PHASE 3: DEEP CLOUD PSYCHOLOGICAL ANALYSIS ---
        try:
            prompt = f"""
            You are 'Project Sentinel', a highly advanced Indian telecom fraud detection AI.
            Analyze the following live phone call transcript.

            SUPPORTED LANGUAGES & CULTURAL CONTEXT:
            The transcript may be in English, Hindi, Marathi, Bengali, Telugu, Tamil, Gujarati, Urdu, Kannada, Odia, Malayalam, Punjabi, or Assamese.

            [LOCAL CPU SENSOR DATA & DETERMINISTIC ENGINE]
            Our Local Edge AI calculated the following V.A.D. emotional signature and rule triggers:
            - Detected Base Emotion: {vad_metrics['emotion'].upper()}
            - Valence (1=Hostile, 10=Happy): {vad_metrics['valence']}
            - Arousal (1=Calm, 10=Panic/Urgent): {vad_metrics['arousal']}
            - Dominance (1=Submissive, 10=Commanding): {vad_metrics['dominance']}
            - Hardcoded Threat Score: {rule_eval["threat_score"]}/10
            - Detected Threat Markers: {', '.join(rule_eval["markers"]) if rule_eval["markers"] else "None"}

            🚨 MATHEMATICAL V.A.D. & IMMUNE SYSTEM TRIGGER RULES 🚨
            1. If the Hardcoded Threat Score is >= 3, you MUST classify the status as "critical" regardless of emotion. This means the caller used authority, crime, and isolation tactics.
            2. If Dominance is HIGH (8-10) and Arousal is HIGH (7-10), it indicates an Aggressive Scammer (Coercion).
            3. If Dominance is LOW (1-3) and Arousal is HIGH (7-10), it indicates a Panicked Victim.
            4. If Dominance is MEDIUM (4-6) or the Base Emotion is JOY/LOVE/NEUTRAL, this is a SAFE familial/peer conversation. You MUST IGNORE money transfer keywords if it's a family member/friend requesting it.

            Transcript to analyze:
            "{text_transcript}"

            Respond ONLY with valid JSON exactly matching this format. Do not use markdown wrappers:
            {{
                "status": "safe",
                "confidence_score": 98,
                "caller_sentiment": "Casual/Friendly",
                "victim_sentiment": "Relaxed",
                "details": "Explanation highlighting the VAD metrics, sequence vectors, or safe familial context."
            }}
            """

            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a strict JSON-only fraud detection system."},
                    {"role": "user", "content": prompt}
                ],
                model=self.fast_model_name,
                temperature=0.0
            )

            result_dict = self._parse_json_safe(chat_completion.choices[0].message.content)

            llm_confidence = result_dict.get("confidence_score", 0)
            llm_status = str(result_dict.get("status", "safe")).strip().lower()

            if llm_status not in ["safe", "warning", "critical"]:
                llm_status = "safe"

            # --- PHASE 4: THE ALGORITHMIC IMMUNE SYSTEM (HARD OVERRIDE) ---
            if rule_eval["threat_score"] >= 3:
                llm_status = "critical"
                llm_confidence = max(llm_confidence, 95)
                if "AI OVERRIDE" not in result_dict.get("details", ""):
                    result_dict["details"] = f"🚨 AI OVERRIDE: Hard extortion vectors detected ({', '.join(rule_eval['markers'])}). " + result_dict.get("details", "")

            elif llm_status == "critical" and rule_eval["threat_score"] == 0 and llm_confidence < 90:
                llm_status = "warning"
                result_dict["details"] = f"(Downgraded) Suspicious tone, but no hard threat vectors detected. {result_dict.get('details')}"

            result_dict["status"] = llm_status
            result_dict["confidence"] = f"{llm_confidence}%"

            return result_dict

        except Exception as e:
            error_msg = str(e)
            print(f"Groq Text Error: {error_msg}")

            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                return {"status": "warning", "confidence": "0%", "details": "Rate limit hit. Pausing analysis."}

            return {"status": "warning", "confidence": "0%", "details": "AI analysis failed. Fallback triggered."}

    def extract_entities(self, text_transcript: str) -> dict:
        # Offline / no-key mode: nothing to extract via the cloud model.
        if not self.client:
            return {
                "phone_numbers": [], "upi_ids": [], "bank_accounts": [],
                "institutions": [], "pii_data": [], "person_names": []
            }
        try:
            prompt = f"""
            Analyze the following transcript of an Indian phone call or text.
            The transcript may be in any of the following 13 languages: English, Hindi, Marathi, Bengali, Telugu, Tamil, Gujarati, Urdu, Kannada, Odia, Malayalam, Punjabi, or Assamese.

            Identify and extract any mentioned:
            1. Phone numbers (standardized to include country code if possible)
            2. UPI IDs
            3. Bank account or IFSC numbers
            4. Institutions (e.g., CBI, RBI, Police, Customs, FedEx, HDFC Bank)
            5. PII Data (Personally Identifiable Information like Aadhar numbers, PAN numbers)
            6. Person names (any individual people named in the call)

            Transcript: "{text_transcript}"

            Respond ONLY with valid JSON exactly matching this format. Do not use markdown wrappers:
            {{
                "phone_numbers": ["list", "of", "extracted", "phones"],
                "upi_ids": ["list", "of", "extracted", "upi_ids"],
                "bank_accounts": ["list", "of", "extracted", "bank_accounts_or_ifsc"],
                "institutions": ["list", "of", "extracted", "institutions"],
                "pii_data": ["list", "of", "extracted", "pii"],
                "person_names": ["list", "of", "extracted", "person_names"]
            }}
            """

            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a strict JSON-only entity extraction model. If none are found, return empty lists."},
                    {"role": "user", "content": prompt}
                ],
                model=self.fast_model_name,
                temperature=0.1
            )

            result_dict = self._parse_json_safe(chat_completion.choices[0].message.content)
            return result_dict

        except Exception as e:
            print(f"Entity Extraction Error: {str(e)}")
            return {
                "phone_numbers": [],
                "upi_ids": [],
                "bank_accounts": [],
                "institutions": [],
                "pii_data": [],
                "person_names": []
            }

# Instantiate our engine
analyzer = ScamClassifier()
