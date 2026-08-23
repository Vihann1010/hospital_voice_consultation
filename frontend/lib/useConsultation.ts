"use client";

/**
 * useConsultation — owns the whole realtime session on the client:
 * WebSocket, mic capture, playback queue, transcript state, and barge-in.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL, consultationWsUrl } from "@/lib/api";
import { MicRecorder } from "@/lib/audio/recorder";
import { PcmPlayer } from "@/lib/audio/player";

export type SessionPhase =
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "ended"
  | "error";

export interface TranscriptEntry {
  id: number;
  role: "patient" | "assistant";
  text: string;
  interrupted?: boolean;
}

interface RestartResponse {
  consultation_id: string;
  session_token: string;
}

interface SessionEndedPayload {
  medical_json: Record<string, unknown> | null;
  transcript: string | null;
}

let entryId = 0;

export function useConsultation(consultationId: string, token: string) {
  const [phase, setPhase] = useState<SessionPhase>("connecting");
  const [entries, setEntries] = useState<TranscriptEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<SessionEndedPayload | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MicRecorder | null>(null);
  const playerRef = useRef<PcmPlayer | null>(null);
  const assistantEntryRef = useRef<number | null>(null);
  const speakingRef = useRef(false);
  const endedRef = useRef(false);

  const appendAssistantDelta = useCallback((text: string) => {
    setEntries((prev) => {
      if (assistantEntryRef.current === null) {
        const id = ++entryId;
        assistantEntryRef.current = id;
        return [...prev, { id, role: "assistant", text }];
      }
      return prev.map((entry) =>
        entry.id === assistantEntryRef.current ? { ...entry, text: entry.text + text } : entry
      );
    });
  }, []);

  const teardown = useCallback(async () => {
    await recorderRef.current?.stop().catch(() => undefined);
    await playerRef.current?.close().catch(() => undefined);
    recorderRef.current = null;
    playerRef.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function connect() {
      const player = new PcmPlayer(22050, (playing) => {
        speakingRef.current = playing;
        if (!endedRef.current) setPhase((p) => (playing ? "speaking" : p === "speaking" ? "listening" : p));
      });
      playerRef.current = player;

      const ws = new WebSocket(consultationWsUrl(consultationId, token));
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = async () => {
        try {
          await player.init();
          const recorder = new MicRecorder(
            (frame) => {
              if (ws.readyState === WebSocket.OPEN) ws.send(frame);
            },
            () => {
              // Barge-in is driven entirely by Sarvam's server-side VAD.
              //
              // The worklet's local energy VAD fires on any sound above a
              // threshold — a cough, a chair scrape, someone talking in the
              // corridor — which cut the assistant off mid-sentence far too
              // readily in a real consulting room.
              //
              // Instead the server cancels the in-flight reply when Sarvam
              // emits an actual recognised utterance during playback, and
              // sends {"type":"interrupted"}, which this hook already handles
              // by flushing playback. Interruption is marginally slower
              // (it waits for Sarvam to finalise the utterance) but only ever
              // triggers on real speech.
              //
              // To restore instant local barge-in, reinstate:
              //   if (speakingRef.current && ws.readyState === WebSocket.OPEN) {
              //     player.flush();
              //     ws.send(JSON.stringify({ type: "interrupt" }));
              //   }
            }
          );
          recorderRef.current = recorder;
          await recorder.start();
          if (!cancelled) setPhase("listening");
        } catch {
          setError(
            "Microphone access is required for the voice consultation. Allow the microphone and reload."
          );
          setPhase("error");
        }
      };

      ws.onmessage = (event: MessageEvent) => {
        if (event.data instanceof ArrayBuffer) {
          player.enqueue(event.data);
          return;
        }
        let message: Record<string, unknown>;
        try {
          message = JSON.parse(event.data as string);
        } catch {
          return;
        }
        switch (message.type) {
          case "session_ready":
            if (typeof message.tts_sample_rate === "number") {
              player.setSampleRate(message.tts_sample_rate);
            }
            break;
          case "final_transcript":
            setEntries((prev) => [
              ...prev,
              { id: ++entryId, role: "patient", text: String(message.text ?? "") },
            ]);
            break;
          case "assistant_start":
            assistantEntryRef.current = null;
            setPhase("thinking");
            break;
          case "assistant_delta":
            appendAssistantDelta(String(message.text ?? ""));
            break;
          case "assistant_end":
            if (message.interrupted && assistantEntryRef.current !== null) {
              const targetId = assistantEntryRef.current;
              setEntries((prev) =>
                prev.map((entry) =>
                  entry.id === targetId ? { ...entry, interrupted: true } : entry
                )
              );
            }
            assistantEntryRef.current = null;
            break;
          case "interrupted":
            player.flush();
            setPhase("listening");
            break;
          case "medical_json":
            break; // stored server-side; surfaced to staff dashboards in a later phase
          case "session_ended":
            endedRef.current = true;
            setSummary({
              medical_json: (message.medical_json as Record<string, unknown>) ?? null,
              transcript: (message.transcript as string) ?? null,
            });
            setPhase("ended");
            break;
          case "error":
            setError(String(message.message ?? "Something went wrong."));
            break;
        }
      };

      ws.onclose = () => {
        void teardown();
        if (!endedRef.current) {
          setPhase((p) => (p === "ended" || p === "error" ? p : "ended"));
        }
      };
      ws.onerror = () => {
        if (!endedRef.current) {
          setError("Connection to the hospital was lost. Please reload to reconnect.");
          setPhase("error");
        }
      };
    }

    void connect();
    return () => {
      cancelled = true;
      endedRef.current = true;
      wsRef.current?.close();
      void teardown();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [consultationId, token]);

  const endConsultation = useCallback(async () => {
    endedRef.current = true;
    playerRef.current?.flush();
    await recorderRef.current?.stop().catch(() => undefined);
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "end" }));
      // Server replies with session_ended, then closes.
    } else {
      setPhase("ended");
    }
  }, []);

  const restartConsultation = useCallback(async (): Promise<RestartResponse | null> => {
    try {
      const response = await fetch(`${API_URL}/api/v1/consultations/${consultationId}/restart`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_token: token }),
      });
      if (!response.ok) throw new Error("Could not restart the consultation.");
      endedRef.current = true;
      wsRef.current?.close();
      await teardown();
      return (await response.json()) as RestartResponse;
    } catch {
      setError("Could not restart the consultation. Please reload and try again.");
      return null;
    }
  }, [consultationId, token, teardown]);

  return { phase, entries, error, summary, endConsultation, restartConsultation };
}
