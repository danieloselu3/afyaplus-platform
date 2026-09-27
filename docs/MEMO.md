# Memo: AfyaPlus Service Platform v1.1.0 — pilot readiness

**To:** CTO, AfyaPlus · **Re:** go / no-go for a supervised pilot · **Date:** 27 September 2026

**Recommendation: GO for a supervised pilot in the four current counties, on four conditions (below).**

## What was built
Olu's laptop scripts are now three services that anyone on the team can run with one command:
- **Triage API.** The mobile app sends a patient message and gets back an urgency level and one safe next step from gpt-4o-mini. Only logged-in coordinators can use it.
- **Logistics tool server (MCP).** Three read-only tools over the clinic data: stock check, delivery route, and delivery time estimate.
- **Logistics assistant.** An AI agent that answers questions like *"which clinics need amoxicillin, and what route should the driver take?"* by calling those tools. It sits behind the same login as triage.

Both services ship as versioned containers. Every answer carries a trace id, so one search shows what was asked, which data was used and what it cost. Running the whole build and all its tests cost under $0.01 in model fees.

## Highest-value component: the logistics assistant, because of its guardrails
The assistant answers a stock-plus-route question in about 5 seconds, a job that today means cross-checking a spreadsheet and a map by hand (the pilot will measure the time saved). What makes it deployable in a health setting is its limits, not its intelligence:
- It answers only from tool data, and says so when data is missing: *"I do not have access to pricing information."*
- It can **recommend** a reorder, but nothing moves until a coordinator presses confirm. A double-click or network retry cannot order twice.
- Viewers get stock look-ups only. Every step is traceable after the fact.

## Main risk: confident, well-formatted wrong answers
In testing, the assistant once told us *"No clinics need an amoxicillin reorder"* when two did. It had quietly checked only the 2 Kisumu clinics. Every tool worked; the model misread the scope of the question. We fixed it: the tools now state how many clinics a result covers, and the assistant may not generalise from a subset. It is the kind of error a busy coordinator would not catch.

**Mitigation:**
- The assistant stays advisory, and all orders go through human confirmation.
- A fixed test set of 20 real coordinator questions runs before every release. Any wrong stock claim blocks the release.
- Coordinators can report a bad answer by quoting its trace id. We review a sample of traces weekly.

## Conditions for go
1. **Keep the pilot at one agent server** until reorder proposals move from memory into a database. They are lost on restart and cannot be shared across copies. Estimate: 2–3 days of work.
2. **Build the 20-question regression set with Mercy's team** before launch, and make it a release gate.
3. **Clinical sign-off on the triage wording.** Red-flag symptoms are already forced to "high" in code, but a clinician must review the advice style.
4. **Operational basics:** secrets held in a secrets manager, HTTPS in front of both services, and an OpenAI budget alert at $20 a month. Expected pilot spend is well below $5 a month.

**Revisit in 6 weeks** with the regression pass rate, the trace-review findings and coordinator time saved.
