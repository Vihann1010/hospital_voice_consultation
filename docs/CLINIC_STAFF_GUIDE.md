# CN Gastrocare & Smile Dental — Staff Guide

How to run a day on this system, for the three people who run it: the front
desk, the doctor, and whoever assists in the endoscopy suite. Keep a copy at
the counter and one in the suite.

This is the short guide for a clinic with no wards and no laboratory of its
own. `docs/STAFF_GUIDE.md` is the full hospital version; where the two differ,
this one is right for here.

> **The system supports your work; it does not decide for you.** Anything
> marked as AI — the intake summary, red flags, suggested diagnoses and tests —
> is a suggestion. The doctor makes every clinical decision.

---

## 1. Signing in

Open the clinic address given to you (for example
`http://<clinic-server>:3000/login`) and sign in with your own email and
password. **Never share a login**: every action is recorded against the person
signed in, and a shared login makes that record meaningless.

| Role | Opens on | Used for |
|---|---|---|
| Reception | **Reception terminal** | registration, billing, payments, appointments |
| Doctor | **Clinical dashboard** | consultations, Visit Pad, prescriptions, procedures |
| Manager, Admin | **Clinical dashboard** | money, reports, settings, staff accounts |

There is no ward terminal and no laboratory terminal here — this clinic has
neither, so those screens are switched off rather than sitting empty.

What each role may and may not do is in `docs/ROLES.txt`. If a button says
"Requires permission", ask the administrator. Do not borrow somebody's login.

---

## 2. The front desk

### Registering a patient

1. **Find them first.** Search by phone number or name before creating anyone
   new. A patient with two files has half a history in each.
2. New patient: name, age, gender, phone. The department is already set — this
   clinic has one.
3. The counter prints a token and opens a visit.

### Billing

Bill the visit at the counter as usual: consultation, and anything else the
patient is having today. A returning patient inside the consultant's
free-follow-up window is not charged again for the consultation — the counter
applies that itself, and the line says why it came out free.

**Procedures bill themselves.** When the doctor finishes an endoscopy, a bill
for it appears against that patient's visit. You take the money and give the
receipt exactly as for anything else. You do not raise it by hand, and you must
not raise a second one.

If a bill is wrong, **correct it** — never delete it. Bills are cancelled or
amended, always with a reason, and the reason is part of the record.

### Booking a procedure

Procedures are booked from the Procedures screen against the patient's visit,
not against an admission — nobody is admitted here. Tell the patient, in
writing if you can:

- **Nothing to eat for six hours** before an upper endoscopy; clear fluids up
  to two hours before, unless the doctor says otherwise.
- **Bowel preparation** the evening before a colonoscopy, as prescribed.
- **Somebody must come with them** if they are having sedation, and that person
  must be able to take them home. A patient who arrives alone for a sedated
  procedure may have to be sent away — say so when booking, not on the day.
- **Blood thinners and diabetes medicines**: the doctor decides what is stopped
  and when. Ask at booking; do not advise it yourself.

---

## 3. The doctor

### The consultation

The patient's voice intake, if they did one, is already at the top of the Visit
Pad as **History from intake**. Read it, then see the patient — it is a
starting point, not a history you took.

The gastroenterology pad has a **GI review** block: appetite, weight change,
bowel habit, bleeding. Fill it every visit even when nothing has changed. It is
what the next visit is compared against, and a change in any of the four is
usually the reason to scope.

**Previous endoscopy** carries forward from visit to visit. What the last scope
showed is the context for everything after it.

**Red flags** are shown but not acted on for you. The screen flags
haematemesis, melaena, obstruction, jaundice and progressive dysphagia; what
happens next is yours to decide.

### Prescribing

Type any medicine by name. If the medicine list looks short, the screen will
say why: this clinic's formulary is drafted and withheld until a
gastroenterologist has reviewed it. That does not stop you prescribing anything
— it only means the system is not suggesting a list nobody has signed off.

**Interaction warnings work regardless.** If you prescribe clarithromycin to a
patient already on a statin, you will be told, and you should be: that is a
fourteen-day course and the harm arrives after the patient has gone home.

### The procedure

1. **The checklist comes first.** A case cannot be wheeled in until the
   day-procedure checklist is signed: identity, consent, fasting. It also asks
   about sedation consent, blood thinners, diabetes medicines, bowel prep, and
   whether somebody is here to take the patient home. Tick only what is true.
