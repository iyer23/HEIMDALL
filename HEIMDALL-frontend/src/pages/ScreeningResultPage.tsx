/**
 * HEIMDALL — Screening Result Page
 * Renders exclusively from the canonical backend result object.
 * No frontend risk recalculation. No invented values.
 */
import { useEffect, useState } from 'react';
import { useParams, useLocation, Link } from 'react-router-dom';
import {
  CheckCircle2, AlertTriangle, XCircle, Download,
  ArrowLeft, Shield, Info, ScanLine, Loader2, Link2, ShieldCheck, XOctagon,
} from 'lucide-react';
import { getScreening, downloadReport, blockchainApi } from '@/services/api';
import type {
  ScreeningResult, CheckStatus, MRZStatus, FaceStatus, ForensicsStatus,
  BlockchainEvidence, BlockchainVerifyResult,
} from '@/types';
import {
  riskColor, riskLabel, decisionColor, decisionLabel,
  formatTs, formatDuration, docTypeLabel,
  faceStatusColor, faceStatusLabel, faceIsMeaningful,
  mrzStatusColor, mrzStatusLabel,
  forensicsStatusColor, forensicsStatusLabel,
} from '@/utils';
import { FaceScanArt, FingerprintArt } from '@/components/art/Art';

function Sec({ title }: { title: string }) {
  return <div className="panel-title">{title}</div>;
}

function StatusIcon({ s }: { s: CheckStatus | string }) {
  if (s === 'PASS' || s === 'NOT_APPLICABLE') return <CheckCircle2 size={14} className="text-ok" />;
  if (s === 'WARNING') return <AlertTriangle size={14} className="text-warn" />;
  if (s === 'FAIL')    return <XCircle size={14} className="text-bad" />;
  return <Info size={14} className="text-mist-dim" />;
}

function SBadge({ s }: { s: string }) {
  const cfg: Record<string, string> = {
    PASS:           'border-ok/25 bg-ok/10 text-ok',
    WARNING:        'border-warn/25 bg-warn/10 text-warn',
    FAIL:           'border-bad/25 bg-bad/10 text-bad',
    NOT_APPLICABLE: 'border-white/10 bg-white/[0.04] text-mist',
  };
  return (
    <span className={`inline-block rounded-full border px-2 py-px font-mono text-[10px] font-semibold uppercase tracking-wider ${cfg[s] ?? 'border-white/10 bg-white/[0.04] text-mist'}`}>
      {s}
    </span>
  );
}

function DecisionBanner({ decision, score }: { decision: string; score: number }) {
  const c     = decisionColor(decision as any);
  const label = decisionLabel(decision as any);
  const Icon  = decision === 'PASS' ? CheckCircle2 : decision === 'REVIEW_REQUIRED' ? AlertTriangle : XCircle;
  return (
    <div
      className="inline-flex items-center gap-2.5 rounded-full px-5 py-2 font-display text-[19px] font-bold uppercase tracking-[0.1em]"
      style={{ background: `${c}14`, color: c, border: `1px solid ${c}45`, boxShadow: `0 0 24px ${c}18` }}
    >
      <Icon size={19} />{label}
    </div>
  );
}

