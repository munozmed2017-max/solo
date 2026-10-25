# Solo — product spec

**Name:** Solo
**Tagline:** "Practice solo. Never alone."

A solo physician runs their own telemedicine practice; Gemini agents do
the back office.

## Screens (tabs across the top)

1. **Practice setup** — practice name, hours, visit fee, booking link with
   a QR code.
2. **Booking page (public)** — name, date of birth, reason for visit,
   symptom questions, file upload. Banner: "Use made-up information
   only."
3. **Visits** — list of booked visits. Visit screen: intake summary and
   records on the left; transcript box, physician plan box, and Approve
   button on the right. After Approve: scribe note, prescription (labeled
   SIMULATED FAX), and patient summary email, each showing its verifier
   rounds.
4. **Approval queue** — every document waiting, with Approve, Edit,
   Reject. Nothing sends without an approval record, enforced in code.
5. **Activity log** — side panel listing every agent action with time.
6. **Agent builder** — the physician asks for a tool (e.g. "find all my
   patients with diabetes and track their visits and A1c"). gemini-4-argon
   (Antigravity managed agent if possible) writes the code and tests, runs
   them on a synthetic panel of 2,500 patients, fixes failures, and the
   tool appears under My tools with tests passed and its count checked
   against the panel's true count.
7. **Results** — 20 synthetic cases run three ways (Flash baseline, Argon
   agents, Argon agents with verifier) with coverage, errors, and errors
   caught.

## Verifier

Independent gemini-4-argon call. Failed sentences go back to the writing
agent for rewrite, up to 3 rounds. All rounds are logged.

**Demo switch `DEMO_PLANTED_ERROR`** inserts "Potassium is elevated at
5.4." into Margaret's first note draft so the verifier rejects it.

## Demo patients (all synthetic)

**Margaret Smith**, 87, heart failure with reduced ejection fraction:
- Meds: carvedilol 6.25 mg twice daily, furosemide 40 mg daily,
  spironolactone 25 mg daily, sacubitril/valsartan 24/26 mg twice daily
- Labs 2026-09-12 normal (potassium 4.3); older labs 2025-08-20 potassium
  5.4
- Weight 70–72 kg, SpO2 98%, walks about 3 miles a day
- Context: ran out of medications, primary doctor away, urgent care 2
  hours away
- No shortness of breath, cough, weight gain, or orthopnea
- Physician gives a bridge refill and tells her to see her primary doctor

**Jhonatan**: allergy panel 2026-10-24 strongly positive for cat dander.

## Build order

Build in this order, showing a result after each step:

1. Margaret's full visit flow with the verifier loop
2. Agent builder
3. Results batch
4. Practice setup and booking page

Don't polish styling until the above is working.