2. Record **wheeled in** and **wheeled out**. There is no incision to record
   for a scope; the two times are enough and the case completes on wheel-out.
3. Write the **endoscopy report**: how far the scope reached, how the patient
   tolerated it, what you found, and what you did about it.
4. If you took a biopsy, tick **biopsy taken**. Signing the report then raises
   the histopathology order by itself, so the specimen leaves the building with
   something in the system waiting for it. Do not also order it by hand.
5. Photographs attach to the patient's record as clinical photographs.

The bill for the procedure is raised when the case completes. The patient pays
at the counter.

---

## 4. In the suite

The assistant's job on this system is the checklist and the times.

- Open the day-procedure checklist as the patient arrives, not after.
- **Identity, consent and fasting are required.** If one of them is not true,
  the case does not start — tell the doctor rather than ticking the box.
- **Bowel preparation: inadequate** is worth saying out loud. A colonoscopy
  through poor preparation is a repeat colonoscopy.
- **No escort** for a sedated patient is a reason to stop and ask.
- Record the times as they happen, not from memory afterwards. They are the
  record of what happened to a patient under sedation.

---

## 5. Smile Dental

The dental practice shares the front desk, the patient records and the
voice intake. What differs:

- **Smile Dental and CN Gastrocare are separate businesses.** Each has its own
  patients: a Smile Dental ID starts `SMD`, a CN Gastrocare one `CNG`, and so
  do their bills. Someone who sees both doctors is registered twice, once
  with each. If you pick a CN Gastrocare patient for a dental visit, the
  counter says so and offers **Register with Smile Dental**, which copies
  their details into a new registration.
- **At the counter,** choose *Dentistry* as the department. The bill and the
  receipt then say Smile Dental; a gastro visit's say CN Gastrocare.
- **Booking a dental procedure,** choose the patient's visit from today's
  list. The booking asks for the **teeth** in FDI numbers — `36`, `11, 21`,
  `55` for a milk tooth — or *Full mouth*, *Upper arch*, *Lower arch*. It
  refuses a number that is not a tooth. Read it back to the patient.
- **In the chair,** the dental checklist comes first: identity, consent,
  and the **tooth confirmed with the patient and on the X-ray**. All three
  are required; there is no fasting question.
- **The procedure bills itself** when the patient leaves the chair. A price
  marked *per tooth* is charged for each tooth booked: two extractions,
  two charges.
- **The tooth chart** on the dental Visit Pad lists each finding's teeth
  (decayed, missing, filled, root-canal treated, crowned…). It is carried to
  the next visit, because it describes the mouth, not the day. So is the
  **treatment plan**: book each sitting of a root canal or crown as its own
  procedure, and tick it off.
- **Prescribing:** the dental medicine list is withheld until the dentist has
  reviewed it, exactly as the gastro one is. General antibiotics and pain
  relief are available meanwhile.

### Two intake tablets

The voice intake runs on two tablets at once, one per practice. Sign each in
with its own nurse login and choose its queue once — **CN Gastrocare** on one,
**Smile Dental** on the other. The tablet remembers the choice through a
reload or a sign-out. Two patients can be interviewed at the same time, and
both doctors' screens can be open at the same time; each doctor sees only
their own practice's patients.

## 6. Reports that come back later

Histopathology goes to an outside laboratory and comes back in about a week.
When the report arrives:

1. Open the patient, find the investigation order raised at the procedure.
2. Upload the report against it. It is read and filed against that order, and
   the doctor sees it on the patient's record.

Reports a patient brings in from anywhere else go in the same place — **Reports
brought** on the consultation screen.

---

## 7. Rules everyone follows

- **Never share your login.** Everything is recorded against whoever is signed in.
- **Nothing is deleted.** Bills, receipts and documents are cancelled, reversed
  or amended, always with a reason.
- **Signed means final.** Correct a signed document by amending it, which keeps
  both versions.
- **Money screens need the finance PIN.** Do not write it near the counter.
- **If the system refuses something, read the message.** It says what to do first.

---

## 8. When something goes wrong

1. Read the message on screen. Most refusals explain themselves — a missing
   field, a step to do first, a permission you do not hold.
2. If the message ends with **(reference …)**, write that reference down. It
   lets the technical team find exactly what happened.
3. Tell the IT person: your name, the patient's UHID, the screen, what you
   pressed, the time, and the reference if there was one.
4. If the system is unavailable, use the agreed **paper forms** and enter the
   records once it is back. A procedure done on paper still needs its checklist
   signed on paper.
