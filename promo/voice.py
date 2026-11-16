"""Add a spoken voice to a finished promo video.

Usage (from the repo root, with the project venv):
  python promo/voice.py promo/laxa-video/voice.json           # → out/rmink-laxa-sv-*-alma.mp4
  python promo/voice.py promo/laxa-video/voice.json --plain   # no emphasis, for comparison
  python promo/voice.py promo/laxa-video/voice.json --wav     # only the voice track

The voice is Alma, a Swedish Piper voice by Daniel Nylander (CC BY 4.0):
https://huggingface.co/yeagersthlm/piper-voice-sv-alma. The model is fetched to
promo/out/assets/voices/ on first use. Needs `pip install piper-tts onnx`.

The last word of every sentence is stressed. Piper has no emphasis control, so
the model graph is patched to take a length factor per phoneme: the last word is
drawn out, a short pause is laid before it, and it is lifted a few dB afterwards.

voice.json:
  { "voice": "alma", "videos": "rmink-laxa-sv-*.mp4",
    "say": {"rmink": "är-em-ink"},          # spelling the voice reads right
    "lines": [[0.6, "Tisdag kväll. Läxa i matte."], ...] }   # start time, text
"""

import argparse
import json
import subprocess
import sys
import urllib.request
import wave
from pathlib import Path

import numpy as np
import onnx
import onnxruntime
from onnx import TensorProto, helper
from piper import PiperVoice

PROMO = Path(__file__).resolve().parent
OUT = PROMO / "out"
VOICES = OUT / "assets" / "voices"
MODELS = {
    "alma": ("sv_SE-alma-medium.onnx", "https://huggingface.co/yeagersthlm/piper-voice-sv-alma/resolve/main/"),
}
HOP = 256  # samples per model frame

# Emphasis on the last word of a sentence
STRETCH = 1.22  # every sound in the word
STRESSED = 1.5  # its stressed vowel
PAUSE = 5  # frames of air before the word (≈ 60 ms)
LIFT_DB = 3.0
GAP = 0.32  # seconds between sentences


def model_path(name: str) -> Path:
    file, base = MODELS[name]
    VOICES.mkdir(parents=True, exist_ok=True)
    for f in (file, file + ".json"):
        if not (VOICES / f).exists():
            print(f"fetching {f}", flush=True)
            urllib.request.urlretrieve(base + f, VOICES / f)
    return VOICES / file


def session(path: Path) -> onnxruntime.InferenceSession:
    """The voice model with two extra inputs, a length factor and extra frames per
    phoneme, and its phoneme lengths as a second output."""
    model = onnx.load(str(path))
    g = model.graph
    ceil = next(n for n in g.node if n.op_type == "Ceil")
    at = list(g.node).index(ceil)
    lengths = ceil.output[0]
    g.node.insert(at, helper.make_node("Mul", [ceil.input[0], "dur_scale"], ["dur_scaled"]))
    ceil.input[0] = "dur_scaled"
    ceil.output[0] = "dur_ceiled"
    g.node.insert(at + 2, helper.make_node("Add", ["dur_ceiled", "dur_add"], [lengths]))
    for name in ("dur_scale", "dur_add"):
        g.input.append(helper.make_tensor_value_info(name, TensorProto.FLOAT, [1, 1, None]))
    g.output.append(helper.make_tensor_value_info(lengths, TensorProto.FLOAT, None))
    return onnxruntime.InferenceSession(model.SerializeToString(), providers=["CPUExecutionProvider"])


