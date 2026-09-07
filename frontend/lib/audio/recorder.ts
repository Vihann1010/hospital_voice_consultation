/** Microphone capture: AudioWorklet -> 16 kHz PCM16 frames + voice-onset events. */
export class MicRecorder {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;

  constructor(
    private onFrame: (pcm16: ArrayBuffer) => void,
    private onVoiceStart: () => void
  ) {}

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    this.context = new AudioContext();
    await this.context.audioWorklet.addModule("/worklets/pcm-recorder.js");
    const source = this.context.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.context, "pcm-recorder");
    this.node.port.onmessage = (event: MessageEvent) => {
      if (event.data?.type === "frame") this.onFrame(event.data.buffer as ArrayBuffer);
      else if (event.data?.type === "voice_start") this.onVoiceStart();
    };
    source.connect(this.node);
    // Keep the graph alive without echoing the mic to speakers.
    const sink = this.context.createGain();
    sink.gain.value = 0;
    this.node.connect(sink);
    sink.connect(this.context.destination);
    if (this.context.state === "suspended") await this.context.resume();
  }

  async stop(): Promise<void> {
    this.node?.port.close();
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    if (this.context && this.context.state !== "closed") await this.context.close();
    this.node = null;
    this.stream = null;
    this.context = null;
  }
}
