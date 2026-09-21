"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useConsultation, type SessionPhase } from "@/lib/hooks/useConsultation";
import { PreviousReportsUpload } from "@/components/patient/previous-reports-upload";

const PHASE_COPY: Record<SessionPhase, { title: string; hint: string }> = {
  connecting: { title: "Connecting…", hint: "Setting up your voice line." },
  listening: { title: "Listening", hint: "Speak whenever you're ready. Take your time." },
  thinking: { title: "One moment", hint: "The assistant is noting what you said." },
  speaking: { title: "Assistant speaking", hint: "Start talking any time — it will stop for you." },
  ended: { title: "Consultation saved", hint: "Your doctor has everything they need." },
  error: { title: "Something went wrong", hint: "" },
};

function VoiceOrb({ phase }: { phase: SessionPhase }) {
  const active = phase === "speaking";
  const listening = phase === "listening";
  return (
    <div className="relative flex h-40 w-40 items-center justify-center" aria-hidden="true">
      {active && (
        <>
          <span className="absolute h-28 w-28 rounded-full border-2 border-marigold/60 animate-pulseRing" />
          <span
            className="absolute h-28 w-28 rounded-full border-2 border-marigold/40 animate-pulseRing"
            style={{ animationDelay: "0.6s" }}
          />
        </>
      )}
      <div
        className={`flex h-28 w-28 items-center justify-center rounded-full transition-colors duration-500 ${
          active
            ? "bg-marigold animate-breathe"
            : listening
              ? "bg-pine animate-breathe"
              : phase === "ended"
                ? "bg-pine-soft"
                : "bg-ink-faint"
        }`}
      >
        <svg viewBox="0 0 24 24" className={`h-10 w-10 ${active ? "text-pine-deep" : "text-mint"}`} fill="none">
          {active ? (
            <path d="M4 12c1.5-4 3-4 4.5 0s3 4 4.5 0 3-4 4.5 0 2 3 2.5 0" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          ) : (
            <>
              <rect x="9" y="3.5" width="6" height="11" rx="3" stroke="currentColor" strokeWidth="1.8" />
              <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v2.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </>
          )}
        </svg>
      </div>
    </div>
  );
}

export default function ConsultationPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const consultationId = params.id;
  const [token, setToken] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    setToken(sessionStorage.getItem(`consult:${consultationId}`));
  }, [consultationId]);

  if (token === undefined) {
    return <p className="py-20 text-center text-sm text-ink-muted">Loading…</p>;
  }
  if (token === null) {
    return (
      <div className="mx-auto max-w-md py-16 text-center">
        <h1 className="font-display text-2xl font-semibold text-pine">Session not found</h1>
        <p className="mt-2 text-sm text-ink-muted">
          This consultation link has expired or was opened in a different browser.
        </p>
        <button
          onClick={() => router.push("/")}
          className="mt-6 rounded-xl bg-pine px-5 py-3 font-display text-sm font-semibold text-mint"
        >
          Register again
        </button>
      </div>
    );
  }
  return <LiveSession consultationId={consultationId} token={token} />;
}

