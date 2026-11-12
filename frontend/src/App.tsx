import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { api, apiUrl, jsonBody, setCsrfToken, type Role, type User } from "./api";
import type {
  AssistantRequest,
  Dashboard,
  Eligibility,
  IntakeRequest,
  Patient,
  PatientDetail,
} from "./types";

type Screen = "dashboard" | "patients" | "tasks" | "visits" | "discharge" | "intake" | "assistant" | "settings";
type Message = { kind: "success" | "error" | "info"; text: string };

const roleTitles: Record<Role, string> = { admin: "Administrator", nurse: "Nurse", doctor: "Doctor" };
const navByRole: Record<Role, Array<[Screen, string]>> = {
  admin: [
    ["dashboard", "Overview"],
    ["patients", "Patients"],
    ["intake", "Intake review"],
    ["discharge", "Discharge"],
    ["assistant", "Knowledge requests"],
    ["settings", "Facility rules"],
  ],
  nurse: [
    ["dashboard", "Overview"],
    ["tasks", "Temperature tasks"],
    ["patients", "Patients"],
    ["intake", "Intake requests"],
    ["assistant", "Knowledge requests"],
  ],
  doctor: [
    ["dashboard", "Overview"],
    ["visits", "Doctor queue"],
    ["patients", "Patients"],
    ["discharge", "Discharge review"],
    ["assistant", "Knowledge requests"],
  ],
};

