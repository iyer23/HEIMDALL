import axios from 'axios';
import type { ScreeningResult, ScreeningRecord, DemoCase, BlockchainEvidence, BlockchainVerifyResult } from '@/types';

const api = axios.create({ baseURL: '/api', timeout: 300000 });

export interface RunScreeningOptions {
  documentFile: File; personFile?: File | null;
  demoMode?: boolean; demoCase?: DemoCase;
}

export async function runScreening(opts: RunScreeningOptions): Promise<ScreeningResult> {
  const fd = new FormData();
  fd.append('document', opts.documentFile);
  if (opts.personFile) fd.append('person_image', opts.personFile);
  if (opts.demoMode)   fd.append('demo_mode', 'true');
  if (opts.demoCase)   fd.append('demo_case', opts.demoCase);
  const r = await api.post<ScreeningResult>('/screening/run', fd,
    { headers: { 'Content-Type': 'multipart/form-data' } });
  return r.data;
}

export async function runDemoScreening(demoCase: DemoCase): Promise<ScreeningResult> {
  const r = await api.post<ScreeningResult>('/screening/demo', { demo_case: demoCase });
  return r.data;
}

export async function getScreenings(params?: { limit?: number; offset?: number; decision?: string })
  : Promise<{ records: ScreeningRecord[]; total: number }> {
  const r = await api.get('/screenings', { params });
  return r.data;
}

export async function getScreening(id: string): Promise<ScreeningResult> {
  const r = await api.get<ScreeningResult>(`/screening/${id}`);
  return r.data;
}

export async function deleteScreening(id: string): Promise<void> {
  await api.delete(`/screening/${id}`);
}

export async function downloadReport(id: string): Promise<Blob> {
  const r = await api.get(`/screening/${id}/report`, { responseType: 'blob' });
  return r.data;
}

export interface AnalyticsSummary {
  total_screened: number; high_risk: number; review_required: number; passed: number;
  avg_processing_time_ms: number;
  risk_distribution: { name: string; value: number; color: string }[];
  recent_trend: { date: string; count: number }[];
}
export async function getAnalytics(): Promise<AnalyticsSummary> {
  const r = await api.get<AnalyticsSummary>('/analytics');
  return r.data;
}

export interface HealthStatus {
  ocr_engine: boolean; tampering_engine: boolean;
  face_engine: boolean; risk_engine: boolean; database: boolean;
}
export async function getHealth(): Promise<HealthStatus> {
  const r = await api.get<HealthStatus>('/health');
  return r.data;
}

/* ── Blockchain evidence (additive) ── */
export const blockchainApi = {
  status: () =>
    api.get('/blockchain/status').then(r => r.data),
  evidence: (screeningId: string) =>
    api.get<BlockchainEvidence>(`/blockchain/${screeningId}`).then(r => r.data),
  verify: (screeningId: string) =>
    api.post<BlockchainVerifyResult>(`/blockchain/${screeningId}/verify`).then(r => r.data),
};

/* ── Auth (additive) ── */
export interface AuthOtpResponse {
  ok: boolean; otp_sent: boolean; dev_otp: string | null; message: string;
}
export interface AuthSession {
  ok: boolean; token: string; email: string; name: string | null;
}
export const authApi = {
  register: (email: string, password: string, name?: string) =>
    api.post<AuthOtpResponse>('/auth/register', { email, password, name }).then(r => r.data),
  login: (email: string, password: string) =>
    api.post<AuthOtpResponse>('/auth/login', { email, password }).then(r => r.data),
  verifyOtp: (email: string, code: string) =>
    api.post<AuthSession>('/auth/verify-otp', { email, code }).then(r => r.data),
  me: (token: string) =>
    api.get('/auth/me', { params: { token } }).then(r => r.data),
  google: (credential: string) =>
    api.post('/auth/google', { credential }).then(r => r.data),
  googleClientId: () =>
    api.get('/auth/google-client-id').then(r => r.data as { client_id: string }),
};

export default api;