class Voice:
    def __init__(self, name: str):
        path = model_path(name)
        self.piper = PiperVoice.load(str(path))
        self.cfg = json.loads(Path(str(path) + ".json").read_text())
        self.rate = self.cfg["audio"]["sample_rate"]
        self.ids = self.cfg["phoneme_id_map"]
        self.sess = session(path)
        self.lengths = self.sess.get_outputs()[1].name

    def sentence(self, phonemes: list[str], emphasis: bool, speed: float = 1.0) -> np.ndarray:
        """One sentence as float samples, its last word stressed."""
        pad = self.ids["_"]
        ids = [*self.ids["^"], *pad]
        where = []  # index into ids for every phoneme
        for p in phonemes:
            if p not in self.ids:
                continue
            where.append((p, len(ids)))
            ids += [*self.ids[p], *pad]
        ids += self.ids["$"]
        scale = np.ones(len(ids), np.float32)
        add = np.zeros(len(ids), np.float32)

        # The last word: from the last space to the closing punctuation
        sounds = [i for i, (p, _) in enumerate(where) if p not in " .,!?:;"]
        word = None
        if emphasis and sounds:
            last = sounds[-1]
            spaces = [i for i, (p, _) in enumerate(where[:last]) if p == " "]
            first = spaces[-1] + 1 if spaces else 0
            if spaces:  # a sentence of one word is already stressed
                word = (where[first][1], where[last][1] + 2)
                scale[word[0] : word[1]] = STRETCH
                marks = [i for i in range(first, last + 1) if where[i][0] == "ˈ"]
                if marks and marks[-1] < last:
                    v = where[marks[-1] + 1][1]
                    end = where[marks[-1] + 2][1] + 2 if marks[-1] + 2 <= last and where[marks[-1] + 2][0] == "ː" else v + 2
                    scale[v:end] = STRESSED
                add[where[spaces[-1]][1]] = PAUSE

        inf = self.cfg["inference"]
        audio, dur = self.sess.run(
            ["output", self.lengths],
            {
                "input": np.array([ids], np.int64),
                "input_lengths": np.array([len(ids)], np.int64),
                "scales": np.array([inf["noise_scale"], inf["length_scale"] / speed, inf["noise_w"]], np.float32),
                "dur_scale": scale.reshape(1, 1, -1),
                "dur_add": add.reshape(1, 1, -1),
            },
        )
        audio = audio.reshape(-1).astype(np.float32)
        if word:
            starts = np.concatenate([[0], np.cumsum(dur.reshape(-1))]) * HOP
            a, b = int(starts[word[0]]), min(int(starts[word[1]]), len(audio))
            ramp = int(self.rate * 0.04)
            gain = np.ones(len(audio), np.float32)
            top = 10 ** (LIFT_DB / 20)
            gain[a:b] = top
            gain[max(a - ramp, 0) : a] = np.linspace(1, top, a - max(a - ramp, 0))
            gain[b : b + ramp] = np.linspace(top, 1, len(gain[b : b + ramp]))
            audio *= gain
        return audio

    def line(self, text: str, emphasis: bool, speed: float = 1.0) -> np.ndarray:
        parts = []
        for phonemes in self.piper.phonemize(text):
            if parts:
                parts.append(np.zeros(int(self.rate * GAP / speed), np.float32))
            parts.append(trim(self.sentence(phonemes, emphasis, speed)))
        return np.concatenate(parts)


def trim(a: np.ndarray, floor: float = 0.01) -> np.ndarray:
    loud = np.nonzero(np.abs(a) > floor)[0]
    return a[max(loud[0] - 400, 0) : loud[-1] + 1200] if len(loud) else a


def track(spec: dict, emphasis: bool, length: float) -> tuple[np.ndarray, int]:
    voice = Voice(spec.get("voice", "alma"))
    say = spec.get("say", {})
    lines = spec["lines"]
    out = np.zeros(int(length * voice.rate), np.float32)
    for i, (start, text) in enumerate(lines):
        for k, v in say.items():
            text = text.replace(k, v)
        room = (lines[i + 1][0] if i + 1 < len(lines) else length) - start - 0.15
        audio = voice.line(text, emphasis)
        speed = 1.0
        if len(audio) / voice.rate > room:  # talk a little faster rather than run into the next line
            speed = min(len(audio) / voice.rate / room * 1.02, 1.15)
            audio = voice.line(text, emphasis, speed)
        secs = len(audio) / voice.rate
        flag = "  ← TOO LONG" if secs > room else ""
        print(f"{start:5.1f}s  {secs:4.1f}s of {room:4.1f}s  x{speed:.2f}  {lines[i][1]}{flag}", flush=True)
        a = int(start * voice.rate)
        audio = audio[: len(out) - a]
        out[a : a + len(audio)] += audio
    peak = np.abs(out).max()
    return out * (0.89 / peak if peak else 1), voice.rate


def write_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


def seconds(path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    return float(subprocess.check_output(cmd))


def mux(video: Path, wav: Path, out: Path) -> None:
    """The picture untouched, the voice as its sound."""
    small = video.stat().st_size < 2_000_000  # the MMS cut: keep it small
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(wav),
        "-map", "0:v", "-map", "1:a", "-c:v", "copy",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000",
        "-c:a", "aac", "-b:a", "32k" if small else "128k", "-ac", "1" if small else "2",
        "-shortest", "-movflags", "+faststart", str(out),
    ]  # fmt: skip
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", type=Path, help="voice.json beside the video")
    ap.add_argument("--plain", action="store_true", help="no emphasis on the last word")
    ap.add_argument("--wav", action="store_true", help="only write the voice track")
    a = ap.parse_args()
    spec = json.loads(a.spec.read_text())
    name = spec.get("voice", "alma")
    tag = name + ("-plain" if a.plain else "")
    videos = sorted(v for v in OUT.glob(spec["videos"]) if f"-{name}" not in v.stem)
    if not videos:
        sys.exit(f"no videos match {spec['videos']} in {OUT}")
    audio, rate = track(spec, not a.plain, seconds(videos[0]))
    wav = OUT / f"{a.spec.parent.name}-{tag}.wav"
    write_wav(wav, audio, rate)
    print(wav)
    if not a.wav:
        for v in videos:
            out = v.with_name(f"{v.stem}-{tag}.mp4")
            mux(v, wav, out)
            print(out)
