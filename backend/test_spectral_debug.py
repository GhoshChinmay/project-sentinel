import sys
import numpy as np
import scipy.io.wavfile as wavfile
import io

from audio_engine import audio_analyzer
from test_audio import generate_synthetic_wave, generate_natural_wave
import librosa

def test_sig():
    f = generate_synthetic_wave()
    sr, sig = wavfile.read(io.BytesIO(f))
    sig = sig.astype(np.float32) / np.max(np.abs(sig))
    res = audio_analyzer._analyze_spectral(sig)
    res2 = audio_analyzer._analyze_biomechanics(sig)
    print("Synthetic Spectral:", res)
    print("Synthetic Biomech:", res2)

    r = generate_natural_wave()
    sr, sig2 = wavfile.read(io.BytesIO(r))
    sig2 = sig2.astype(np.float32) / np.max(np.abs(sig2))
    res3 = audio_analyzer._analyze_spectral(sig2)
    res4 = audio_analyzer._analyze_biomechanics(sig2)
    print("Natural Spectral:", res3)
    print("Natural Biomech:", res4)

test_sig()
