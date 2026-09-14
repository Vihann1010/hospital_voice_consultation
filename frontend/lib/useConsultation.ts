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

export function useConsultation(
  consultationId: string,
  token: string | null,
  initialEntries: TranscriptEntry[] = []
) {
  const [phase, setPhase] = useState<SessionPhase>("connecting");
  const [entries, setEntries] = useState<TranscriptEntry[]>(initialEntries);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<SessionEndedPayload | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MicRecorder | null>(null);
  const playerRef = useRef<PcmPlayer | null>(null);
  const assistantEntryRef = useRef<number | null>(null);
  const speakingRef = useRef(false);
  const endedRef = useRef(false);

  // Which line a reply's words belong to is decided HERE, not inside the
  // state updater. React may run an updater twice (always in development) or
  // later, after "assistant_end" has already cleared the ref. An updater that
  // assigned the ref created the line on its first run and then, on its
  // second, looked for a line that run had never committed — so the whole
  // reply vanished from the screen while the patient heard it and the server
  // saved it. Updaters must only read what they are given.
  const appendAssistantDelta = useCallback((text: string) => {
    const current = assistantEntryRef.current;
    if (current === null) {
      const id = ++entryId;
      assistantEntryRef.current = id;
      setEntries((prev) => [...prev, { id, role: "assistant", text }]);
      return;
    }
    setEntries((prev) =>
      prev.map((entry) => (entry.id === current ? { ...entry, text: entry.text + text } : entry))
    );
  }, []);

  const teardown = useCallback(async () => {
    await recorderRef.current?.stop().catch(() => undefined);
    await playerRef.current?.close().catch(() => undefined);
    recorderRef.current = null;
    playerRef.current = null;
  }, []);

  useEffect(() => {
    if (!token) {
      endedRef.current = true;
      setPhase("ended");
      return;
    }
    endedRef.current = false;
    assistantEntryRef.current = null;
    setEntries(initialEntries);
    setError(null);
    setSummary(null);
    setPhase("connecting");
    const sessionToken = token;
    // Everything below belongs to THIS connection. React mounts effects
    // twice in development, and a discarded socket's late events must not
    // touch the live one — they once raised "connection lost" over a session
    // that was working, and could stop the new session's microphone.
    let disposed = false;
    let opened = false;
    let socket: WebSocket | null = null;
    let ownRecorder: MicRecorder | null = null;
    let ownPlayer: PcmPlayer | null = null;

    const stopOwn = async () => {
      await ownRecorder?.stop().catch(() => undefined);
      await ownPlayer?.close().catch(() => undefined);
      if (recorderRef.current === ownRecorder) recorderRef.current = null;
      if (playerRef.current === ownPlayer) playerRef.current = null;
    };

    async function connect() {
      const player = new PcmPlayer(22050, (playing) => {
        if (disposed) return;
        speakingRef.current = playing;
        if (!endedRef.current) setPhase((p) => (playing ? "speaking" : p === "speaking" ? "listening" : p));
      });
      ownPlayer = player;
      playerRef.current = player;

      const ws = new WebSocket(consultationWsUrl(consultationId, sessionToken));
      ws.binaryType = "arraybuffer";
      socket = ws;
      wsRef.current = ws;

      ws.onopen = async () => {
        if (disposed) {
          ws.close();
          return;
        }
        opened = true;
        try {
          await player.init();
          const recorder = new MicRecorder(
            (frame) => {
              if (!disposed && ws.readyState === WebSocket.OPEN) ws.send(frame);
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
              // by flushing playback.
            }
          );
          ownRecorder = recorder;
          recorderRef.current = recorder;
          await recorder.start();
          if (disposed) {
            await stopOwn();
            return;
          }
          setPhase("listening");
        } catch {
          if (disposed) return;
          setError(
            "Microphone access is required for the voice consultation. Allow the microphone and reload."
          );
          setPhase("error");
        }
      };

      ws.onmessage = (event: MessageEvent) => {
        if (disposed) return;
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
            // A reply that produced no audio (or has finished playing) must
            // not leave the screen saying "Thinking".
            if (!speakingRef.current) setPhase((p) => (p === "thinking" ? "listening" : p));
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

      ws.onclose = (event: CloseEvent) => {
        void stopOwn();
        if (disposed || endedRef.current) return;
        if (event.code === 1008) {
          // Policy close: this intake is no longer live (finished, or
          // abandoned earlier). Nothing is wrong with the connection.
          setPhase("ended");
          return;
        }
        setError(
          opened
            ? "The connection to the hospital dropped. Use Restart to continue this intake."
            : "Could not reach the hospital. Check the network, then reload."
        );
        setPhase("error");
      };
      // Every failure is followed by a close event, which reports it. An
      // error on its own — including the one a socket fires when it is
      // closed while still connecting — is not evidence of anything.
      ws.onerror = () => undefined;
    }

    void connect();
    return () => {
      disposed = true;
      endedRef.current = true;
      socket?.close();
      void stopOwn();
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
