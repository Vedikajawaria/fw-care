# Demo guide

## Current status

The project is prepared for a single-origin container deployment with persistent local SQLite storage. No public demo URL exists yet because this workspace has no configured hosting account or persistent-volume service.

## Walkthrough

1. Sign in as Administrator and review occupancy and synthetic outcome metrics.
2. Open Patients and admit a patient. The record appears in both staff workflows.
3. Sign in as Nurse, open Temperature tasks, and record a measurement. A correction can be recorded with a reason; the original reading remains in history.
4. Sign in as Doctor, open Doctor queue, and record a visit.
5. In Administrator view, submit an intake with missing details. It is retained as `needs_review`; complete the details to admit it.
6. Submit a blank or unsupported knowledge request. It is queued for staff review and no AI-generated answer is used.
7. Record a deceased outcome from the Doctor queue. The admission closes and the bed is released.
8. Review the seeded eligible patient as Doctor. Finalize discharge as Administrator and confirm occupancy decreases.

The eligibility rule uses readings from the prior three completed facility-local dates. Seed patient data is relative to the day the database is first created.
Patients active before today with no accepted reading yesterday or today are flagged as "Missed yesterday".

## Deployment notes

Build the included Docker image on a host that provides a persistent volume. Mount the persistent volume at `/data`, set `DATABASE_URL=sqlite:////data/factwise.db`, a unique secret, and secure cookies. Health check: `/healthz`. The API serves `frontend/dist` from the same origin.

Do not use a host with ephemeral serverless storage for the SQLite database. This prototype is not approved for real patient data.
