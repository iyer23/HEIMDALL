// ─── Document & Decision enums ───────────────────────────────────────────────
export type DocumentType = 'passport' | 'visa' | 'national_id' | 'driving_licence' | 'permit' | 'unknown';
export type Decision     = 'PASS' | 'REVIEW_REQUIRED' | 'HIGH_RISK';
export type CheckStatus  = 'PASS' | 'WARNING' | 'FAIL' | 'NOT_APPLICABLE';

// Face service now uses 'status' with these values
export type FaceStatus =
  | 'MATCH' | 'POSSIBLE_MATCH' | 'REVIEW' | 'MISMATCH'
  | 'INCONCLUSIVE' | 'NOT_PROVIDED' | 'UNAVAILABLE';

// MRZ status
export type MRZStatus =
  | 'NOT_APPLICABLE' | 'NOT_DETECTED' | 'UNREADABLE'
  | 'VALID' | 'PARTIAL' | 'INVALID';

// Forensics status
export type ForensicsStatus =
  | 'CLEAN' | 'LOW_ANOMALY' | 'SUSPICIOUS' | 'HIGH_ANOMALY' | 'INCONCLUSIVE';

// ─── Demo cases ───────────────────────────────────────────────────────────────
export type DemoCase =
  | 'valid_passport' | 'expired_document' | 'tampered_text'
  | 'face_mismatch'  | 'multiple_flags'
  | 'aadhaar_valid'  | 'aadhaar_tampered';

// ─── OCR ─────────────────────────────────────────────────────────────────────
export interface OCRField {
  label: string;
  value: string | null;
  confidence: number;     // 0-100
  detected: boolean;
  flagged?: boolean;
}
export interface OCRResult {
  document_type: DocumentType;
  document_type_confidence: number;  // 0-1 from classification
  overall_confidence: number;        // 0-100
  ocr_available: boolean;
  fields: OCRField[];
  raw_mrz?: string | null;
  demo_mode: boolean;
  error?: string;
}

// ─── Validation ───────────────────────────────────────────────────────────────
export interface ValidationCheck {
  check_name: string;
  status: CheckStatus;
  message: string;
  detail?: string;
}
export interface ValidationResult {
  checks: ValidationCheck[];
  passed: number;
  warnings: number;
  failed: number;
  demo_mode: boolean;
}

// ─── MRZ ─────────────────────────────────────────────────────────────────────
export interface MRZCheck {
  check_name: string;
  status: CheckStatus;
  message: string;
  field?: string;
  digit?: string;
  expected?: number;
}
export interface MRZCrossValidation {
  field: string;
  ocr_val: string;
  mrz_val: string;
  match: boolean;
  status: CheckStatus;
  message: string;
}
export interface MRZParsed {
  format?: string;
  issuing_state?: string;
  surname?: string;
  given_names?: string;
  full_name?: string;
  document_number?: string;
  nationality?: string;
  date_of_birth?: string;
  sex?: string;
  expiry_date?: string;
}
export interface MRZResult {
  status: MRZStatus;
  mrz_present: boolean;
  format: string | null;
  parsed: MRZParsed;
  checks: MRZCheck[];
  cross_validation: MRZCrossValidation[];
  checksums_valid: boolean;
  cross_valid: boolean;
  summary: string;
  demo_mode: boolean;
}

// ─── Tampering / Forensics ────────────────────────────────────────────────────
export interface SuspiciousRegion {
  label: string;
  confidence: number;
  bbox: [number, number, number, number];   // x, y, w, h (normalised 0-1)
  reason: string;
}
export interface TamperingResult {
  forensics_available: boolean;
  status: ForensicsStatus;
  is_suspicious: boolean;
  overall_confidence: number;               // 0-100 (anomaly confidence, not forgery probability)
  regions: SuspiciousRegion[];
  metadata_flags: string[];
  metadata_status: 'PRESENT' | 'ABSENT' | 'PRESENT_WITH_ANOMALIES';
  analysis_types: { ela: boolean; metadata: boolean };
  interpretation: string;                   // human-readable advisory text
  demo_mode: boolean;
}

// ─── Face Verification ────────────────────────────────────────────────────────
export interface FaceVerificationResult {
  status: FaceStatus;
  face_available: boolean;
  face_detected_document: boolean;
  face_detected_person: boolean;
  multiple_faces_document: boolean;
  multiple_faces_person: boolean;
  match_score: number | null;               // null when not performed/inconclusive
  distance: number | null;
  threshold_used: number;
  image_quality: 'good' | 'fair' | 'poor' | 'N/A';
  message: string;
  demo_mode: boolean;
}

// ─── Risk / Evidence Fusion ───────────────────────────────────────────────────
export interface RiskFactor {
  label: string;
  points: number;
  severity: 'low' | 'medium' | 'high';
  description: string;
}
export interface RiskBreakdown {
  ocr:        { points: number; cap: number };
  validation: { points: number; cap: number };
  mrz:        { points: number; cap: number };
  forensics:  { points: number; cap: number };
  metadata:   { points: number; cap: number };
  face:       { points: number; cap: number };
  total:      number;
}
export interface RiskResult {
  score: number;
  decision: Decision;
  color: string;
  factors: RiskFactor[];
  breakdown: RiskBreakdown;
  override_reason?: string | null;
}
export interface EvidenceSignal {
  label: string;
  module: string;
  contribution: number;
  reason: string;
  ok: boolean;
}
export interface EvidenceFusion {
  narrative: string;
  signals: EvidenceSignal[];
}

// ─── Blockchain evidence (tamper-evident audit layer) ─────────────────────────
export interface BlockchainEvidence {
  mode: string;                      // 'sepolia' | 'demo'
  network: string;
  network_label: string;
  contract_address: string | null;
  screening_id: string;
  result_hash: string;               // SHA-256 of the PII-free integrity payload
  risk_score: number;
  decision: string;
  hash_algorithm: string;
  status: string;                    // REGISTERED | DEMO_REGISTERED | PENDING | FAILED | NOT_ANCHORED | ...
  tx_hash: string | null;
  block_number: number | null;
  explorer_url: string | null;
  registered_at: string;
  note: string;
}

export interface BlockchainVerifyResult {
  mode: string;
  network: string;
  network_label: string;
  screening_id: string;
  computed_hash: string;
  onchain_hash: string | null;
  anchored: boolean | null;
  verified: boolean;
  verdict: string;                   // VERIFIED | MISMATCH | NOT_FOUND | UNAVAILABLE
  message: string;
  checked_at: string;
  disclaimer: string;
}

// ─── Full screening result (canonical — matches backend exactly) ──────────────
export interface ScreeningResult {
  screening_id: string;
  timestamp: string;
  document_type: DocumentType;
  document_type_confidence: number;   // percentage (0-100)
  ocr: OCRResult;
  validation: ValidationResult;
  mrz: MRZResult;
  tampering: TamperingResult;
  face_verification: FaceVerificationResult;
  risk: RiskResult;
  evidence_fusion: EvidenceFusion;
  processing_time_ms: number;
  demo_mode: boolean;
  blockchain?: BlockchainEvidence;
}

// ─── History record (list view) ───────────────────────────────────────────────
export interface ScreeningRecord {
  screening_id: string;
  timestamp: string;
  document_type: DocumentType;
  nationality?: string;
  risk_score: number;
  decision: Decision;
  processing_time_ms: number;
  demo_mode: boolean;
}

// ─── UI only ──────────────────────────────────────────────────────────────────
export interface ProcessingStep {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'error';
  duration_ms?: number;
}
