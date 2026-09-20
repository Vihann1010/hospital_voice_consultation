"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { startConsultation, DEPARTMENTS, type Department, type Gender } from "@/lib/api";
import { DEPARTMENT_LABEL } from "@/lib/format";

/** One line telling a patient what the department is for, in their words. */
const DEPARTMENT_BLURB: Record<string, string> = {
  orthopedics: "Bones, joints, back pain, injuries",
  gynecology: "Women's health, pregnancy care, cycles",
  gastroenterology: "Stomach, digestion, liver, acidity",
};

/** The departments a patient can walk in and pick from.
 *
 * The doctor's name used to be printed on each card. It was hardcoded, so it
 * was wrong the moment a consultant changed and wrong from the start at a
 * clinic that never employed them — and this screen is unauthenticated, so it
 * cannot read the consultant register. The department and what it covers is
 * what the patient actually needs to choose correctly. */
const DEPARTMENT_CHOICES: { value: Department; label: string; blurb: string }[] =
  DEPARTMENTS.map((value) => ({
    value,
    label: DEPARTMENT_LABEL[value] ?? value,
    blurb: DEPARTMENT_BLURB[value] ?? "",
  }));

const GENDERS: { value: Gender; label: string }[] = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "other", label: "Other" },
];

export default function IntakePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<Gender | "">("");
  const [phone, setPhone] = useState("");
  const [department, setDepartment] = useState<Department | "">("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const ageNumber = Number(age);
    if (!name.trim() || name.trim().length < 2) return setError("Please enter the patient's full name.");
    if (!Number.isFinite(ageNumber) || ageNumber < 0 || ageNumber > 120)
      return setError("Please enter a valid age between 0 and 120.");
    if (!gender) return setError("Please select a gender.");
    if (phone.replace(/\D/g, "").length < 8) return setError("Please enter a valid phone number.");
    if (!department) return setError("Please choose a department for this visit.");

    setSubmitting(true);
    try {
      const session = await startConsultation({
        patient: { name: name.trim(), age: ageNumber, gender, phone_number: phone.trim() },
        department,
      });
      sessionStorage.setItem(`consult:${session.consultation_id}`, session.session_token);
      router.push(`/consultation/${session.consultation_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the consultation. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="grid gap-10 lg:grid-cols-[1.1fr_1fr] lg:items-start">
      <section>
        <p className="mb-3 inline-block rounded-full bg-pine/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-pine">
          Before you see the doctor
        </p>
        <h1 className="font-display text-4xl font-semibold leading-[1.08] text-pine sm:text-5xl">
          Tell us what brings you in — in your own words, in your own language.
        </h1>
        <p className="mt-4 max-w-md text-[15px] leading-relaxed text-ink-muted">
          Our voice assistant will talk with you for a few minutes, note your symptoms and
          history, and hand a ready summary to your doctor. Speak in Hindi, English, or a mix —
          it follows you.
        </p>
        <dl className="mt-8 space-y-4 border-l-2 border-marigold pl-5">
          <div>
            <dt className="text-sm font-semibold text-ink">Just talk naturally</dt>
            <dd className="text-sm text-ink-muted">No forms after this one. It listens and asks.</dd>
          </div>
          <div>
            <dt className="text-sm font-semibold text-ink">Interrupt any time</dt>
            <dd className="text-sm text-ink-muted">Start speaking and the assistant stops for you.</dd>
          </div>
          <div>
            <dt className="text-sm font-semibold text-ink">Goes straight to your doctor</dt>
            <dd className="text-sm text-ink-muted">Your answers reach the consultation room before you do.</dd>
          </div>
        </dl>
      </section>

      <form
        onSubmit={onSubmit}
        className="rounded-2xl border border-pine/10 bg-mint-card p-6 shadow-[0_2px_16px_rgba(14,59,52,0.06)] sm:p-7"
        noValidate
      >
        <h2 className="font-display text-xl font-semibold text-pine">Patient details</h2>

        <div className="mt-5 space-y-4">
          <div>
            <label htmlFor="name" className="field-label">Full name</label>
            <input
              id="name"
              className="field-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Sunita Verma"
              autoComplete="name"
              maxLength={255}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="age" className="field-label">Age</label>
              <input
                id="age"
                className="field-input"
                value={age}
                onChange={(e) => setAge(e.target.value.replace(/[^\d]/g, ""))}
                inputMode="numeric"
                placeholder="Years"
                maxLength={3}
              />
            </div>
            <div>
              <label htmlFor="gender" className="field-label">Gender</label>
              <select
                id="gender"
                className="field-input"
                value={gender}
                onChange={(e) => setGender(e.target.value as Gender)}
              >
                <option value="" disabled>Select</option>
                {GENDERS.map((g) => (
                  <option key={g.value} value={g.value}>{g.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="phone" className="field-label">Phone number</label>
            <input
              id="phone"
              className="field-input"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              inputMode="tel"
              autoComplete="tel"
              placeholder="+91 98xxxxxxx"
              maxLength={20}
            />
          </div>

          <fieldset>
            <legend className="field-label">Department</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {DEPARTMENT_CHOICES.map((d) => {
                const selected = department === d.value;
                return (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() => setDepartment(d.value)}
                    aria-pressed={selected}
                    className={`rounded-xl border p-3.5 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-pine/40 ${
                      selected
                        ? "border-pine bg-pine text-mint shadow-sm"
                        : "border-ink-faint/40 bg-white hover:border-pine/50"
                    }`}
                  >
                    <span className="block font-display text-[15px] font-semibold">
                      {d.label}
                    </span>
                    <span className={`mt-1 block text-xs ${selected ? "text-mint/70" : "text-ink-faint"}`}>
                      {d.blurb}
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>
        </div>

        {error && (
          <p role="alert" className="mt-4 rounded-lg border border-clay/30 bg-clay/5 px-3 py-2 text-sm text-clay">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="mt-6 w-full rounded-xl bg-marigold px-5 py-3.5 font-display text-base font-semibold text-pine-deep transition hover:bg-marigold-deep disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Preparing your consultation…" : "Start consultation"}
        </button>
        <p className="mt-3 text-center text-xs text-ink-faint">
          Uses your microphone. Your browser will ask for permission.
        </p>
      </form>
    </div>
  );
}
