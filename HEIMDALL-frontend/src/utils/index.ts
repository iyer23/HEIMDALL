import type { Decision, FaceStatus, ForensicsStatus, MRZStatus } from '@/types';

// ─── Risk thresholds (must match backend risk_service.py) ─────────────────────
export const THRESHOLD_PASS = 24;
export const THRESHOLD_HIGH = 59;

export function riskColor(score: number): string {
  if (score <= THRESHOLD_PASS) return '#356859';
  if (score <= THRESHOLD_HIGH) return '#C47A2C';
  return '#B54848';
}
export function riskLabel(score: number): string {
  if (score <= THRESHOLD_PASS) return 'Pass';
  if (score <= THRESHOLD_HIGH) return 'Review Required';
  return 'High Risk';
}
export function decisionColor(d: Decision): string {
  return { PASS: '#356859', REVIEW_REQUIRED: '#C47A2C', HIGH_RISK: '#B54848' }[d] ?? '#5A6153';
}
export function decisionLabel(d: Decision): string {
  return { PASS: 'PASS', REVIEW_REQUIRED: 'REVIEW REQUIRED', HIGH_RISK: 'HIGH RISK' }[d] ?? d;
}

// ─── Face status helpers ──────────────────────────────────────────────────────
export function faceStatusColor(s: FaceStatus | string): string {
  if (s === 'MATCH')                return '#356859';
  if (s === 'POSSIBLE_MATCH')       return '#4E7A6B';
  if (s === 'REVIEW')               return '#C47A2C';
  if (s === 'MISMATCH')             return '#B54848';
  return '#8A9080';  // INCONCLUSIVE / NOT_PROVIDED / UNAVAILABLE
}
export function faceStatusLabel(s: FaceStatus | string): string {
  const m: Record<string,string> = {
    MATCH:         'Match',
    POSSIBLE_MATCH:'Possible Match',
    REVIEW:        'Review Required',
    MISMATCH:      'Mismatch',
    INCONCLUSIVE:  'Inconclusive',
    NOT_PROVIDED:  'Not Provided',
    UNAVAILABLE:   'Engine Unavailable',
  };
  return m[s] ?? s;
}
export function faceIsMeaningful(s: FaceStatus | string): boolean {
  return ['MATCH','POSSIBLE_MATCH','REVIEW','MISMATCH'].includes(s);
}

// ─── MRZ status helpers ───────────────────────────────────────────────────────
export function mrzStatusColor(s: MRZStatus | string): string {
  if (s === 'VALID')          return '#356859';
  if (s === 'PARTIAL')        return '#C47A2C';
  if (s === 'INVALID')        return '#B54848';
  if (s === 'NOT_DETECTED')   return '#C47A2C';
  if (s === 'UNREADABLE')     return '#C47A2C';
  return '#8A9080';  // NOT_APPLICABLE
}
export function mrzStatusLabel(s: MRZStatus | string): string {
  const m: Record<string,string> = {
    NOT_APPLICABLE: 'Not Applicable',
    NOT_DETECTED:   'Not Detected',
    UNREADABLE:     'Unreadable',
    VALID:          'Valid',
    PARTIAL:        'Partial',
    INVALID:        'Invalid',
  };
  return m[s] ?? s;
}

// ─── Forensics helpers ────────────────────────────────────────────────────────
export function forensicsStatusColor(s: ForensicsStatus | string): string {
  if (s === 'CLEAN')        return '#356859';
  if (s === 'LOW_ANOMALY')  return '#4E7A6B';
  if (s === 'SUSPICIOUS')   return '#C47A2C';
  if (s === 'HIGH_ANOMALY') return '#B54848';
  return '#8A9080';  // INCONCLUSIVE
}
export function forensicsStatusLabel(s: ForensicsStatus | string): string {
  const m: Record<string,string> = {
    CLEAN:        'Clean',
    LOW_ANOMALY:  'Low Anomaly',
    SUSPICIOUS:   'Suspicious',
    HIGH_ANOMALY: 'High Anomaly',
    INCONCLUSIVE: 'Inconclusive',
  };
  return m[s] ?? s;
}

// ─── Formatting ───────────────────────────────────────────────────────────────
export function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}
export function formatFileSize(b: number): string {
  if (b < 1024)        return `${b} B`;
  if (b < 1048576)     return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}
export function formatTs(iso: string): string {
  return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}
export const formatTimestamp = formatTs;

export function docTypeLabel(t: string): string {
  return t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
export const getDocumentTypeLabel = docTypeLabel;

// ─── File validation ──────────────────────────────────────────────────────────
export function validateFile(f: File): string | null {
  const ok = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
  if (!ok.includes(f.type)) return 'Unsupported type. Use JPG, PNG or PDF.';
  if (f.size > 10 * 1024 * 1024) return 'File exceeds 10 MB limit.';
  return null;
}

// ─── Aliases for legacy components ───────────────────────────────────────────
export const getRiskColor      = riskColor;
export const getDocTypeLabel   = docTypeLabel;
export function getDecisionLabel(d: Decision): string { return decisionLabel(d); }
export function cn(...cls: (string | undefined | null | false)[]): string {
  return cls.filter(Boolean).join(' ');
}
