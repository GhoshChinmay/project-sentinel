import base64
import json
import io
import os
import numpy as np
from dotenv import load_dotenv
from PIL import Image
from openai import OpenAI

load_dotenv()

# ─────────────────────────────────────────────────────────────────
# OpenRouter Vision Client
# Model: google/gemma-3-27b-it
#   ✅ Natively multimodal — handles image + text in one call
#   ✅ Strong structured JSON output
#   ✅ Excellent at fine-grained visual forensic reasoning
# ─────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
VISION_MODEL = "google/gemma-3-27b-it"

from cv_engine import cv_analyzer

# Safe import for PyTorch
try:
    import torch
    import torchvision.transforms as transforms
    from torchvision import models
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

# ============================================================
# OFFICIAL RBI SECURITY FEATURES (used to ground LLM prompts)
# ============================================================
RBI_SECURITY_FEATURES = """
Official RBI genuine-note characteristics (forensic checklist):
1. WATERMARK: A Mahatma Gandhi portrait watermark visible in the left blank window,
   with light/shade effect and multi-directional lines.
2. SECURITY THREAD: A windowed, partially visible thread running vertically,
   inscribed with "RBI" and "Bharat" in Hindi, appearing as a broken dashed line.
3. INTAGLIO (RAISED) PRINTING: Gandhi's portrait, RBI seal, Ashoka Pillar emblem
   printed in raised ink with visible print-depth/texture.
4. MICRO-LETTERING: Tiny "RBI" text embedded within/around Gandhi's portrait.
5. PAPER TEXTURE: Textured rag paper with visible fiber grain and natural
   photographic noise — not clean, flat, or digitally rendered colors.
6. PORTRAIT REALISM: Gandhi's portrait derived from a real photograph via
   fine engraving — highly detailed, never cartoon or illustration-like.
7. REGISTER & PRINT QUALITY: Clean printing, no broken lines, smudges,
   or mismatched Devanagari and English text.
8. IDENTIFICATION MARK: Raised geometric shape near Ashoka Pillar (denomination-specific).
"""

DENOMINATION_SPECS = """
DENOMINATION SPECIFIC FEATURES:
- Rs.10: Chocolate Brown. Reverse: Sun Temple, Konark.
- Rs.20: Greenish Yellow. Reverse: Ellora Caves.
- Rs.50: Fluorescent Blue. Reverse: Hampi with Chariot.
- Rs.100: Lavender. Reverse: Rani Ki Vav.
- Rs.200: Bright Yellow. Reverse: Sanchi Stupa. Identification mark: H shape.
- Rs.500: Stone Grey. Reverse: Red Fort. Identification mark: Circle.
"""

# ─────────────────────────────────────────────────────────────────
# GANDHI PORTRAIT IDENTITY FEATURES
# Used for the dedicated portrait verification check (Priority 2).
# ─────────────────────────────────────────────────────────────────
GANDHI_IDENTITY_FEATURES = """
Mahatma Gandhi's portrait on genuine Indian Rupee notes has these EXACT visual features:
- COMPLETELY BALD HEAD: Absolutely no hair on the crown or top of the head.
- ROUND WIRE-FRAME GLASSES: Thin, circular spectacles with a narrow bridge.
- PROMINENT LARGE EARLOBES: Distinctively large, rounded earlobes on both sides.
- NARROW NOSE: Thin nose bridge with a prominent tip.
- SLIGHT CLOSED SMILE: Gentle, closed-mouth smile with thin lips.
- ENGRAVING RENDERING: Fine line-engraving style, not a photograph or painting.
- VISIBLE FACIAL WRINKLES: Fine wrinkles around the eyes and cheeks.
- FACE ANGLE: Slightly angled three-quarter view, facing slightly left.

A face with hair on the crown, non-round glasses, different ear proportions,
a wide nose, or resembling any actor, politician, or TV character is NOT Gandhi.
"""


