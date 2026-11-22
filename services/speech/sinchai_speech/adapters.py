"""ASR and TTS adapters for Hindi, Maithili and Bhojpuri.

  TextASR       offline: the "audio" is the transcript itself (demo, tests); an optional noise model
                (word drops / substitutions) lets the eval measure how robust Saathi is to ASR errors
  HttpASR/TTS   a hosted Indic speech service (SPEECH_ASR_URL / SPEECH_TTS_URL / SPEECH_API_KEY)
  EspeakTTS     offline TTS through espeak-ng if installed (Hindi voice), else text only

Word error rate is computed with a standard Levenshtein alignment over words.
"""

from __future__ import annotations

import base64
import random
import shutil
import subprocess
from dataclasses import dataclass

import httpx


def wer(ref: str, hyp: str) -> float:
    r, h = ref.split(), hyp.split()
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r)][len(h)] / max(len(r), 1)


@dataclass
class TextASR:
    noise: float = 0.0  # probability per word of drop or substitution
    seed: int = 0
    name: str = "text-passthrough"

    def transcribe(self, audio_or_text: str, language: str = "hi") -> dict:
        words = audio_or_text.split()
        if self.noise > 0:
            rng = random.Random(f"{self.seed}|{audio_or_text}")
            out = []
            for w in words:
                x = rng.random()
                if x < self.noise / 2:
                    continue
                if x < self.noise:
                    out.append(w[:-1] if len(w) > 2 else w)
                else:
                    out.append(w)
            words = out
        return {"text": " ".join(words), "language": language, "engine": self.name}


@dataclass
class HttpASR:
    url: str
    api_key: str | None = None
    name: str = "http-asr"

    def transcribe(self, audio_b64: str, language: str = "hi") -> dict:
        r = httpx.post(self.url, headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
                       json={"audio": audio_b64, "language": language}, timeout=30)
        r.raise_for_status()
        j = r.json()
        return {"text": j.get("text", ""), "language": language, "engine": self.name}


@dataclass
class EspeakTTS:
    name: str = "espeak-ng"

    def available(self) -> bool:
        return shutil.which("espeak-ng") is not None

    def synthesize(self, text: str, language: str = "hi") -> dict:
        if not self.available() or not text:
            return {"text": text, "audio_b64": None, "engine": "text-only"}
        voice = {"hi": "hi", "mai": "hi", "bho": "hi", "en": "en-in"}.get(language, "hi")
        wav = subprocess.run(["espeak-ng", "-v", voice, "--stdout", text], capture_output=True, timeout=20).stdout
        return {"text": text, "audio_b64": base64.b64encode(wav).decode(), "engine": self.name, "mime": "audio/wav"}


@dataclass
class HttpTTS:
    url: str
    api_key: str | None = None

    def synthesize(self, text: str, language: str = "hi") -> dict:
        r = httpx.post(self.url, headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
                       json={"text": text, "language": language}, timeout=30)
        r.raise_for_status()
        return {"text": text, **r.json(), "engine": "http-tts"}


@dataclass
class TextTTS:
    def synthesize(self, text: str, language: str = "hi") -> dict:
        return {"text": text, "audio_b64": None, "engine": "text-only"}


def make_asr(provider: str, url: str | None = None, key: str | None = None):
    return HttpASR(url, key) if provider == "http" and url else TextASR()


def make_tts(provider: str, url: str | None = None, key: str | None = None):
    if provider == "http" and url:
        return HttpTTS(url, key)
    e = EspeakTTS()
    return e if e.available() else TextTTS()