function messageText(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

function formatTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "Not recorded";
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [screen, setScreen] = useState<Screen>("dashboard");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);
  const [dataVersion, setDataVersion] = useState(0);
  const [detail, setDetail] = useState<PatientDetail | null>(null);
  const [assistantReply, setAssistantReply] = useState("");

  const refresh = useCallback(() => setDataVersion((value) => value + 1), []);
  const reportError = useCallback((error: unknown) => setMessage({ kind: "error", text: messageText(error) }), []);

  useEffect(() => {
    let alive = true;
    api<{ user: User | null; csrf_token: string | null }>("/api/v1/auth/me")
      .then((result) => {
        if (!alive) return;
        if (result.user && result.csrf_token) {
          setUser(result.user);
          setCsrfToken(result.csrf_token);
        }
      })
      .catch((error: unknown) => {
        if (alive) setMessage({ kind: "error", text: messageText(error) });
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const handleLogin = async (username: string) => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api<{ user: User; csrf_token: string }>("/api/v1/auth/login", {
        method: "POST",
        body: jsonBody({ username, password: "Demo123!" }),
      });
      setCsrfToken(result.csrf_token);
      setUser(result.user);
      setScreen("dashboard");
      refresh();
    } catch (error) {
      reportError(error);
    } finally {
      setBusy(false);
    }
  };

  const handleLogout = async () => {
    try {
      await api("/api/v1/auth/logout", { method: "POST" });
      setUser(null);
      setCsrfToken("");
      setDetail(null);
    } catch (error) {
      reportError(error);
    }
  };

  const runAction = async (action: () => Promise<void>, success?: string) => {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      refresh();
      if (success) setMessage({ kind: "success", text: success });
    } catch (error) {
      reportError(error);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <main className="loading-screen">Loading FactWise Care</main>;
  if (!user) return <Login onLogin={handleLogin} busy={busy} message={message} />;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">FW</div>
          <div>
            <strong>FactWise</strong>
            <span>CARE OPERATIONS</span>
          </div>
        </div>
        <div className="facility-label">FACILITY</div>
        <div className="facility-name">Northfield Quarantine Unit</div>
        <nav className="primary-nav" aria-label="Main navigation">
          {navByRole[user.role].map(([key, label]) => (
            <button
              className={`nav-item ${screen === key ? "active" : ""}`}
              key={key}
              onClick={() => {
                setScreen(key);
                setDetail(null);
                setMessage(null);
              }}
            >
              <span>{label}</span>
              {key === "intake" && <span className="nav-indicator">Review</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="role-card">
            <span className="eyebrow">SIGNED IN AS</span>
            <strong>{user.full_name}</strong>
            <span>{roleTitles[user.role]}</span>
          </div>
          <button className="logout-button" onClick={handleLogout}>Sign out</button>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <div className="eyebrow">FACTWISE CARE / {roleTitles[user.role].toUpperCase()}</div>
            <h1>{navByRole[user.role].find(([key]) => key === screen)?.[1] ?? "Overview"}</h1>
          </div>
          <div className="topbar-right">
            <span className="today-label">{new Date().toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}</span>
            <span className="live-state"><i /> Local data active</span>
          </div>
        </header>
        {message && <div className={`message ${message.kind}`} role="status">{message.text}</div>}
        {screen === "dashboard" && <DashboardScreen refreshKey={dataVersion} onError={reportError} />}
        {screen === "patients" && <PatientsScreen role={user.role} refreshKey={dataVersion} onOpen={setDetail} onError={reportError} onAction={runAction} />}
        {screen === "tasks" && (
          <WorkflowScreen role="nurse" refreshKey={dataVersion} busy={busy} onAction={runAction} onOpen={setDetail} onError={reportError} />
        )}
        {screen === "visits" && (
          <WorkflowScreen role="doctor" refreshKey={dataVersion} busy={busy} onAction={runAction} onOpen={setDetail} onError={reportError} />
        )}
        {screen === "discharge" && (
          <DischargeScreen role={user.role} refreshKey={dataVersion} busy={busy} onAction={runAction} onError={reportError} />
        )}
        {screen === "intake" && (
          <IntakeScreen role={user.role} refreshKey={dataVersion} busy={busy} onAction={runAction} onError={reportError} />
        )}
        {screen === "assistant" && (
          <AssistantScreen
            role={user.role}
            refreshKey={dataVersion}
            reply={assistantReply}
            onReply={setAssistantReply}
            onAction={runAction}
            onError={reportError}
          />
        )}
        {screen === "settings" && user.role === "admin" && (
          <SettingsScreen busy={busy} onAction={runAction} onError={reportError} />
        )}
        {detail && <PatientDrawer patient={detail} onClose={() => setDetail(null)} />}
      </main>
    </div>
  );
}

function Login({ onLogin, busy, message }: { onLogin: (username: string) => void; busy: boolean; message: Message | null }) {
  return (
    <main className="login-screen">
      <section className="login-card">
        <div className="brand login-brand">
          <div className="brand-mark">FW</div>
          <div><strong>FactWise</strong><span>CARE OPERATIONS</span></div>
        </div>
        <div className="eyebrow">Q2 FUNCTIONAL PROTOTYPE</div>
        <h1>Care, coordinated.</h1>
        <p>Daily patient operations, clear handoffs, and accountable discharge review.</p>
        {message && <div className={`message ${message.kind}`} role="alert">{message.text}</div>}
        <div className="demo-access">
          <span className="eyebrow">DEVELOPMENT DEMO ACCESS</span>
          <button disabled={busy} onClick={() => onLogin("admin")}><span>Administrator</span><small>Admissions and facility oversight</small><b>Sign in</b></button>
          <button disabled={busy} onClick={() => onLogin("nurse")}><span>Nurse</span><small>Daily temperature tasks</small><b>Sign in</b></button>
          <button disabled={busy} onClick={() => onLogin("doctor")}><span>Doctor</span><small>Visit queue and discharge review</small><b>Sign in</b></button>
        </div>
        <div className="demo-note">Synthetic records only. This prototype is not a clinical decision system.</div>
      </section>
    </main>
  );
}

function DashboardScreen({ refreshKey, onError }: { refreshKey: number; onError: (e: unknown) => void }) {
  const [data, setData] = useState<Dashboard | null>(null);
  useEffect(() => {
    api<Dashboard>("/api/v1/dashboard/summary").then(setData).catch(onError);
  }, [refreshKey, onError]);
  if (!data) return <div className="loading-line">Loading facility metrics</div>;
  return (
    <div className="content-stack">
      <section className="intro-row">
        <div><span className="eyebrow">TODAY AT A GLANCE</span><h2>Facility operations</h2><p>Live status from active admissions and recorded care tasks.</p></div>
        <a className="text-link" href={apiUrl("/api/v1/dashboard/export.csv")}>Download daily CSV <span>↗</span></a>
      </section>
      <section className="metric-grid">
        <Metric label="Beds occupied" value={`${data.occupied} / ${data.capacity}`} detail={`${data.available} available`} />
        <Metric label="Temperatures recorded" value={data.temperature_recorded} detail={`${data.temperature_pending} still pending`} />
        <Metric label="Doctor visits complete" value={data.visits_recorded} detail={`${data.visits_pending} still pending`} />
        <Metric label="Eligible for review" value={data.eligible_for_review} detail="Requires doctor review and admin action" />
      </section>
      <section className="two-column">
        <div className="panel">
          <div className="panel-heading"><div><span className="eyebrow">OUTCOME SNAPSHOT</span><h3>Finalized outcomes</h3></div><span className="tag">{data.outcomes.label}</span></div>
          <div className="outcome-numbers">
            <div><span>Mortality</span><strong>{data.outcomes.mortality_rate == null ? "N/A" : `${data.outcomes.mortality_rate}%`}</strong><small>{data.outcomes.deaths} deaths / {data.outcomes.denominator} outcomes</small><small>Benchmark {data.outcomes.mortality_benchmark}%</small></div>
            <div><span>Survival</span><strong>{data.outcomes.survival_rate == null ? "N/A" : `${data.outcomes.survival_rate}%`}</strong><small>{data.outcomes.alive} alive / {data.outcomes.denominator} outcomes</small><small>Benchmark {data.outcomes.survival_benchmark}%</small></div>
          </div>
          <p className="fine-print">Outcome period: {data.outcomes.period_start ?? "No outcomes"} to {data.outcomes.period_end ?? "No outcomes"}</p>
          <p className="fine-print">Synthetic sample only. Active admissions are excluded from the denominator.</p>
        </div>
        <div className="panel rules-panel">
          <span className="eyebrow">OPERATIONAL RULE</span>
          <h3>Three completed days</h3>
          <p>Eligibility uses recorded readings from the previous three complete facility-local days. Missing dates do not qualify. It is an operational rule, not a medical diagnosis.</p>
          <div className="threshold"><span>Configured placeholder threshold</span><strong>{data.fever_threshold_c.toFixed(1)} °C</strong></div>
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return <article className="metric-card"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function PatientsScreen({
  role,
  refreshKey,
  onOpen,
  onError,
  onAction,
}: {
  role: Role;
  refreshKey: number;
  onOpen: (patient: PatientDetail) => void;
  onError: (e: unknown) => void;
  onAction: (action: () => Promise<void>, success?: string) => Promise<void>;
}) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [showAdmit, setShowAdmit] = useState(false);
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  useEffect(() => {
    api<Patient[]>("/api/v1/patients").then(setPatients).catch(onError);
  }, [refreshKey, onError]);
  const admit = async (event: FormEvent) => {
    event.preventDefault();
    await onAction(async () => {
      await api("/api/v1/admissions", { method: "POST", body: jsonBody({ full_name: name, age: Number(age) }) });
      setName("");
      setAge("");
      setShowAdmit(false);
    }, "Patient admitted and a bed assigned.");
  };
  return (
    <div className="content-stack">
      <section className="intro-row">
        <div><span className="eyebrow">ACTIVE REGISTRY</span><h2>Patients</h2><p>Open a record to review measurements, visits, and task status.</p></div>
        {role === "admin" && <button className="button primary" onClick={() => setShowAdmit(!showAdmit)}>{showAdmit ? "Close form" : "Admit patient"}</button>}
      </section>
      {showAdmit && <form className="inline-form panel" onSubmit={(event) => { void admit(event).catch(onError); }}>
        <label>Patient name<input required value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>Age<input required type="number" min="0" max="125" value={age} onChange={(e) => setAge(e.target.value)} /></label>
        <button className="button primary" type="submit">Assign bed and admit</button>
      </form>}
      <PatientTable patients={patients} onOpen={async (patient) => {
        try { onOpen(await api<PatientDetail>(`/api/v1/patients/${patient.id}`)); } catch (error) { onError(error); }
      }} />
    </div>
  );
}

function PatientTable({ patients, onOpen, children }: { patients: Patient[]; onOpen: (patient: Patient) => void; children?: (patient: Patient) => ReactNode }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Patient</th><th>Bed</th><th>Temperature</th><th>Doctor visit</th><th>Discharge rule</th><th /></tr></thead>
        <tbody>
          {patients.map((patient) => (
            <tr key={patient.id}>
              <td><button className="patient-link" onClick={() => onOpen(patient)}><strong>{patient.full_name}</strong><small>{patient.patient_code} · {patient.age} years</small></button></td>
              <td>{patient.bed_code ?? "Not assigned"}</td>
              <td><Status value={patient.temperature_status} /></td>
              <td><Status value={patient.doctor_visit_status} /></td>
              <td><Status value={patient.eligible ? "eligible" : "not eligible"} /></td>
              <td>{children?.(patient)}</td>
            </tr>
          ))}
          {!patients.length && <tr><td className="empty-row" colSpan={6}>No active patient records.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function Status({ value }: { value: string }) {
  const normalized = value.replaceAll("_", " ");
  return <span className={`status-chip ${normalized.includes("recorded") || normalized === "eligible" ? "good" : normalized.includes("pending") || normalized.includes("missed") ? "pending" : "neutral"}`}>{normalized}</span>;
}

function WorkflowScreen({
  role,
  refreshKey,
  busy,
  onAction,
  onOpen,
  onError,
}: {
  role: "nurse" | "doctor";
  refreshKey: number;
  busy: boolean;
  onAction: (action: () => Promise<void>, success?: string) => Promise<void>;
  onOpen: (patient: PatientDetail) => void;
  onError: (e: unknown) => void;
}) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [rowId, setRowId] = useState("");
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState("C");
  const [note, setNote] = useState("");
  const [urgent, setUrgent] = useState("");
  const [visitNotes, setVisitNotes] = useState("");
  const [correctionReason, setCorrectionReason] = useState("");
  const [outcomeNotes, setOutcomeNotes] = useState("");
  const [correctionMode, setCorrectionMode] = useState(false);
  const [outcomeMode, setOutcomeMode] = useState(false);
  useEffect(() => {
    const endpoint = role === "nurse" ? "/api/v1/nurse-tasks" : "/api/v1/doctor-queue";
    api<Patient[]>(endpoint).then(setPatients).catch(onError);
  }, [role, refreshKey, onError]);
  const selected = patients.find((p) => p.id === rowId);
  const closeForm = () => {
    setRowId("");
    setCorrectionMode(false);
    setOutcomeMode(false);
    setValue("");
    setUnit("C");
    setNote("");
    setUrgent("");
    setVisitNotes("");
    setCorrectionReason("");
    setOutcomeNotes("");
  };
  const submitTemperature = (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    void onAction(async () => {
      if (correctionMode && selected.latest_temperature_id) {
        await api(`/api/v1/patients/${selected.id}/temperatures/${selected.latest_temperature_id}/correction`, {
          method: "POST",
          body: jsonBody({ value: Number(value), unit, reason: correctionReason }),
        });
      } else {
        await api(`/api/v1/patients/${selected.id}/temperatures`, {
          method: "POST",
          body: jsonBody({ value: Number(value), unit, measured_at: new Date().toISOString(), note }),
        });
      }
      setValue("");
      setNote("");
      setCorrectionReason("");
      closeForm();
    }, correctionMode ? "Correction saved. The original reading remains in history." : "Temperature saved. The task list and doctor queue are updated.");
  };
  const submitVisit = (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    void onAction(async () => {
      await api(`/api/v1/patients/${selected.id}/visits`, {
        method: "POST",
        body: jsonBody({ notes: visitNotes, urgent_reason: urgent }),
      });
      setVisitNotes("");
      setUrgent("");
      closeForm();
    }, "Doctor visit saved.");
  };
  const submitOutcome = (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    void onAction(async () => {
      await api(`/api/v1/patients/${selected.id}/outcome`, {
        method: "POST",
        body: jsonBody({ notes: outcomeNotes }),
      });
      setOutcomeNotes("");
      closeForm();
    }, "Deceased outcome recorded and bed released.");
  };
  return (
    <div className="content-stack">
      <section className="intro-row"><div><span className="eyebrow">{role === "nurse" ? "NURSING WORKLIST" : "MEDICAL WORKLIST"}</span><h2>{role === "nurse" ? "Today's temperature tasks" : "Today's doctor queue"}</h2><p>{role === "nurse" ? "Record one routine measurement per patient and local day." : "Review measurements, then record today's doctor visit."}</p></div><span className="tag">Facility local date</span></section>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Patient</th><th>Temperature</th><th>Latest reading</th><th>Doctor visit</th><th>Task</th></tr></thead>
          <tbody>{patients.map((patient) => (
            <tr key={patient.id}>
              <td><button className="patient-link" onClick={async () => {
                try { onOpen(await api<PatientDetail>(`/api/v1/patients/${patient.id}`)); } catch (error) { onError(error); }
              }}><strong>{patient.full_name}</strong><small>{patient.patient_code} · Bed {patient.bed_code}</small></button></td>
              <td><Status value={patient.temperature_status} /></td>
              <td>{patient.latest_temperature_c == null ? "No reading" : `${patient.latest_temperature_c.toFixed(1)} °C`}</td>
              <td><Status value={patient.doctor_visit_status} /></td>
              <td>
                {role === "nurse" ? (
                  patient.temperature_status === "recorded" && patient.latest_temperature_id ? (
                    <button className="button small" onClick={() => {
                      setRowId(patient.id);
                      setCorrectionMode(true);
                      setOutcomeMode(false);
                    }}>Correct reading</button>
                  ) : (
                    <button className="button small" onClick={() => {
                      setRowId(patient.id);
                      setCorrectionMode(false);
                      setOutcomeMode(false);
                    }}>Record temperature</button>
                  )
                ) : (
                  <div className="row-actions">
                    {patient.doctor_visit_status !== "recorded"
                      ? <button className="button small" onClick={() => {
                          setRowId(patient.id);
                          setOutcomeMode(false);
                        }}>Record visit</button>
                      : <span className="task-complete">Complete</span>}
                    <button className="plain-button" onClick={() => {
                      setRowId(patient.id);
                      setOutcomeMode(true);
                    }}>Record outcome</button>
                  </div>
                )}
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {selected && <form className="panel action-form" onSubmit={outcomeMode ? submitOutcome : role === "nurse" ? submitTemperature : submitVisit}>
        <div className="panel-heading"><div><span className="eyebrow">{outcomeMode ? "OUTCOME RECORD" : correctionMode ? "CORRECTION" : role === "nurse" ? "NEW MEASUREMENT" : "DOCTOR NOTE"}</span><h3>{selected.full_name}</h3></div><button type="button" className="plain-button" onClick={closeForm}>Close</button></div>
        {outcomeMode ? <div className="outcome-form">
          <div className="warning-box">This records a deceased outcome, closes the active admission, and releases the bed. The action is permanent and requires doctor authorization.</div>
          <label>Notes<input value={outcomeNotes} onChange={(e) => setOutcomeNotes(e.target.value)} maxLength={1000} /></label>
          <button className="button primary" disabled={busy} type="submit">Confirm deceased outcome</button>
        </div> : role === "nurse" ? <>
          <div className="form-grid">
            <label>Temperature<input required type="number" min={unit === "C" ? 30 : 86} max={unit === "C" ? 45 : 113} step="0.1" value={value} onChange={(e) => setValue(e.target.value)} /></label>
            <label>Unit<select value={unit} onChange={(e) => setUnit(e.target.value)}><option value="C">Celsius</option><option value="F">Fahrenheit</option></select></label>
          </div>
          {correctionMode
            ? <label>Correction reason<input required value={correctionReason} onChange={(e) => setCorrectionReason(e.target.value)} maxLength={500} /></label>
            : <label>Optional note<input value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} /></label>}
        </> : <>
          {selected.temperature_status !== "recorded" && <div className="warning-box">Today's temperature is pending. For an urgent visit, provide a reason below.</div>}
          <label>Visit notes<textarea rows={3} value={visitNotes} onChange={(e) => setVisitNotes(e.target.value)} maxLength={2000} /></label>
          {selected.temperature_status !== "recorded" && <label>Urgent-care reason<input value={urgent} onChange={(e) => setUrgent(e.target.value)} maxLength={500} placeholder="Required before saving this visit" /></label>}
        </>}
        {!outcomeMode && <button className="button primary" disabled={busy} type="submit">{busy ? "Saving" : correctionMode ? "Save correction" : "Save record"}</button>}
      </form>}
    </div>
  );
}

function DischargeScreen({
  role,
  refreshKey,
  busy,
  onAction,
  onError,
}: {
  role: Role;
  refreshKey: number;
  busy: boolean;
  onAction: (action: () => Promise<void>, success?: string) => Promise<void>;
  onError: (e: unknown) => void;
}) {
  const [items, setItems] = useState<Array<Patient & { evidence: Eligibility; doctor_reviewed: boolean; review_notes: string }>>([]);
  useEffect(() => {
    api<typeof items>("/api/v1/discharge-review").then(setItems).catch(onError);
  }, [refreshKey, onError]);
  return (
    <div className="content-stack">
      <section className="intro-row"><div><span className="eyebrow">DETERMINISTIC EVIDENCE</span><h2>Discharge review</h2><p>Only eligible patients appear here. Doctor reviews evidence; an administrator finalizes discharge.</p></div><span className="tag">Not a medical diagnosis</span></section>
      {items.map((item) => <article className="panel evidence-card" key={item.admission_id}>
        <div className="panel-heading"><div><span className="eyebrow">{item.patient_code} / BED {item.bed_code}</span><h3>{item.full_name}</h3></div><Status value={item.doctor_reviewed ? "review recorded" : "review pending"} /></div>
        <p className="evidence-reason">{item.evidence.reason} Configured threshold: {item.evidence.threshold_c.toFixed(1)} °C.</p>
        <div className="evidence-days">{item.evidence.days.map((day) => <div key={day.date}><span>{day.date}</span><strong>{day.readings_c.length ? day.readings_c.map((t) => `${t.toFixed(1)}°`).join(", ") : "No reading"}</strong><small>{day.qualifies ? "Qualifying day" : "Does not qualify"}</small></div>)}</div>
        {role === "doctor" && !item.doctor_reviewed && <button className="button" disabled={busy} onClick={() => void onAction(async () => {
          await api(`/api/v1/admissions/${item.admission_id}/discharge-review`, { method: "POST", body: jsonBody({ notes: "Reviewed the displayed deterministic evidence." }) });
        }, "Discharge review recorded.")}>Record doctor review</button>}
        {role === "admin" && <button className="button primary" disabled={busy || !item.doctor_reviewed} title={!item.doctor_reviewed ? "Doctor review is required" : ""} onClick={() => void onAction(async () => {
          await api(`/api/v1/admissions/${item.admission_id}/discharge`, { method: "POST", body: jsonBody({ notes: "Discharged after review." }) });
        }, "Discharge finalized and bed released.")}>Finalize discharge</button>}
      </article>)}
      {!items.length && <div className="empty-panel">No patients currently meet the configured three-full-day rule.</div>}
    </div>
  );
}

function IntakeScreen({
  role,
  refreshKey,
  busy,
  onAction,
  onError,
}: {
  role: Role;
  refreshKey: number;
  busy: boolean;
  onAction: (action: () => Promise<void>, success?: string) => Promise<void>;
  onError: (e: unknown) => void;
}) {
  const [items, setItems] = useState<IntakeRequest[]>([]);
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [details, setDetails] = useState("");
  const [openId, setOpenId] = useState("");
  const [completionName, setCompletionName] = useState("");
  const [completionAge, setCompletionAge] = useState("");
  const [completionDetails, setCompletionDetails] = useState("");
  useEffect(() => {
    api<IntakeRequest[]>("/api/v1/intake-requests").then(setItems).catch(onError);
  }, [refreshKey, onError]);
  const create = (event: FormEvent) => {
    event.preventDefault();
    void onAction(async () => {
      await api("/api/v1/intake-requests", {
        method: "POST",
        body: jsonBody({ full_name: name, age: age ? Number(age) : null, details }),
      });
      setName("");
      setAge("");
      setDetails("");
    }, "Intake request saved. Missing information is flagged for review.");
  };
  const complete = (event: FormEvent, id: string) => {
    event.preventDefault();
    void onAction(async () => {
      await api(`/api/v1/intake-requests/${id}/complete`, {
        method: "POST",
        body: jsonBody({ full_name: completionName, age: Number(completionAge), details: completionDetails }),
      });
      setOpenId("");
      setCompletionName("");
      setCompletionAge("");
      setCompletionDetails("");
    }, "Patient admitted and intake request completed.");
  };
  return (
    <div className="content-stack">
      <section className="intro-row"><div><span className="eyebrow">INCOMPLETE INFORMATION IS PRESERVED</span><h2>Intake review</h2><p>Submit what is available. Requests missing patient details are queued for review rather than discarded.</p></div></section>
      <form className="panel inline-form intake-form" onSubmit={create}>
        <label>Patient name, if known<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Leave blank if unknown" /></label>
        <label>Age, if known<input type="number" min="0" max="125" value={age} onChange={(e) => setAge(e.target.value)} placeholder="Optional" /></label>
        <label>Available context<input value={details} onChange={(e) => setDetails(e.target.value)} maxLength={2000} placeholder="Optional notes for human review" /></label>
        <button className="button primary" disabled={busy} type="submit">Save intake request</button>
      </form>
      <div className="table-wrap"><table>
        <thead><tr><th>Request</th><th>Received</th><th>Status</th><th>Review note</th><th>Action</th></tr></thead>
        <tbody>{items.map((item) => <tr key={item.id}>
          <td><strong>{item.full_name ?? "Name not provided"}</strong><small>{item.age == null ? "Age not provided" : `${item.age} years`} · {item.details || "No additional context"}</small></td>
          <td>{formatTime(item.created_at)}</td>
          <td><Status value={item.status} /></td>
          <td>{item.review_note || "Ready for admission"}</td>
          <td>{role === "admin" && item.status !== "completed" && <button className="button small" onClick={() => {
            setOpenId(openId === item.id ? "" : item.id);
            setCompletionName(item.full_name ?? "");
            setCompletionAge(item.age == null ? "" : String(item.age));
            setCompletionDetails(item.details);
          }}>Review and admit</button>}</td>
        </tr>)}
        {!items.length && <tr><td className="empty-row" colSpan={5}>No intake requests have been submitted.</td></tr>}
        </tbody>
      </table></div>
      {openId && role === "admin" && <form className="panel action-form" onSubmit={(event) => complete(event, openId)}>
        <div className="panel-heading"><div><span className="eyebrow">HUMAN REVIEW REQUIRED</span><h3>Complete patient details</h3></div><span className="tag">Admission needs a name and age</span></div>
        <div className="form-grid"><label>Patient name<input required value={completionName} onChange={(e) => setCompletionName(e.target.value)} /></label><label>Age<input required type="number" min="0" max="125" value={completionAge} onChange={(e) => setCompletionAge(e.target.value)} /></label></div>
        <label>Review notes<input value={completionDetails} onChange={(e) => setCompletionDetails(e.target.value)} /></label>
        <button disabled={busy} className="button primary" type="submit">Confirm and assign a bed</button>
      </form>}
    </div>
  );
}

function AssistantScreen({
  role,
  refreshKey,
  reply,
  onReply,
  onAction,
  onError,
}: {
  role: Role;
  refreshKey: number;
  reply: string;
  onReply: (value: string) => void;
  onAction: (action: () => Promise<void>, success?: string) => Promise<void>;
  onError: (e: unknown) => void;
}) {
  const [question, setQuestion] = useState("");
  const [requests, setRequests] = useState<AssistantRequest[]>([]);
  useEffect(() => {
    if (role === "nurse") return;
    api<AssistantRequest[]>("/api/v1/ai/requests").then(setRequests).catch(onError);
  }, [refreshKey, role, onError]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void onAction(async () => {
      const result = await api<{ answer: string; human_review_required: boolean; ai_used: boolean }>("/api/v1/ai/ask", {
        method: "POST",
        body: jsonBody({ question }),
      });
      onReply(result.answer);
      setQuestion("");
    });
  };
  return (
    <div className="content-stack">
      <section className="intro-row"><div><span className="eyebrow">ADVISORY ONLY</span><h2>Knowledge requests</h2><p>No response from this panel can change a patient record, eligibility, or discharge state.</p></div><span className="tag warning-tag">AI not configured</span></section>
      <div className="two-column">
        <form className="panel assistant-panel" onSubmit={submit}>
          <span className="eyebrow">SUBMIT A QUESTION</span><h3>Ask about approved facility information</h3>
          <p>When evidence is missing or the question is blank, the request is still saved and flagged for human review. No AI response is trusted or generated in this build.</p>
          <label>Question<input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Question is optional; blank requests are queued too" /></label>
          <button className="button primary" type="submit">Submit for review</button>
          {reply && <div className="review-result"><span className="eyebrow">REVIEW REQUIRED</span><p>{reply}</p></div>}
        </form>
        {role !== "nurse" && <section className="panel">
          <div className="panel-heading"><div><span className="eyebrow">HUMAN REVIEW QUEUE</span><h3>Requests</h3></div><span className="tag">{requests.filter((r) => r.status === "needs_review").length} open</span></div>
          <div className="request-list">{requests.map((item) => <article className="request-item" key={item.id}>
            <div className="request-meta"><Status value={item.status} /><time>{formatTime(item.created_at)}</time></div>
            <p>{item.question || "No question provided"}</p><small>{item.answer}</small>
            {item.status === "needs_review" && <button className="button small" onClick={() => void onAction(async () => {
              await api(`/api/v1/ai/requests/${item.id}/review`, { method: "POST", body: jsonBody({ review_note: "Reviewed by staff. No approved evidence available." }) });
            }, "Human review recorded.")}>Mark reviewed</button>}
          </article>)}
          {!requests.length && <div className="empty-inline">No knowledge requests are waiting.</div>}</div>
        </section>}
      </div>
    </div>
  );
}

function SettingsScreen({
  busy,
  onAction,
  onError,
}: {
  busy: boolean;
  onAction: (action: () => Promise<void>, success?: string) => Promise<void>;
  onError: (e: unknown) => void;
}) {
  const [threshold, setThreshold] = useState("38.0");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [reviewRequired, setReviewRequired] = useState(true);
  useEffect(() => {
    api<{ fever_threshold_c: number; facility_timezone: string; discharge_requires_doctor_review: boolean }>("/api/v1/settings")
      .then((data) => {
        setThreshold(String(data.fever_threshold_c));
        setTimezone(data.facility_timezone);
        setReviewRequired(data.discharge_requires_doctor_review);
      })
      .catch(onError);
  }, [onError]);
  const save = (event: FormEvent) => {
    event.preventDefault();
    void onAction(async () => {
      await api("/api/v1/settings", {
        method: "PATCH",
        body: jsonBody({
          fever_threshold_c: Number(threshold),
          facility_timezone: timezone,
          discharge_requires_doctor_review: reviewRequired,
        }),
      });
    }, "Facility rules saved and audited.");
  };
  return <form className="panel settings-form" onSubmit={save}>
    <span className="eyebrow">ADMINISTRATOR CONTROL</span><h2>Facility rules</h2>
    <p>These are operational placeholders and must not be interpreted as approved clinical policy.</p>
    <label>Fever threshold (°C)<input required type="number" min="35" max="42" step="0.1" value={threshold} onChange={(e) => setThreshold(e.target.value)} /></label>
    <label>Facility time zone<input required value={timezone} onChange={(e) => setTimezone(e.target.value)} /></label>
    <label className="check-label"><input className="checkbox" type="checkbox" checked={reviewRequired} onChange={(e) => setReviewRequired(e.target.checked)} /> Require doctor review before discharge</label>
    <button className="button primary" disabled={busy}>Save settings</button>
  </form>;
}

function PatientDrawer({ patient, onClose }: { patient: PatientDetail; onClose: () => void }) {
  const eligible = useMemo(() => patient.eligible, [patient.eligible]);
  return <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <aside className="patient-drawer" aria-label="Patient details">
      <div className="panel-heading"><div><span className="eyebrow">{patient.patient_code} / BED {patient.bed_code}</span><h2>{patient.full_name}</h2><p>{patient.age} years · Admitted {formatTime(patient.admitted_at)}</p></div><button className="plain-button" onClick={onClose}>Close</button></div>
      <section className="drawer-section"><span className="eyebrow">CURRENT TASKS</span><div className="status-row"><span>Temperature today</span><Status value={patient.temperature_status} /></div><div className="status-row"><span>Doctor visit today</span><Status value={patient.doctor_visit_status} /></div><div className="status-row"><span>Discharge rule</span><Status value={eligible ? "eligible" : "not eligible"} /></div></section>
      <section className="drawer-section"><span className="eyebrow">TEMPERATURE HISTORY</span>{patient.temperatures.map((reading) => <div className="history-item" key={reading.id}><strong>{reading.value_c.toFixed(1)} °C · {reading.status}</strong><span>{reading.local_date} · Measured {formatTime(reading.measured_at)}</span><small>Recorded by {reading.recorded_by} at {formatTime(reading.recorded_at)}{reading.correction_reason ? ` · Correction: ${reading.correction_reason}` : ""}{reading.note ? ` · ${reading.note}` : ""}</small></div>)}{!patient.temperatures.length && <p className="empty-inline">No temperature readings recorded.</p>}</section>
      <section className="drawer-section"><span className="eyebrow">DOCTOR VISITS</span>{patient.visits.map((visit) => <div className="history-item" key={visit.id}><strong>{visit.local_date} · {visit.doctor}</strong><span>{visit.notes || "No visit notes"}</span>{visit.urgent_reason && <small>Urgent reason: {visit.urgent_reason}</small>}</div>)}{!patient.visits.length && <p className="empty-inline">No doctor visits recorded.</p>}</section>
    </aside>
  </div>;
}

export default App;
