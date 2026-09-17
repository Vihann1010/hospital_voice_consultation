"use client";

/**
 * Doctor dictation: streams microphone audio to Sarvam STT over a WebSocket
 * and accumulates finalised utterances into one transcript.
 *
 * Reuses the AudioWorklet recorder built for patient intake, so both sides of
 * the platform capture audio through the same tested path.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { staffApi } from "@/lib/staffApi";
import { MicRecorder } from "@/lib/audio/recorder";

export type DictationState = "idle" | "connecting" | "listening" | "error";

export function useDictation() {
  const [state, setState] = useState<DictationState>("idle");
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MicRecorder | null>(null);
  const stoppingRef = useRef(false);

  const cleanup = useCallback(async () => {
    await recorderRef.current?.stop().catch(() => undefined);
    recorderRef.current = null;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: "stop" }));
      } catch {
        /* socket already closing */
      }
    }
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const start = useCallback(async () => {
    if (state === "listening" || state === "connecting") return;
    setError(null);
    setState("connecting");
    stoppingRef.current = false;

    const ws = new WebSocket(staffApi.dictationWsUrl());
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = async () => {
      try {
        const recorder = new MicRecorder(
          (frame) => {
            if (ws.readyState === WebSocket.OPEN) ws.send(frame);
          },
          // Dictation has no assistant speaking over the doctor, so the
          // recorder's barge-in signal is unused here.
          () => undefined
        );
        recorderRef.current = recorder;
        await recorder.start();
        setState("listening");
      } catch {
        setError("Microphone access is needed to dictate. Allow it and try again.");
        setState("error");
        void cleanup();
      }
    };

    ws.onmessage = (event: MessageEvent) => {
      if (typeof event.data !== "string") return;
      let message: Record<string, unknown>;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.type === "transcript" && typeof message.text === "string") {
        setTranscript((current) =>
          current ? `${current.trim()} ${message.text as string}`.trim() : (message.text as string)
        );
      } else if (message.type === "error") {
        setError(String(message.message ?? "Speech recognition failed."));
        setState("error");
      }
    };

    ws.onerror = () => {
      if (!stoppingRef.current) {
        setError("Could not reach the speech service.");
        setState("error");
      }
    };

    ws.onclose = () => {
      if (!stoppingRef.current) setState((current) => (current === "error" ? current : "idle"));
    };
  }, [state, cleanup]);

  const stop = useCallback(async () => {
    stoppingRef.current = true;
    await cleanup();
    setState("idle");
  }, [cleanup]);

  useEffect(() => {
    return () => {
      stoppingRef.current = true;
      void cleanup();
    };
  }, [cleanup]);

  return {
    state,
    transcript,
    error,
    start,
    stop,
    setTranscript,
    reset: () => setTranscript(""),
    listening: state === "listening",
  };
}