export default function ScreeningResultPage() {
  const { id }   = useParams<{ id: string }>();
  const location = useLocation();
  const [result, setResult]   = useState<ScreeningResult | null>(location.state?.result ?? null);
  const [loading, setLoading] = useState(!result);
  const [dl, setDl]           = useState(false);
  const [bch, setBch]         = useState<BlockchainEvidence | null>(result?.blockchain ?? null);
  const [verifyRes, setVerifyRes] = useState<BlockchainVerifyResult | null>(null);
  const [verifying, setVerifying] = useState(false);

  useEffect(() => {
    if (!result && id) {
      getScreening(id).then(r => {
        setResult(r);
        if (r.blockchain) setBch(r.blockchain);
      }).catch(() => {}).finally(() => setLoading(false));
    }
  }, [id, result]);

  useEffect(() => {
    if (!bch && id) {
      blockchainApi.evidence(id).then(setBch).catch(() => {});
    }
  }, [bch, id]);

  const runVerify = async () => {
    if (!id) return;
    setVerifying(true);
    setVerifyRes(null);
    try {
      setVerifyRes(await blockchainApi.verify(id));
    } catch { /* handled via verdict UI below */ }
    finally { setVerifying(false); }
  };

  const handleDl = async () => {
    if (!id) return;
    setDl(true);
    try {
      const blob = await downloadReport(id);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url;
      a.download = `HEIMDALL_${id}_report.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { alert('Report generation failed.'); }
    finally { setDl(false); }
  };

  if (loading) return (
    <div className="flex items-center gap-2.5 p-6 text-sm text-mist">
      <Loader2 size={15} className="animate-spin text-vigil-400" /> Loading result…
    </div>
  );
  if (!result) return <p className="p-6 text-sm text-bad">Result not found.</p>;

  const { ocr, validation, mrz, tampering, face_verification: face, risk, evidence_fusion: ef } = result;
  const score    = risk.score;
  const decision = risk.decision;
  const bd       = risk.breakdown;

  // Decide which sections to show
  const showMRZ      = mrz.status !== 'NOT_APPLICABLE';
  const showFace     = face.status !== 'NOT_PROVIDED';
  const faceHasScore = faceIsMeaningful(face.status);

  return (
    <div className="max-w-[1000px]">
      {/* Breadcrumb */}
      <Link to="/history" className="rise group mb-4 inline-flex items-center gap-1.5 text-xs font-medium text-mist transition-colors hover:text-vigil-300">
        <ArrowLeft size={13} className="transition-transform group-hover:-translate-x-0.5" /> Back to History
      </Link>

      {/* ── Header card ── */}
      <div className="panel rise mb-4 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2.5">
              <Shield size={15} className="text-vigil-400" />
              <span className="font-mono text-xs tracking-wide text-mist">{result.screening_id}</span>
              {result.demo_mode && (
                <span className="rounded border border-fuchsia-400/30 bg-fuchsia-400/10 px-2 py-px font-mono text-[9px] font-semibold uppercase tracking-wider text-fuchsia-300">
                  demo / synthetic
                </span>
              )}
            </div>
            <DecisionBanner decision={decision} score={score} />
            <div className="mt-3.5 flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-mist">
              <span>Risk: <strong className="font-mono font-semibold tabular-nums" style={{ color: riskColor(score) }}>{score}/100</strong></span>
              <span>Type: <strong className="font-semibold text-white">{docTypeLabel(result.document_type)}</strong>
                {' '}({result.document_type_confidence.toFixed(1)}%)</span>
              <span className="text-mist-dim">{formatTs(result.timestamp)}</span>
              <span className="text-mist-dim">Processed in: <span className="font-mono">{formatDuration(result.processing_time_ms)}</span></span>
            </div>
            {risk.override_reason && (
              <div className="mt-3 flex items-center gap-2 rounded-lg border border-warn/25 bg-warn/[0.07] px-3 py-2 text-[11px] text-warn">
                <AlertTriangle size={13} />
                Decision override: {risk.override_reason}
              </div>
            )}
          </div>
          <button onClick={handleDl} disabled={dl} className="btn-ghost">
            {dl ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            {dl ? 'Generating…' : 'Download Report'}
          </button>
        </div>
      </div>

      {/* ── Module summary strip ── */}
      <div className={`mb-4 grid gap-3 rise rise-1 ${showMRZ && showFace ? 'grid-cols-2 md:grid-cols-5' : showMRZ || showFace ? 'grid-cols-2 md:grid-cols-4' : 'grid-cols-3'}`}>
        {[
          { label: 'OCR',        ok: ocr.ocr_available && ocr.overall_confidence >= 60, sub: ocr.ocr_available ? `${ocr.overall_confidence.toFixed(0)}% conf` : 'Unavailable' },
          { label: 'Validation', ok: validation.failed === 0, sub: `${validation.passed}✓ ${validation.warnings}⚠ ${validation.failed}✗` },
          ...(showMRZ ? [{ label: 'MRZ', ok: mrz.status === 'VALID', sub: mrzStatusLabel(mrz.status) }] : []),
          { label: 'Forensics',  ok: tampering.status === 'CLEAN', sub: forensicsStatusLabel(tampering.status) },
          ...(showFace ? [{ label: 'Face', ok: face.status === 'MATCH', sub: faceHasScore && face.match_score != null ? `${face.match_score.toFixed(0)}%` : faceStatusLabel(face.status) }] : []),
        ].map(m => (
          <div key={m.label} className="panel p-3.5 text-center transition-transform duration-150 hover:-translate-y-0.5">
            {m.ok
              ? <CheckCircle2 size={18} className="mx-auto mb-1.5 text-ok" />
              : <AlertTriangle size={18} className="mx-auto mb-1.5 text-warn" />}
            <div className="panel-title !text-[11px]">{m.label}</div>
            <div className="mt-1 text-[11px] text-mist-dim">{m.sub}</div>
          </div>
        ))}
      </div>

      {/* ── 2-column grid ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_310px]">
        {/* Left */}
        <div className="flex flex-col gap-4">

          {/* WHY FLAGGED */}
          {(ef.signals.some(s => s.contribution > 0) || score === 0) && (
            <div className="panel rise rise-2 border-l-[3px] !border-l-vigil-400 p-5">
              <Sec title="WHY FLAGGED — Evidence Fusion" />
              {ef.narrative && (
                <p className="mb-3 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3.5 py-2.5 text-xs leading-relaxed text-mist-bright">
                  {ef.narrative}
                </p>
              )}
              <div className="flex flex-col gap-1.5">
                {ef.signals.map((sig, i) => (
                  <div
                    key={i}
                    className={`flex items-start gap-3 rounded-lg border px-3 py-2 ${
                      sig.ok ? 'border-ok/20 bg-ok/[0.06]' : 'border-bad/25 bg-bad/[0.06]'
                    }`}
                  >
                    <span
                      className="min-w-[34px] shrink-0 text-right font-mono text-xs font-bold"
                      style={{ color: sig.contribution > 0 ? '#B54848' : '#356859' }}
                    >
                      {sig.contribution > 0 ? `+${sig.contribution}` : '✓'}
                    </span>
                    <div className="flex-1">
                      <div className="text-xs font-semibold text-white">{sig.label}</div>
                      <div className="mt-0.5 text-[11px] leading-relaxed text-mist">{sig.reason}</div>
                    </div>
                    <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-mist-dim">{sig.module}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* OCR Fields */}
          <div className="panel rise rise-2 p-5">
            <Sec title="Extracted Fields (OCR)" />
            {!ocr.ocr_available && (
              <div className="mb-3 rounded-lg border border-warn/25 bg-warn/[0.07] px-3 py-2 text-xs text-warn">
                ⚠ {ocr.error ?? 'OCR engine unavailable — text extraction could not be performed.'}
              </div>
            )}
            {ocr.overall_confidence > 0 && ocr.overall_confidence < 60 && (
              <div className="mb-3 rounded-lg border border-warn/25 bg-warn/[0.07] px-3 py-2 text-xs text-warn">
                ⚠ Low OCR confidence ({ocr.overall_confidence.toFixed(0)}%) — manual field verification recommended.
              </div>
            )}
            {ocr.fields.length === 0 ? (
              <p className="text-[13px] italic text-mist-dim">No fields could be extracted.</p>
            ) : (
              <div className="grid grid-cols-1 gap-x-8 gap-y-1.5 md:grid-cols-2">
                {ocr.fields.map(f => (
                  <div key={f.label} className="border-b border-white/[0.05] pb-2">
                    <div className="field-label mb-1">{f.label}</div>
                    <div className={`text-[13px] font-medium ${f.flagged ? 'text-bad' : 'text-white'}`}>
                      {f.value ?? <span className="italic text-mist-dim">Not detected</span>}
                    </div>
                    {f.detected && (
                      <div className="mt-1.5 h-[3px] overflow-hidden rounded-full bg-white/[0.06]">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{
                            width: `${Math.min(100, f.confidence)}%`,
                            background: f.confidence >= 80 ? '#34D399' : f.confidence >= 60 ? '#FBBF24' : '#F87171',
                          }}
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {ocr.raw_mrz && (
              <div className="mt-4 rounded-lg border border-white/[0.06] bg-ink-900/80 px-3 py-2.5">
                <div className="field-label mb-1.5">Raw MRZ</div>
                <div className="break-all font-mono text-[11px] leading-relaxed text-ok">{ocr.raw_mrz}</div>
              </div>
            )}
          </div>

          {/* Document Validation */}
          <div className="panel rise rise-2 p-5">
            <Sec title="Document Validation" />
            <table className="w-full border-collapse text-[13px]">
              <tbody>
                {validation.checks.map((c, i) => (
                  <tr key={i} className="border-b border-white/[0.05] last:border-0">
                    <td className="w-6 py-2.5"><StatusIcon s={c.status} /></td>
                    <td className="py-2.5 pr-3 font-medium text-white">{c.check_name}</td>
                    <td className="py-2.5 text-xs text-mist">{c.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* MRZ — only shown when applicable */}
          {showMRZ ? (
            <div className="panel rise rise-2 p-5">
              <div className="mb-3 flex flex-wrap items-center gap-2.5">
                <Sec title="MRZ Analysis (ICAO 9303)" />
                <span
                  className="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider"
                  style={{
                    color: mrzStatusColor(mrz.status),
                    background: `${mrzStatusColor(mrz.status)}14`,
                    border: `1px solid ${mrzStatusColor(mrz.status)}40`,
                  }}
                >
                  {mrzStatusLabel(mrz.status)}
                </span>
              </div>
              <p className="mb-3 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-2 text-xs leading-relaxed text-mist-bright">
                {mrz.summary}
              </p>

              {/* Parsed fields */}
              {mrz.mrz_present && mrz.parsed && Object.keys(mrz.parsed).length > 0 && (
                <div className="mb-3 grid grid-cols-1 gap-x-6 gap-y-1 md:grid-cols-2">
                  {([
                    ['Format',       mrz.parsed.format],
                    ['Full Name',    mrz.parsed.full_name],
                    ['Doc Number',   mrz.parsed.document_number],
                    ['Nationality',  mrz.parsed.nationality],
                    ['DOB',          mrz.parsed.date_of_birth],
                    ['Expiry',       mrz.parsed.expiry_date],
                    ['Sex',          mrz.parsed.sex],
                    ['Issuing State',mrz.parsed.issuing_state],
                  ] as [string, string | undefined][]).filter(([, v]) => v).map(([k, v]) => (
                    <div key={k} className="border-b border-white/[0.05] pb-1.5">
                      <div className="field-label">{k}</div>
                      <div className="font-mono text-xs font-medium text-white">{v}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Checksums */}
              {mrz.checks.length > 0 && (
                <>
                  <div className="eyebrow mb-1.5">Checksum Verification</div>
                  <table className="w-full border-collapse text-xs">
                    <tbody>
                      {mrz.checks.map((c, i) => (
                        <tr key={i} className="border-b border-white/[0.05] last:border-0">
                          <td className="w-5 py-2"><StatusIcon s={c.status} /></td>
                          <td className="py-2 pr-3 font-medium text-white">{c.check_name}</td>
                          <td className="py-2 text-[11px] text-mist">{c.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}

              {/* Cross-validation */}
              {mrz.cross_validation.length > 0 && (
                <>
                  <div className="eyebrow mb-1.5 mt-4">OCR / MRZ Cross-Validation</div>
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="bg-white/[0.02]">
                        {['Field', 'OCR Value', 'MRZ Value', 'Status'].map(h => (
                          <th key={h} className="field-label px-2.5 py-2 text-left">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {mrz.cross_validation.map((cv, i) => (
                        <tr key={i} className="border-b border-white/[0.05] last:border-0">
                          <td className="px-2.5 py-2 font-medium text-white">{cv.field}</td>
                          <td className="px-2.5 py-2 font-mono text-[11px] text-mist-bright">{cv.ocr_val}</td>
                          <td className="px-2.5 py-2 font-mono text-[11px] text-mist-bright">{cv.mrz_val}</td>
                          <td className="px-2.5 py-2"><SBadge s={cv.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>
          ) : (
            <div className="panel rise rise-2 flex items-center gap-2.5 bg-white/[0.02] p-5 text-[13px] text-mist">
              <Info size={14} className="shrink-0 text-mist-dim" />
              <span><strong className="text-white">MRZ:</strong> Not applicable for {docTypeLabel(result.document_type)} documents. MRZ checks were skipped.</span>
            </div>
          )}

          {/* Forensics */}
          <div className="panel rise rise-2 p-5">
            <div className="mb-3 flex flex-wrap items-center gap-2.5">
              <Sec title="Image Forensic Analysis" />
              <span className="text-[#3F4A32]"><FingerprintArt size={18} /></span>
              <span
                className="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider"
                style={{
                  color: forensicsStatusColor(tampering.status),
                  background: `${forensicsStatusColor(tampering.status)}14`,
                  border: `1px solid ${forensicsStatusColor(tampering.status)}40`,
                }}
              >
                {forensicsStatusLabel(tampering.status)}
              </span>
              {tampering.overall_confidence > 0 && (
                <span className="font-mono text-[11px] text-mist-dim">({tampering.overall_confidence.toFixed(0)}% anomaly confidence)</span>
              )}
            </div>

            {result.demo_mode && (
              <div className="mb-3 rounded-lg border border-fuchsia-400/25 bg-fuchsia-400/[0.07] px-3 py-2 text-[11px] text-fuchsia-300">
                DEMO ANALYSIS — Forensic results are pre-configured synthetic data.
              </div>
            )}

            {tampering.interpretation && (
              <p className="mb-3 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-2 text-xs leading-relaxed text-mist-bright">
                {tampering.interpretation}
              </p>
            )}

            {tampering.regions.map((r, i) => (
              <div key={i} className="mb-2 rounded-lg border border-bad/25 bg-bad/[0.06] px-3 py-2 last:mb-0">
                <div className="text-xs font-semibold text-bad">{r.label} — <span className="font-mono">{r.confidence.toFixed(0)}%</span> confidence</div>
                <div className="mt-0.5 text-[11px] text-mist">{r.reason}</div>
              </div>
            ))}

            {tampering.metadata_flags.length > 0 && (
              <div className="mt-3">
                <div className="eyebrow mb-1.5">Metadata ({tampering.metadata_status})</div>
                {tampering.metadata_flags.map((f, i) => (
                  <div key={i} className="py-0.5 text-xs text-warn">• {f}</div>
                ))}
              </div>
            )}

            {tampering.metadata_status === 'ABSENT' && tampering.metadata_flags.length === 0 && (
              <div className="mt-3 text-xs italic text-mist-dim">
                EXIF metadata absent — this is normal for shared/uploaded images and does not indicate tampering.
              </div>
            )}
          </div>

          {/* Face Verification */}
          {showFace ? (
            <div className="panel rise rise-2 p-5">
              <div className="mb-3 flex flex-wrap items-center gap-2.5">
                <Sec title="Face Verification" />
                <span className="text-[#3F4A32]"><FaceScanArt size={18} /></span>
              </div>
              <div className="mb-3 flex items-center gap-4">
                {faceHasScore && face.match_score != null ? (
                  <div className="font-display text-[34px] font-bold leading-none tabular-nums" style={{ color: faceStatusColor(face.status) }}>
                    {face.match_score.toFixed(1)}%
                  </div>
                ) : null}
                <div>
                  <div className="text-sm font-semibold" style={{ color: faceStatusColor(face.status) }}>
                    {faceStatusLabel(face.status)}
                  </div>
                  <div className="mt-0.5 text-xs text-mist">{face.message}</div>
                </div>
              </div>
              {faceHasScore && face.match_score != null && (
                <>
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{ width: `${face.match_score}%`, background: faceStatusColor(face.status) }}
                    />
                  </div>
                  <div className="mt-1.5 font-mono text-[10px] text-mist-dim">
                    Threshold used: {(face.threshold_used * 100).toFixed(0)}% (distance ≤ {face.threshold_used})
                  </div>
                </>
              )}
              <p className="mt-3 text-[11px] italic text-mist-dim">
                Face similarity is a supporting indicator only and does not independently prove identity.
              </p>
            </div>
          ) : (
            <div className="panel rise rise-2 flex items-center gap-2.5 bg-white/[0.02] p-5 text-[13px] text-mist">
              <Info size={14} className="shrink-0 text-mist-dim" />
              <span>No reference photograph was provided. Face comparison was not performed.</span>
            </div>
          )}
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-4">
          {/* Risk score */}
          <div className="panel rise rise-3 p-5">
            <Sec title="Risk Score" />
            <div className="mb-4 text-center">
              <div className="font-display text-[52px] font-bold leading-none tabular-nums" style={{ color: riskColor(score) }}>
                {score}
              </div>
              <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-mist-dim">out of 100</div>
              <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-white/[0.06]">
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{ width: `${score}%`, background: riskColor(score), boxShadow: `0 0 12px ${riskColor(score)}66` }}
                />
              </div>
              <div className="mt-2 font-display text-sm font-semibold uppercase tracking-[0.12em]" style={{ color: riskColor(score) }}>
                {riskLabel(score)}
              </div>
            </div>

            {/* Category breakdown */}
            {bd && (
              <>
                <div className="eyebrow mb-2.5">Score Breakdown</div>
                {(Object.entries(bd) as [string, any][]).filter(([k]) => k !== 'total').map(([k, v]) => (
                  <div key={k} className="mb-1.5 flex items-center gap-2.5">
                    <span className="w-[74px] shrink-0 text-[11px] capitalize text-mist">{k}</span>
                    <div className="h-[5px] flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${(v.points / v.cap) * 100}%`, background: v.points > 0 ? riskColor(v.points * 5) : 'rgba(255,255,255,0.14)' }}
                      />
                    </div>
                    <span className={`w-8 text-right font-mono text-[11px] tabular-nums ${v.points > 0 ? 'text-bad' : 'text-mist-dim'}`}>
                      {v.points > 0 ? `+${v.points}` : '0'}
                    </span>
                    <span className="w-6 font-mono text-[10px] text-mist-dim">/{v.cap}</span>
                  </div>
                ))}
                <div className="mt-2.5 flex justify-between border-t border-white/[0.07] pt-2.5 font-display text-[15px] font-semibold uppercase tracking-[0.1em]">
                  <span className="text-mist-bright">Total</span>
                  <span style={{ color: riskColor(score) }}>{score}/100</span>
                </div>
              </>
            )}
          </div>

          {/* Risk factors detail */}
          <div className="panel rise rise-3 p-5">
            <Sec title="Contributing Factors" />
            {risk.factors.filter(f => f.points > 0).length === 0 ? (
              <p className="text-xs italic text-mist">No risk factors — all checks passed.</p>
            ) : (
              risk.factors.filter(f => f.points > 0).map((f, i) => (
                <div key={i} className="flex items-start gap-2.5 border-b border-white/[0.05] py-2 last:border-0">
                  <span className="min-w-[30px] shrink-0 font-mono text-xs font-bold text-bad">+{f.points}</span>
                  <div>
                    <div className="text-xs font-semibold text-white">{f.label}</div>
                    <div className="mt-0.5 text-[11px] leading-relaxed text-mist-dim">{f.description}</div>
                  </div>
                </div>
              ))
            )}
            {/* Clean factors */}
            {risk.factors.filter(f => f.points === 0).slice(0, 4).map((f, i) => (
              <div key={i} className="flex items-center gap-2.5 border-b border-white/[0.05] py-1.5 last:border-0">
                <span className="min-w-[30px] shrink-0 font-mono text-xs font-bold text-ok">✓</span>
                <span className="text-xs text-mist">{f.label}</span>
              </div>
            ))}
          </div>

          {/* Blockchain Evidence */}
          <div className="panel rise rise-3 p-5">
            <div className="mb-3 flex flex-wrap items-center gap-2.5">
              <Sec title="Blockchain Evidence" />
              <Link2 size={15} className="text-vigil-400" />
              {bch && (
                <span
                  className="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider"
                  style={{
                    color: bch.status.startsWith('REGISTERED') || bch.status.startsWith('DEMO_REGISTERED')
                      ? '#356859' : bch.status === 'FAILED' ? '#B54848' : '#C47A2C',
                    background: (bch.status.startsWith('REGISTERED') || bch.status.startsWith('DEMO_REGISTERED'))
                      ? '#35685914' : bch.status === 'FAILED' ? '#B5484814' : '#C47A2C14',
                    border: `1px solid ${bch.status.startsWith('REGISTERED') || bch.status.startsWith('DEMO_REGISTERED')
                      ? '#35685940' : bch.status === 'FAILED' ? '#B5484840' : '#C47A2C40'}`,
                  }}
                >
                  {bch.status === 'DEMO_REGISTERED' ? 'Anchored · Demo' : bch.status.replace(/_/g, ' ').toLowerCase()}
                </span>
              )}
            </div>

            {bch ? (
              <>
                {bch.mode !== 'sepolia' && (
                  <div className="mb-3 rounded-lg border border-fuchsia-400/25 bg-fuchsia-400/[0.07] px-3 py-2 text-[11px] text-fuchsia-300">
                    DEMO BLOCKCHAIN — a simulated ledger is used because no network
                    configuration is present. No real transaction is claimed.
                  </div>
                )}
                <div className="flex flex-col gap-1.5">
                  <div className="border-b border-white/[0.05] pb-1.5">
                    <div className="field-label">Network</div>
                    <div className="text-[13px] font-medium text-white">{bch.network_label}</div>
                  </div>
                  <div className="border-b border-white/[0.05] pb-1.5">
                    <div className="field-label">Screening ID</div>
                    <div className="font-mono text-xs font-medium text-white">{bch.screening_id || id}</div>
                  </div>
                  {bch.result_hash && (
                    <div className="border-b border-white/[0.05] pb-1.5">
                      <div className="field-label">Result Hash (SHA-256)</div>
                      <div className="break-all font-mono text-[11px] text-ok" title={bch.result_hash}>
                        {bch.result_hash}
                      </div>
                    </div>
                  )}
                  {bch.tx_hash && (
                    <div className="border-b border-white/[0.05] pb-1.5">
                      <div className="field-label">Transaction Hash</div>
                      {bch.explorer_url ? (
                        <a href={bch.explorer_url} target="_blank" rel="noreferrer"
                           className="break-all font-mono text-[11px] text-vigil-300 underline decoration-vigil-300/30 underline-offset-2 hover:decoration-vigil-300">
                          {bch.tx_hash}
                        </a>
                      ) : (
                        <div className="break-all font-mono text-[11px] text-mist-bright" title={bch.tx_hash}>
                          {bch.tx_hash}
                        </div>
                      )}
                    </div>
                  )}
                  {bch.block_number != null && (
                    <div className="border-b border-white/[0.05] pb-1.5">
                      <div className="field-label">Block</div>
                      <div className="font-mono text-xs text-white">{bch.block_number}</div>
                    </div>
                  )}
                  <div className="border-b border-white/[0.05] pb-1.5">
                    <div className="field-label">Anchored At</div>
                    <div className="text-[13px] text-white">{formatTs(bch.registered_at)}</div>
                  </div>
                </div>

                <button onClick={runVerify} disabled={verifying} className="btn-ghost mt-4 w-full py-2.5">
                  {verifying
                    ? <><Loader2 size={14} className="animate-spin" /> Verifying…</>
                    : <><ShieldCheck size={14} /> Verify Integrity</>}
                </button>

                {verifyRes && (
                  <div
                    className="mt-3 rounded-lg px-3 py-2.5 text-[11px] leading-relaxed"
                    style={{
                      border: `1px solid ${verifyRes.verdict === 'VERIFIED' ? '#35685955' : verifyRes.verdict === 'MISMATCH' ? '#B5484855' : '#C47A2C55'}`,
                      background: verifyRes.verdict === 'VERIFIED' ? '#3568590f' : verifyRes.verdict === 'MISMATCH' ? '#B548480f' : '#C47A2C0f',
                      color: verifyRes.verdict === 'VERIFIED' ? '#356859' : verifyRes.verdict === 'MISMATCH' ? '#B54848' : '#C47A2C',
                    }}
                  >
                    <div className="mb-1 flex items-center gap-1.5 font-display text-[12px] font-bold uppercase tracking-[0.1em]">
                      {verifyRes.verdict === 'VERIFIED' ? <ShieldCheck size={14} />
                       : verifyRes.verdict === 'MISMATCH' ? <XOctagon size={14} />
                       : <AlertTriangle size={14} />}
                      {verifyRes.verdict.replace('_', ' ')}
                    </div>
                    {verifyRes.message}
                    {verifyRes.onchain_hash && verifyRes.onchain_hash !== verifyRes.computed_hash && (
                      <div className="mt-1.5 break-all font-mono text-[10px] text-mist">
                        Anchored: {verifyRes.onchain_hash}
                      </div>
                    )}
                  </div>
                )}

                <p className="mt-3 text-[10.5px] italic leading-relaxed text-mist-dim">
                  Blockchain anchoring provides tamper-evident integrity for the screening
                  record only — it does not prove that a document is genuine. Only the hash,
                  screening ID, score, decision and timestamp are stored on-chain; never
                  images, OCR text or personal data.
                </p>
              </>
            ) : (
              <p className="text-[13px] italic text-mist-dim">
                No blockchain evidence is available for this record.
              </p>
            )}
          </div>

          {/* Actions */}
          <div className="rise rise-4">
            <Link to="/screening/new" className="btn-primary w-full">
              <ScanLine size={15} /> New Screening
            </Link>
          </div>

          {/* Disclaimer */}
          <div className="rise rise-4 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3.5 py-3 text-[11px] leading-relaxed text-mist">
            <strong className="text-mist-bright">Disclaimer:</strong> HEIMDALL is an automated screening aid. Results are probabilistic
            indicators and are not proof of identity, authenticity, fraud, or document forgery.
            Final decisions must be made by authorised human reviewers.
          </div>
        </div>
      </div>
    </div>
  );
}