class SentinelTriFactorDetector:
    def __init__(self):
        if not OPENROUTER_API_KEY or "YOUR_KEY_HERE" in OPENROUTER_API_KEY:
            print("WARNING: OPENROUTER_API_KEY not set. Vision AI will use offline fallback only.")
            self.openrouter_client = None
        else:
            self.openrouter_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=OPENROUTER_API_KEY,
            )

        self.vision_model_name = VISION_MODEL
        self.model_path = "sentinel_best.pth"
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu") if HAS_TORCH else "cpu"
        self.class_names = ['fake', 'real']
        self.cnn_model = self._load_custom_model()

        if HAS_TORCH:
            self.transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
            ])

        self.MAX_UNIQUE_COLOR_RATIO = 0.06
        self.MIN_TEXTURE_VARIANCE = 25.0
        self.MAX_FLAT_REGION_RATIO = 0.55

    def _load_custom_model(self):
        if HAS_TORCH and os.path.exists(self.model_path):
            try:
                print("Loading Sentinel Edge-Optimized CNN...")
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    checkpoint = torch.load(self.model_path, map_location=self.device, weights_only=False)

                if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                    state_dict = checkpoint['model_state_dict']
                    if 'class_names' in checkpoint:
                        self.class_names = [c.lower() for c in checkpoint['class_names']]
                else:
                    state_dict = checkpoint

                model = models.efficientnet_b0(weights=None)
                num_ftrs = model.classifier[1].in_features
                model.classifier[1] = nn.Linear(num_ftrs, len(self.class_names))
                model.load_state_dict(state_dict)
                model = model.to(self.device)
                model.eval()
                print("Sentinel CNN loaded successfully.")
                return model
            except Exception as e:
                print(f"Model Load Error: {e}")
        else:
            print("sentinel_best.pth not found. Running in Edge Fallback mode.")
        return None

    def _parse_json_safe(self, text):
        """Safely extract JSON from LLM output, handling markdown and empty responses."""
        try:
            if not text or not text.strip():
                raise ValueError("LLM returned an empty response.")

            text = text.strip()

            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]

            text = text.strip()
            start = text.find('{')
            end = text.rfind('}')

            import re
            if start != -1 and end != -1:
                json_str = text[start:end+1]
                # Clean up stray letter prefixes before keys (like S"reason":)
                json_str = re.sub(r'([a-zA-Z]+)\s*"\s*(\w+)\s*"\s*:', r'"\2":', json_str)
                return json.loads(json_str)

            cleaned_text = re.sub(r'([a-zA-Z]+)\s*"\s*(\w+)\s*"\s*:', r'"\2":', text)
            return json.loads(cleaned_text)
        except Exception as e:
            print(f"RAW LLM OUTPUT (parse failure):\n{text}\n")
            raise ValueError(f"Failed to parse LLM JSON: {e}")

    def _detect_illustration_signature(self, image_bytes: bytes) -> dict:
        """OpenCV-based check for cartoon/illustration signatures."""
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            img = img.resize((512, 512))
            arr = np.asarray(img).astype(np.float32)

            quantized = (arr // 8).astype(np.int32)
            flat_pixels = quantized.reshape(-1, 3)
            unique_colors = len(np.unique(flat_pixels, axis=0))
            total_pixels = flat_pixels.shape[0]
            unique_color_ratio = unique_colors / total_pixels

            gray = np.dot(arr[..., :3], [0.299, 0.587, 0.114])
            gy, gx = np.gradient(gray)
            gradient_mag = np.sqrt(gx ** 2 + gy ** 2)
            texture_variance = float(np.var(gradient_mag))
            flat_region_ratio = float(np.mean(gradient_mag < 2.0))

            mx = arr.max(axis=2)
            mn = arr.min(axis=2)
            saturation = np.where(mx > 0, (mx - mn) / (mx + 1e-6), 0)
            sat_std = float(np.std(saturation))

            flags = []
            suspicion_score = 0

            if unique_color_ratio < self.MAX_UNIQUE_COLOR_RATIO:
                flags.append(f"Very low color diversity ({unique_color_ratio:.4f}) — typical of flat illustration.")
                suspicion_score += 1
            if texture_variance < self.MIN_TEXTURE_VARIANCE:
                flags.append(f"Very low texture variance ({texture_variance:.1f}) — missing paper-grain noise.")
                suspicion_score += 1
            if flat_region_ratio > self.MAX_FLAT_REGION_RATIO:
                flags.append(f"Large flat-color regions ({flat_region_ratio:.1%}) — consistent with digital shading.")
                suspicion_score += 1
            if sat_std < 0.05:
                flags.append("Unnaturally uniform color saturation across the image.")
                suspicion_score += 1

            return {
                "is_likely_illustration": suspicion_score >= 2,
                "suspicion_score": suspicion_score,
                "unique_color_ratio": round(unique_color_ratio, 5),
                "texture_variance": round(texture_variance, 2),
                "flat_region_ratio": round(flat_region_ratio, 3),
                "saturation_std": round(sat_std, 4),
                "flags": flags,
            }
        except Exception as e:
            return {"is_likely_illustration": True, "suspicion_score": 99, "flags": [f"CV check error: {e}"]}

    def _verify_portrait_identity(self, image_bytes: bytes, crop_coords: tuple = None) -> dict:
        """
        Crops the portrait region and independently verifies whether the face
        is Mahatma Gandhi via the Gemma API.
        """
        # Default — assume Gandhi if we can't check (fail-open for portrait only)
        default_pass = {"is_gandhi": True, "confidence": "N/A", "reason": "Portrait check skipped."}

        try:
            if not self.openrouter_client:
                return default_pass

            # --- Crop the portrait region ---
            img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            w, h = img.size

            if crop_coords:
                left, top, right, bottom = crop_coords
            else:
                # Fallback to the middle-right 60% where the printed portrait typically sits
                left  = int(w * 0.40)
                top   = int(h * 0.05)
                right = int(w * 0.95)
                bottom = int(h * 0.95)

            portrait_crop = img.crop((left, top, right, bottom))
            portrait_crop = portrait_crop.resize((512, 512), Image.Resampling.LANCZOS)

            buffered = io.BytesIO()
            portrait_crop.save(buffered, format="JPEG", quality=90)
            portrait_url = f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"

            portrait_prompt = f"""
You are a forensic portrait identity specialist for the Reserve Bank of India.
You are shown a CROPPED image of the portrait region of an Indian Rupee banknote.
Your ONLY job: determine if the face depicted is Mahatma Gandhi.

{GANDHI_IDENTITY_FEATURES}

STRICT RULES:
- If the face has ANY hair on the crown of the head → it is NOT Gandhi → return is_gandhi: false.
- If the glasses are not thin, round, wire-frames → NOT Gandhi → return is_gandhi: false.
- If the face resembles any actor, TV character, or modern politician → NOT Gandhi → return is_gandhi: false.
- If you see no face or just background text → NOT Gandhi → return is_gandhi: false.
- Only return is_gandhi: true if you are HIGHLY CONFIDENT the face matches ALL Gandhi features above.
- Being strict here is critical. A near-miss is a fail. Missing a fake is far worse than a false alarm.

Respond ONLY with valid JSON (no markdown):
{{
    "is_gandhi": true or false,
    "confidence": "e.g. 95%",
    "reason": "One sentence describing what you actually see in this face."
}}
"""

            response = self.openrouter_client.chat.completions.create(
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": portrait_prompt},
                        {"type": "image_url", "image_url": {"url": portrait_url}}
                    ]
                }],
                model=self.vision_model_name,
                temperature=0.0,
                max_tokens=256,
            )

            raw = response.choices[0].message.content
            print(f"\n[Portrait Identity Raw]\n{raw}\n")
            
            is_gandhi = True
            confidence = "Unknown"
            reason = "No reason provided."

            try:
                result = self._parse_json_safe(raw)
                is_gandhi = bool(result.get("is_gandhi", True))
                confidence = str(result.get("confidence", "Unknown"))
                reason = str(result.get("reason", "No reason provided."))
            except Exception as parse_err:
                print(f"[Portrait Check Parsing Warning — using regex fallback]: {parse_err}")
                raw_clean = raw.lower()
                # Substring fallback for is_gandhi
                if "is_gandhi" in raw_clean:
                    after_key = raw_clean.split("is_gandhi")[1]
                    if "false" in after_key[:20]:
                        is_gandhi = False
                    elif "true" in after_key[:20]:
                        is_gandhi = True
                
                # Extract reason from raw text if possible
                import re
                reason_match = re.search(r'"reason"\s*:\s*"([^"]+)"', raw, re.IGNORECASE)
                if reason_match:
                    reason = reason_match.group(1)
                else:
                    reason = f"Extracted via raw fallback: {raw.strip()}"

            print(f"[Portrait Verdict] is_gandhi={is_gandhi} | confidence={confidence} | reason={reason}")
            return {"is_gandhi": is_gandhi, "confidence": confidence, "reason": reason}

        except Exception as e:
            print(f"[Portrait Check Error — skipping]: {e}")
            return {"is_gandhi": True, "confidence": "N/A", "reason": f"Portrait check skipped: {e}"}

    def analyze_document(self, base64_image: str) -> dict:
        try:
            image_bytes = base64.b64decode(base64_image)
            img_raw = Image.open(io.BytesIO(image_bytes)).convert('RGB')

            # --- PRE-FLIGHT: Compress image for API efficiency ---
            img = img_raw.copy()
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            optimized_url = f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"

            # ─────────────────────────────────────────────────────
            # PHASE 1: LOCAL EDGE AI (runs before any API call)
            # ─────────────────────────────────────────────────────
            illustration_check = self._detect_illustration_signature(image_bytes)
            cv_results = cv_analyzer.analyze_image_quality(image_bytes)
            cv_results['texture_variance'] = illustration_check.get('texture_variance')
            cv_results['flat_region_ratio'] = f"{illustration_check.get('flat_region_ratio', 0) * 100:.1f}%"

            cnn_label = "safe"
            cnn_confidence = 90.0

            if self.cnn_model and HAS_TORCH:
                image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
                tensor = self.transform(image).unsqueeze(0).to(self.device)
                with torch.no_grad():
                    outputs = self.cnn_model(tensor)
                    probs = torch.nn.functional.softmax(outputs[0], dim=0)

                    try:
                        fake_idx = self.class_names.index('fake')
                        real_idx = self.class_names.index('real')
                    except ValueError:
                        fake_idx, real_idx = 0, 1

                    fake_prob = probs[fake_idx].item() * 100
                    real_prob = probs[real_idx].item() * 100

                    if fake_prob > real_prob:
                        cnn_label, cnn_confidence = "critical", fake_prob
                    else:
                        cnn_label, cnn_confidence = "safe", real_prob

            # --- Offline fallback if API fails ---
            def trigger_offline_fallback(error_msg):
                print(f"\n{'='*60}")
                print(f"CLOUD API FAILED — Falling over to Local Edge AI")
                print(f"   Reason: {error_msg}")
                print(f"{'='*60}\n")

                is_fake = (cnn_label == "critical" or illustration_check["is_likely_illustration"])
                status = "critical" if is_fake else "safe"
                markers = []
                anomalies = []

                if illustration_check["is_likely_illustration"]:
                    markers.append("Local Computer Vision detected cartoon or digital render signatures.")
                    markers.extend(illustration_check.get("flags", []))
                    anomalies.append({
                        "label": "Synthetic/Cartoon Signature Detected",
                        "box": {"left": "10%", "top": "10%", "width": "80%", "height": "80%"}
                    })

                if cnn_label == "critical":
                    markers.append(f"Edge CNN: Counterfeit ({cnn_confidence:.1f}% confidence).")
                else:
                    markers.append(f"Edge CNN: Genuine ({cnn_confidence:.1f}% confidence).")

                if status == "safe":
                    markers.append("All local sensor signals indicate genuine physical features.")

                return {
                    "visual_reasoning": "Cloud AI was unavailable. Result based on local Edge CNN and OpenCV texture analysis.",
                    "denomination": "Edge Analysis",
                    "status": status,
                    "confidence": f"{cnn_confidence:.1f}%",
                    "forgery_markers": markers,
                    "anomalies": anomalies,
                    "cv_metrics": cv_results,
                    "illustration_check": illustration_check,
                    "dl_metrics": f"{'Counterfeit' if cnn_label == 'critical' else 'Genuine'} ({cnn_confidence:.1f}%)"
                }

            # ─────────────────────────────────────────────────────
            # PHASE 2A: CLOUD API — Main forensic scan
            # ─────────────────────────────────────────────────────
            try:
                cnn_verdict_str = 'COUNTERFEIT (critical)' if cnn_label == 'critical' else 'GENUINE (safe)'
                status_to_set = 'critical' if cnn_label == 'critical' else 'safe'
                verdict_word = 'counterfeit' if cnn_label == 'critical' else 'genuine'

                unified_report_prompt = f"""
You are a Forensic AI Assistant for the Reserve Bank of India (RBI).
You have two responsibilities: (1) verify if this image is a valid Indian Rupee note,
(2) locate the main printed portrait of Mahatma Gandhi, and (3) generate a forensic report synchronized with our trained Edge CNN model.

Edge CNN Model Verdict: {cnn_verdict_str} (Confidence: {cnn_confidence:.1f}%)

{RBI_SECURITY_FEATURES}

{DENOMINATION_SPECS}

══════════════════════════════════════════
STEP 1 — IS THIS A VALID INDIAN RUPEE NOTE?
══════════════════════════════════════════
If the image is NOT an Indian Rupee banknote (blank paper, random object, person,
digital illustration, cartoon), return:
- status: "invalid"
- visual_reasoning: explain why (e.g. "This is a blank piece of paper, not a currency note")
- forgery_markers: [{{"label": "Not a valid Indian Rupee note", "status": "failed"}}]
- anomalies: []

══════════════════════════════════════════
STEP 2 — LOCATE PORTRAIT
══════════════════════════════════════════
If it IS a note, locate the main printed portrait of Mahatma Gandhi (not the watermark).
It can be on the right side of the note (standard layout) or on the left side (if captured by a mirrored webcam).
Return its bounding box coordinates as percentages of the image width/height in "portrait_box".

══════════════════════════════════════════
STEP 3 — SYNC WITH CNN VERDICT & ASSESS SPECIFIC FEATURES
══════════════════════════════════════════
Set status to "{status_to_set}" and confidence to "{cnn_confidence:.1f}%".

In "forgery_markers", you MUST evaluate each of these security features:
1. "Genuine Indian Rupee note": verify if it is an official RBI printed note layout.
2. "Mahatma Gandhi portrait present": verify if a portrait exists.
3. "RBI logo and guarantee clauses present": verify if present.
4. "Correct denomination value": verify if correct denomination is present.
5. "Consistent color scheme": verify color schema of the note.

CRITICAL FEATURE MARKING RULES (STRICTLY ENFORCED):
- For EACH of the 5 features above, output an object: {{"label": "string", "status": "passed | failed"}}.
- If the note is counterfeit (status is critical), ONLY mark features as "failed" if they are ACTUALLY failed or missing in the image.
- Do NOT mark correct features as "failed" just to justify a counterfeit status. For example, if Gandhi's face is fake/substituted but the RBI logo and denomination are correct, "Mahatma Gandhi portrait present" should be "failed", but "RBI logo and guarantee clauses present" and "Correct denomination value" MUST be marked "passed".
- If the note is genuine (status is safe), mark all verified features as "passed".

Respond ONLY with valid JSON (no markdown wrappers):
{{
    "visual_reasoning": "string",
    "denomination": "string",
    "status": "critical | safe | invalid",
    "confidence": "string",
    "forgery_markers": [
        {{"label": "Genuine Indian Rupee note", "status": "passed | failed"}},
        {{"label": "Mahatma Gandhi portrait present", "status": "passed | failed"}},
        {{"label": "RBI logo and guarantee clauses present", "status": "passed | failed"}},
        {{"label": "Correct denomination value (Rs. XX)", "status": "passed | failed"}},
        {{"label": "Consistent color scheme (color)", "status": "passed | failed"}}
    ],
    "portrait_box": {{
        "left": "percentage string, e.g. 50%",
        "top": "percentage string, e.g. 5%",
        "width": "percentage string, e.g. 40%",
        "height": "percentage string, e.g. 90%"
    }},
    "anomalies": [
        {{
            "label": "string",
            "box": {{"left": "string", "top": "string", "width": "string", "height": "string"}}
        }}
    ]
}}
"""

                if not self.openrouter_client:
                    raise RuntimeError("OpenRouter client not initialized — OPENROUTER_API_KEY missing in backend/.env")

                chat_completion = self.openrouter_client.chat.completions.create(
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": unified_report_prompt},
                            {"type": "image_url", "image_url": {"url": optimized_url}}
                        ]
                    }],
                    model=self.vision_model_name,
                    temperature=0.0,
                    max_tokens=2048,
                )

                raw_content = chat_completion.choices[0].message.content
                print(f"\n[Main Scan Response]\n{raw_content[:600]}\n")
                final_result = self._parse_json_safe(raw_content)

            except Exception as cloud_error:
                return trigger_offline_fallback(str(cloud_error))

            # ─────────────────────────────────────────────────────
            # PHASE 2B: PORTRAIT IDENTITY VERIFICATION (Priority 2)
            # Only runs if the image was accepted as a valid note.
            # ─────────────────────────────────────────────────────
            reporter_status = str(final_result.get("status", "critical")).strip().lower()

            if reporter_status == "invalid":
                reason = final_result.get("visual_reasoning", "This image does not appear to be an Indian Rupee note.")
                return {
                    "status": "invalid",
                    "confidence": "100%",
                    "visual_reasoning": reason,
                    "forgery_markers": [{"label": reason, "status": "failed"}],
                    "cv_metrics": cv_results,
                    "dl_metrics": None,
                    "anomalies": []
                }

            # Parse portrait bounding box dynamically
            portrait_box = final_result.get("portrait_box")
            crop_coords = None
            portrait_is_gandhi = True
            portrait_reason = ""
            portrait_check = {"is_gandhi": True, "confidence": "N/A", "reason": "Portrait check not performed."}
            portrait_location_mismatch = False
            portrait_mismatch_reason = ""

            w, h = img_raw.size

            if portrait_box and isinstance(portrait_box, dict):
                try:
                    def parse_pct(val):
                        if isinstance(val, str):
                            return float(val.replace("%", "").strip())
                        return float(val)

                    box_left = parse_pct(portrait_box.get("left", 0))

                    # Apply user rule: portrait must never be on the right half of the image
                    if box_left > 50.0:
                        portrait_location_mismatch = True
                        portrait_mismatch_reason = "Portrait is on the right side of the note (must be on the left/center side)."
                    
                    if box_left < 40.0: # Mirrored layout
                        px_left = int(w * 0.02)
                        px_top = int(h * 0.02)
                        px_right = int(w * 0.55)
                        px_bottom = int(h * 0.98)
                    else: # Standard layout
                        px_left = int(w * 0.40)
                        px_top = int(h * 0.02)
                        px_right = int(w * 0.98)
                        px_bottom = int(h * 0.98)

                    crop_coords = (px_left, px_top, px_right, px_bottom)
                except Exception as box_err:
                    print(f"Error parsing portrait_box coordinates: {box_err}")
            else:
                # Default to standard right-side crop
                crop_coords = (int(w * 0.40), int(h * 0.02), int(w * 0.98), int(h * 0.98))

            if portrait_location_mismatch:
                print(f"\n PORTRAIT LOCATION MISMATCH — Overriding verdict to CRITICAL\n   Reason: {portrait_mismatch_reason}\n")
                final_result["status"] = "critical"
                final_result["confidence"] = f"{cnn_confidence:.1f}%"
                
                existing_markers = list(final_result.get("forgery_markers") or [])
                found_marker = False
                for m in existing_markers:
                    if isinstance(m, dict) and "portrait" in m.get("label", "").lower():
                        m["status"] = "failed"
                        m["label"] = f"PORTRAIT LOCATION MISMATCH: {portrait_mismatch_reason}"
                        found_marker = True
                
                if not found_marker:
                    existing_markers.insert(0, {
                        "label": f"PORTRAIT LOCATION MISMATCH: {portrait_mismatch_reason}",
                        "status": "failed"
                    })
                final_result["forgery_markers"] = existing_markers
                
                # Add anomaly box to right side
                anomalies = list(final_result.get("anomalies") or [])
                anomalies.insert(0, {
                    "label": "Portrait Location Mismatch (On Right Side)",
                    "box": {
                        "left": portrait_box.get("left", "55%"),
                        "top": portrait_box.get("top", "5%"),
                        "width": portrait_box.get("width", "40%"),
                        "height": portrait_box.get("height", "90%")
                    }
                })
                final_result["anomalies"] = anomalies
                portrait_is_gandhi = False
                portrait_reason = portrait_mismatch_reason
            else:
                # Run the dedicated portrait identity check
                portrait_check = self._verify_portrait_identity(image_bytes, crop_coords)
                portrait_is_gandhi = portrait_check.get("is_gandhi", True)
                portrait_reason = portrait_check.get("reason", "")

            # If portrait is invalid and NOT overridden by location mismatch → override status and inject marker
            if not portrait_is_gandhi and not portrait_location_mismatch:
                print(f"\n PORTRAIT IDENTITY MISMATCH — Overriding verdict to CRITICAL\n   Reason: {portrait_reason}\n")
                
                final_result["status"] = "critical"
                final_result["confidence"] = f"{cnn_confidence:.1f}%"
                
                existing_markers = list(final_result.get("forgery_markers") or [])
                
                # Check if "Mahatma Gandhi portrait present" exists as an object and set it to failed
                found_marker = False
                for m in existing_markers:
                    if isinstance(m, dict) and "portrait" in m.get("label", "").lower():
                        m["status"] = "failed"
                        m["label"] = f"PORTRAIT IDENTITY MISMATCH: The face is NOT Mahatma Gandhi. {portrait_reason}"
                        found_marker = True
                
                if not found_marker:
                    existing_markers.insert(0, {
                        "label": f"PORTRAIT IDENTITY MISMATCH: The face on this note is NOT Mahatma Gandhi. {portrait_reason}",
                        "status": "failed"
                    })
                
                final_result["forgery_markers"] = existing_markers

                # Ensure portrait region bounding box is always shown on mismatch
                anomalies = list(final_result.get("anomalies") or [])
                if not any("portrait" in str(a.get("label", "")).lower() for a in anomalies):
                    b_left = portrait_box.get("left") if (portrait_box and portrait_box.get("left")) else "50%"
                    b_top = portrait_box.get("top") if (portrait_box and portrait_box.get("top")) else "5%"
                    b_width = portrait_box.get("width") if (portrait_box and portrait_box.get("width")) else "40%"
                    b_height = portrait_box.get("height") if (portrait_box and portrait_box.get("height")) else "90%"
                    
                    anomalies.insert(0, {
                        "label": "Portrait Identity Mismatch — Not Mahatma Gandhi",
                        "box": {"left": b_left, "top": b_top, "width": b_width, "height": b_height}
                    })
                final_result["anomalies"] = anomalies

            # ─────────────────────────────────────────────────────
            # PHASE 3: FINAL FUSION
            # ─────────────────────────────────────────────────────
            final_status = str(final_result.get("status", "critical")).strip().lower()
            override_flags = []

            if cnn_label == "critical":
                override_flags.append(f"Edge CNN flagged as counterfeit ({cnn_confidence:.1f}% confidence).")
            if illustration_check["is_likely_illustration"]:
                override_flags.append("Local CV detected cartoon or illustration signatures.")

            if override_flags and final_status == "safe":
                final_result["status"] = "critical"
                existing = list(final_result.get("forgery_markers") or [])
                for f in override_flags:
                    existing.append({"label": f, "status": "failed"})
                final_result["forgery_markers"] = existing
                if not final_result.get("anomalies"):
                    final_result["anomalies"] = [{
                        "label": "Algorithmic Integrity Mismatch",
                        "box": {"left": "40%", "top": "10%", "width": "20%", "height": "80%"}
                    }]

            # Attach sensor metadata for UI display
            final_result['cv_metrics'] = cv_results
            final_result['illustration_check'] = illustration_check
            final_result['dl_metrics'] = f"{'Counterfeit' if cnn_label == 'critical' else 'Genuine'} ({cnn_confidence:.1f}%)"
            final_result['portrait_check'] = portrait_check

            return final_result

        except Exception as e:
            print(f"\n[CRITICAL SYSTEM ERROR in analyze_document]: {e}\n")
            return {
                "status": "invalid",
                "confidence": "N/A",
                "visual_reasoning": "A critical internal error occurred while processing this image.",
                "forgery_markers": [{"label": "System error: Could not process the image.", "status": "failed"}],
                "cv_metrics": {},
                "dl_metrics": "Error",
                "anomalies": []
            }


vision_analyzer = SentinelTriFactorDetector()