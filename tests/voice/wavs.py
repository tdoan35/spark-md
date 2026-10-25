"""Deterministic synthetic WAVs for the voice routes, named like 09's bench clips
(<speaker>_<clip_id>.wav, 16 kHz). Generated, never committed: no binaries in the repo, no ffmpeg.
Usage: this module's helpers, or `python tests/voice/wavs.py DIR` to write the clip set.
"""
import io
import math
import random
import struct
import wave

RATE = 16000
# clip_id -> (seconds, tone Hz): tone bursts with a syllable-rate envelope, sized like the bench clips.
CLIPS = {
    'synth_show_nodule': (1.6, 200.0),
    'synth_compare_prior': (1.8, 240.0),
    'synth_why_flag': (1.5, 180.0),
    'synth_reset_view': (1.3, 260.0),
    'synth_silence': (0.5, 0.0),          # acceptance 2 shape: nobody talking
    'synth_room_noise': (2.0, -1.0),      # room-noise stand-in (acceptance 2)
    'synth_too_long': (6.5, 220.0),       # over the 6 s limit
}


def pcm(seconds, hz, seed=7):
    """s16le mono samples: silence (0), noise (<0) or enveloped tone."""
    n = round(seconds * RATE)
    rng = random.Random(seed)
    out = bytearray()
    for i in range(n):
        if hz == 0.0:
            v = 0.0
        elif hz < 0.0:
            v = rng.uniform(-0.4, 0.4)
        else:
            env = 0.5 + 0.5 * math.sin(2 * math.pi * 3.0 * i / RATE)   # ~3 syllables/s
            v = 0.5 * env * math.sin(2 * math.pi * hz * i / RATE)
        out += struct.pack('<h', max(-32768, min(32767, round(v * 32767))))
    return bytes(out)


def wav(samples, rate=RATE, channels=1, bits=16):
    """Wrap raw samples in a RIFF/WAV container (any rate/channels/width, for 422 cases too)."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(bits // 8)
        w.setframerate(rate)
        w.writeframes(samples)
    return buf.getvalue()


def clip(clip_id):
    seconds, hz = CLIPS[clip_id]
    return wav(pcm(seconds, hz))


if __name__ == '__main__':
    import os
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else '.'
    os.makedirs(out, exist_ok=True)
    for name in CLIPS:
        with open(os.path.join(out, name + '.wav'), 'wb') as f:
            f.write(clip(name))
    print(f'wrote {len(CLIPS)} clips to {out}')
