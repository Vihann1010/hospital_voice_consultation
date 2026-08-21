/**
 * Gapless PCM16 playback queue.
 *
 * TTS audio arrives as raw PCM16 chunks over the WebSocket. Each chunk is
 * scheduled back-to-back on a single AudioContext timeline so playback is
 * continuous, and flush() cancels every scheduled source instantly for
 * barge-in interruption.
 */
export class PcmPlayer {
  private context: AudioContext | null = null;
  private nextStartTime = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private leftover: Uint8Array | null = null; // odd trailing byte between chunks

  constructor(
    private sampleRate: number,
    private onPlaybackChange?: (playing: boolean) => void
  ) {}

  async init(): Promise<void> {
    if (this.context) return;
    this.context = new AudioContext();
    if (this.context.state === "suspended") {
      // Browsers may block audio until a gesture; try now and again on first tap.
      void this.context.resume().catch(() => undefined);
      const unlock = () => {
        void this.context?.resume().catch(() => undefined);
        document.removeEventListener("pointerdown", unlock);
        document.removeEventListener("keydown", unlock);
      };
      document.addEventListener("pointerdown", unlock);
      document.addEventListener("keydown", unlock);
    }
    this.nextStartTime = this.context.currentTime;
  }

  setSampleRate(rate: number): void {
    this.sampleRate = rate;
  }

  get isPlaying(): boolean {
    return this.sources.size > 0;
  }

  enqueue(chunk: ArrayBuffer): void {
    if (!this.context || chunk.byteLength === 0) return;

    // Stitch chunks so an odd byte never corrupts sample alignment.
    let bytes = new Uint8Array(chunk);
    if (this.leftover) {
      const joined = new Uint8Array(this.leftover.length + bytes.length);
      joined.set(this.leftover);
      joined.set(bytes, this.leftover.length);
      bytes = joined;
      this.leftover = null;
    }
    const usable = bytes.length - (bytes.length % 2);
    if (usable === 0) {
      this.leftover = bytes;
      return;
    }
    if (usable < bytes.length) this.leftover = bytes.slice(usable);

    const pcm = new Int16Array(bytes.buffer, bytes.byteOffset, usable / 2);
    const floats = new Float32Array(pcm.length);
    for (let i = 0; i < pcm.length; i++) floats[i] = pcm[i] / 0x8000;

    const buffer = this.context.createBuffer(1, floats.length, this.sampleRate);
    buffer.copyToChannel(floats, 0);

    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);

    const now = this.context.currentTime;
    const startAt = Math.max(this.nextStartTime, now + 0.02);
    source.start(startAt);
    this.nextStartTime = startAt + buffer.duration;

    this.sources.add(source);
    if (this.sources.size === 1) this.onPlaybackChange?.(true);
    source.onended = () => {
      this.sources.delete(source);
      if (this.sources.size === 0) this.onPlaybackChange?.(false);
    };
  }

  /** Stop everything scheduled immediately (patient interrupted). */
  flush(): void {
    for (const source of this.sources) {
      try {
        source.onended = null;
        source.stop();
        source.disconnect();
      } catch {
        /* already stopped */
      }
    }
    const wasPlaying = this.sources.size > 0;
    this.sources.clear();
    this.leftover = null;
    if (this.context) this.nextStartTime = this.context.currentTime;
    if (wasPlaying) this.onPlaybackChange?.(false);
  }

  async close(): Promise<void> {
    this.flush();
    if (this.context && this.context.state !== "closed") await this.context.close();
    this.context = null;
  }
}
