"""Generate ring.wav and hangup.wav sound files for the frontend."""
import struct, math, wave

def make_wav(filename, sample_rate, samples):
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for s in samples:
            s = max(-1.0, min(1.0, s))
            wf.writeframes(struct.pack('<h', int(s * 32767)))

def generate_ring():
    sr = 22050
    vol = 0.4
    samples = []
    for cycle in range(5):
        # Ring burst: 1s of dual-tone
        for i in range(int(sr * 1.0)):
            t = i / sr
            fade_in = min(1.0, i / (sr * 0.02))
            fade_out = min(1.0, (sr * 1.0 - i) / (sr * 0.02))
            env = fade_in * fade_out
            val = (math.sin(2 * math.pi * 440 * t) + math.sin(2 * math.pi * 480 * t)) * 0.5 * vol * env
            samples.append(val)
        # Silence: 3s
        for i in range(int(sr * 3.0)):
            samples.append(0.0)
    make_wav('ring.wav', sr, samples)
    print(f"Created ring.wav ({len(samples)/sr:.1f}s, {len(samples)*2} bytes)")

def generate_hangup():
    sr = 22050
    vol = 0.35
    tones = [620, 520, 420]
    samples = []
    for idx, freq in enumerate(tones):
        beep_len = 0.15
        num = int(sr * beep_len)
        for i in range(num):
            t = i / sr
            fade_in = min(1.0, i / (sr * 0.01))
            fade_out = min(1.0, (num - i) / (sr * 0.01))
            env = fade_in * fade_out
            samples.append(math.sin(2 * math.pi * freq * t) * vol * env)
        if idx < len(tones) - 1:
            for i in range(int(sr * 0.08)):
                samples.append(0.0)
    make_wav('hangup.wav', sr, samples)
    print(f"Created hangup.wav ({len(samples)/sr:.1f}s, {len(samples)*2} bytes)")

if __name__ == '__main__':
    generate_ring()
    generate_hangup()
    print("Done!")
