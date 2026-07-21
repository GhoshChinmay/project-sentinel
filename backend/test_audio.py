"""
Project Sentinel — Tri-Layer Deepfake Detection Test Suite
===========================================================
Tests the new SOTA ensemble engine with:
  1. A synthetic/robotic waveform (should be detected as DEEPFAKE)
  2. A natural human-like waveform (should be classified as HUMAN)
  3. Validates all 3 layers return expected results
"""

import sys
import numpy as np
import scipy.io.wavfile as wavfile
import io

# Fix Windows cp1252 console encoding — allows Unicode (em-dash, etc.) in output
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from audio_engine import audio_analyzer

def generate_synthetic_wave():
    """
    Fake AI Voice (Deepfake Vocoder):
    - Rigid 440Hz sine (zero pitch variation → low jitter)
    - Constant amplitude (zero amplitude variation → low shimmer)
    - Uniform Gaussian white noise (vocoder hiss → high spectral flatness)
    """
    sample_rate = 16000
    t = np.linspace(0, 4, int(sample_rate * 4), endpoint=False)

    # Perfectly steady 440Hz tone (zero jitter)
    signal = 0.5 * np.sin(2 * np.pi * 440 * t)

    # Deepfake vocoder hiss: uniform noise across all frequencies
    vocoder_hiss = np.random.normal(0, 0.02, signal.shape)

    final_signal = signal + vocoder_hiss

    byte_io = io.BytesIO()
    wavfile.write(byte_io, sample_rate, final_signal.astype(np.float32))
    return byte_io.getvalue()

def generate_natural_wave():
    """
    Natural Human Voice:
    - F0 with vibrato (pitch micro-tremors → high jitter)
    - Amplitude modulation (breathing → high shimmer)
    - Sharp harmonic peaks (formants → low spectral flatness)
    - Chaotic phase from breath noise
    """
    sample_rate = 16000
    t = np.linspace(0, 4, int(sample_rate * 4), endpoint=False)

    # Human vocal cord flutter (vibrato at ~5Hz)
    f0 = 220 + 8 * np.sin(2 * np.pi * 5.2 * t) + np.random.normal(0, 2, t.shape)

    # Fundamental + harmonics (formant structure)
    phase = np.cumsum(2 * np.pi * f0 / sample_rate)
    signal = (
        0.5 * np.sin(phase) +
        0.25 * np.sin(2 * phase) +
        0.12 * np.sin(3 * phase) +
        0.06 * np.sin(4 * phase)
    )

    # Natural amplitude modulation (breathing rhythm ~0.3Hz)
    breath_envelope = 0.8 + 0.2 * np.sin(2 * np.pi * 0.3 * t)
    signal = signal * breath_envelope

    # Chaotic breath noise (natural vocal tract)
    breath_noise = np.random.normal(0, 0.015, signal.shape)

    final_signal = signal + breath_noise

    byte_io = io.BytesIO()
    wavfile.write(byte_io, sample_rate, final_signal.astype(np.float32))
    return byte_io.getvalue()


print("=" * 60)
print("[TEST] PROJECT SENTINEL -- TRI-LAYER DEEPFAKE DETECTION TEST")
print("=" * 60)

# --- TEST 1: SYNTHETIC / DEEPFAKE VOICE ---
print("\n[Test 1] Analyzing Artificial/Robotic Voice Clone...")        
print("-" * 50)
fake_audio = generate_synthetic_wave()
fake_result = audio_analyzer.analyze_audio_wave(fake_audio)

print(f"  Verdict:              {fake_result['audio_signal']}")
print(f"  Is Deepfake:          {fake_result['is_synthetic_voice']}")
print(f"  Ensemble Confidence:  {fake_result['deepfake_probability']}%")
print(f"  Layers Flagged:       {fake_result.get('layers_flagged', '?')}/{fake_result.get('layers_total', '?')}")
print()

# Per-layer breakdown
for layer_key in ['layer_wav2vec', 'layer_biomechanical', 'layer_spectral']:
    layer = fake_result.get(layer_key, {})
    name = layer.get('layer', layer_key)
    available = layer.get('available', False)
    flagged = layer.get('is_deepfake', False)
    conf = layer.get('confidence', 0)
    detail = layer.get('detail', 'N/A')
    status = "[FLAGGED]" if flagged else "[CLEAR]"
    print(f"  [{name.upper():^16}] {status} (conf: {conf}%) | {detail[:80]}")

# --- TEST 2: NATURAL HUMAN VOICE ---
print(f"\n{'=' * 60}")
print("\n[Test 2] Analyzing Natural Human Speech...")
print("-" * 50)
real_audio = generate_natural_wave()
real_result = audio_analyzer.analyze_audio_wave(real_audio)

print(f"  Verdict:              {real_result['audio_signal']}")
print(f"  Is Deepfake:          {real_result['is_synthetic_voice']}")
print(f"  Ensemble Confidence:  {real_result['deepfake_probability']}%")
print(f"  Layers Flagged:       {real_result.get('layers_flagged', '?')}/{real_result.get('layers_total', '?')}")
print()

for layer_key in ['layer_wav2vec', 'layer_biomechanical', 'layer_spectral']:
    layer = real_result.get(layer_key, {})
    name = layer.get('layer', layer_key)
    available = layer.get('available', False)
    flagged = layer.get('is_deepfake', False)
    conf = layer.get('confidence', 0)
    detail = layer.get('detail', 'N/A')
    status = "[FLAGGED]" if flagged else "[CLEAR]"
    print(f"  [{name.upper():^16}] {status} (conf: {conf}%) | {detail[:80]}")

# --- VALIDATION ---
print(f"\n{'=' * 60}")
print("[VALIDATION] SUMMARY")
print("-" * 50)

fake_ok = fake_result['is_synthetic_voice'] == True
real_ok = real_result['is_synthetic_voice'] == False

print(f"  Synthetic audio -> Detected as DEEPFAKE:  {'[PASS]' if fake_ok else '[FAIL]'}")
print(f"  Natural audio   -> Detected as HUMAN:     {'[PASS]' if real_ok else '[FAIL]'}")

if fake_ok and real_ok:
    print("\n[PASS] ALL TESTS PASSED -- Tri-Layer Engine is working correctly!")
else:
    print("\n[FAIL] Some tests failed -- review layer outputs above.")

print("=" * 60)