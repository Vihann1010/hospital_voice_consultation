/**
 * Captures mic audio, downsamples to 16 kHz PCM16 frames (~64 ms), and runs a
 * light energy-based VAD so the main thread can barge-in instantly when the
 * patient talks over the assistant.
 *
 * Messages posted to the main thread:
 *   { type: "frame", buffer: ArrayBuffer }   PCM16 mono @16k
 *   { type: "voice_start" }                  speech onset detected
 */
class PcmRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.frameSamples = 1024; // 64 ms at 16 kHz
    this.out = new Int16Array(this.frameSamples);
    this.outIndex = 0;
    this.readPos = 0;

    // VAD state
    this.noiseFloor = 0.008;
    this.voicedFrames = 0;
    this.silentFrames = 0;
    this.inSpeech = false;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    const ratio = sampleRate / this.targetRate;

    // Adaptive noise floor + energy for this render quantum.
    let sumSq = 0;
    for (let i = 0; i < channel.length; i++) sumSq += channel[i] * channel[i];
    const rms = Math.sqrt(sumSq / channel.length);
    this.noiseFloor = 0.995 * this.noiseFloor + 0.005 * Math.min(rms, 0.02);
    const threshold = Math.max(this.noiseFloor * 3.5, 0.012);

    if (rms > threshold) {
      this.voicedFrames++;
      this.silentFrames = 0;
      if (!this.inSpeech && this.voicedFrames >= 3) {
        this.inSpeech = true;
        this.port.postMessage({ type: "voice_start" });
      }
    } else {
      this.silentFrames++;
      this.voicedFrames = 0;
      if (this.inSpeech && this.silentFrames >= 25) this.inSpeech = false;
    }

    // Linear-interpolation downsample into the outgoing PCM16 frame buffer.
    while (this.readPos < channel.length) {
      const idx = Math.floor(this.readPos);
      const frac = this.readPos - idx;
      const a = channel[idx];
      const b = idx + 1 < channel.length ? channel[idx + 1] : a;
      const sample = a + (b - a) * frac;
      const clamped = Math.max(-1, Math.min(1, sample));
      this.out[this.outIndex++] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      this.readPos += ratio;

      if (this.outIndex === this.frameSamples) {
        const copy = this.out.slice().buffer;
        this.port.postMessage({ type: "frame", buffer: copy }, [copy]);
        this.outIndex = 0;
      }
    }
    this.readPos -= channel.length;
    return true;
  }
}

registerProcessor("pcm-recorder", PcmRecorder);
