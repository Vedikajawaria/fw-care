export interface Patient {
  id: string;
  admission_id: string | null;
  patient_code: string;
  full_name: string;
  age: number;
  bed_code: string | null;
  status: string;
  temperature_status: string;
  latest_temperature_id: string | null;
  latest_temperature_c: number | null;
  doctor_visit_status: string;
  eligible: boolean;
}

export interface Dashboard {
  capacity: number;
  occupied: number;
  available: number;
  temperature_recorded: number;
  temperature_pending: number;
  visits_recorded: number;
  visits_pending: number;
  eligible_for_review: number;
  fever_threshold_c: number;
  facility_timezone: string;
  outcomes: {
    label: string;
    deaths: number;
    alive: number;
    denominator: number;
    period_start: string | null;
    period_end: string | null;
    mortality_rate: number | null;
    survival_rate: number | null;
    mortality_benchmark: number;
    survival_benchmark: number;
  };
}

export interface PatientDetail extends Patient {
  admitted_at: string | null;
  temperatures: Array<{
    id: string;
    value_c: number;
    unit_entered: string;
    measured_at: string;
    local_date: string;
    note: string;
    recorded_by: string;
    status: string;
    correction_of_id: string | null;
    correction_reason: string;
    recorded_at: string;
  }>;
  visits: Array<{
    id: string;
    visited_at: string;
    local_date: string;
    notes: string;
    doctor: string;
    urgent_reason: string;
  }>;
}

export interface IntakeRequest {
  id: string;
  full_name: string | null;
  age: number | null;
  details: string;
  status: string;
  review_note: string;
  created_patient_id: string | null;
  created_at: string;
}

export interface AssistantRequest {
  id: string;
  question: string;
  status: string;
  answer: string;
  review_note: string;
  created_at: string;
}

export interface Eligibility {
  eligible: boolean;
  reason: string;
  threshold_c: number;
  days: Array<{ date: string; readings_c: number[]; qualifies: boolean }>;
}