function LiveSession({ consultationId, token }: { consultationId: string; token: string }) {
  const router = useRouter();
  const { phase, entries, error, summary, endConsultation, restartConsultation } = useConsultation(consultationId, token);
  const [ending, setEnding] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Whether the view was following the conversation when the last line
  // arrived. If the patient has scrolled up to re-read something, new lines
  // must not yank them back down mid-sentence.
  const followingRef = useRef(true);

  function handleScroll() {
    const element = scrollRef.current;
    if (!element) return;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    followingRef.current = distanceFromBottom < 80;
  }

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || !followingRef.current) return;
    // The assistant's reply streams in word by word, so this runs often.
    // Smooth scrolling would queue animations faster than they finish and
    // visibly lag behind the text; an instant jump tracks it exactly.
    element.scrollTop = element.scrollHeight;
  }, [entries]);

  const copy = PHASE_COPY[phase];

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,380px)_1fr]">
      <section className="flex flex-col items-center rounded-2xl border border-pine/10 bg-mint-card px-6 py-10 text-center">
        <VoiceOrb phase={phase} />
        <h1 className="mt-6 font-display text-2xl font-semibold text-pine" aria-live="polite">
          {copy.title}
        </h1>
        <p className="mt-1.5 max-w-[26ch] text-sm text-ink-muted">{error ?? copy.hint}</p>

        {phase !== "ended" && phase !== "error" && (
          <button
            onClick={async () => {
              setEnding(true);
              await endConsultation();
            }}
            disabled={ending}
            className="mt-8 rounded-xl border border-clay/40 px-5 py-2.5 text-sm font-semibold text-clay transition hover:bg-clay hover:text-white disabled:opacity-60"
          >
            {ending ? "Saving…" : "End consultation"}
          </button>
        )}

        {phase === "ended" && (
          <div className="mt-8 w-full">
            <div className="rounded-xl bg-pine px-4 py-4 text-left text-mint">
              <p className="font-display text-sm font-semibold">What happens next</p>
              <p className="mt-1 text-sm text-mint/85">
                Your summary is with the front desk. Please wait to be called — your doctor will
                already know your history.
              </p>
            </div>
            <button
              onClick={() => router.push("/intake")}
              className="mt-4 w-full rounded-xl bg-marigold px-5 py-3 font-display text-sm font-semibold text-pine-deep hover:bg-marigold-deep"
            >
              Back to intake
            </button>
          </div>
        )}
        {phase === "error" && (
          <button
            onClick={() => window.location.reload()}
            className="mt-8 rounded-xl bg-pine px-5 py-2.5 font-display text-sm font-semibold text-mint"
          >
            Reload and reconnect
          </button>
        )}
        {phase !== "ended" && (
          <button
            onClick={async () => {
              setRestarting(true);
              const replacement = await restartConsultation();
              if (!replacement) {
                setRestarting(false);
                return;
              }
              sessionStorage.setItem(`consult:${replacement.consultation_id}`, replacement.session_token);
              router.replace(`/consultation/${replacement.consultation_id}`);
            }}
            disabled={restarting}
            className="mt-3 rounded-xl border border-pine/30 px-5 py-2.5 text-sm font-semibold text-pine transition hover:bg-mint disabled:opacity-60"
          >
            {restarting ? "Restarting..." : "Restart consultation"}
          </button>
        )}
      </section>

      {phase === "ended" ? (
        <PreviousReportsUpload sessionToken={token} />
      ) : (
      <section className="flex h-[clamp(320px,60vh,620px)] flex-col overflow-hidden rounded-2xl border border-pine/10 bg-white">
        <div className="border-b border-pine/10 px-5 py-3.5">
          <h2 className="font-display text-sm font-semibold uppercase tracking-[0.14em] text-ink-muted">
            Live transcript
          </h2>
        </div>
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="thin-scroll min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5"
          role="log"
          aria-live="polite"
        >
          {entries.length === 0 && (
            <p className="py-10 text-center text-sm text-ink-faint">
              The conversation will appear here as you speak.
            </p>
          )}
          {entries.map((entry) => (
            <div key={entry.id} className={entry.role === "patient" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed ${
                  entry.role === "patient"
                    ? "rounded-br-md bg-pine text-mint"
                    : "rounded-bl-md bg-mint text-ink"
                }`}
              >
                {entry.text}
                {entry.interrupted && (
                  <span className="mt-1 block text-[11px] italic opacity-70">— you interrupted, no problem</span>
                )}
              </div>
            </div>
          ))}
        </div>
        {summary?.transcript && (
          <details className="border-t border-pine/10 px-5 py-3 text-sm text-ink-muted">
            <summary className="cursor-pointer font-semibold text-pine">Full saved transcript</summary>
            <pre className="mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap font-sans text-[13px] leading-relaxed">
              {summary.transcript}
            </pre>
          </details>
        )}
      </section>
      )}
    </div>
  );
}
