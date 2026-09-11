import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getScreenings, getAnalytics } from '@/services/api';
import type { ScreeningRecord } from '@/types';
import { riskColor, formatTs, docTypeLabel } from '@/utils';
import { ShieldCheck, ShieldAlert, ScanSearch, FileSearch, ArrowUpRight } from 'lucide-react';

function Badge({ d }: { d: string }) {
  if (d === 'PASS') return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-ok/25 bg-ok/10 px-2.5 py-0.5 text-[11px] font-semibold text-ok">
      <span className="h-1 w-1 rounded-full bg-ok" />Pass
    </span>
  );
  if (d === 'REVIEW_REQUIRED') return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-warn/25 bg-warn/10 px-2.5 py-0.5 text-[11px] font-semibold text-warn">
      <span className="h-1 w-1 rounded-full bg-warn" />Review
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-bad/25 bg-bad/10 px-2.5 py-0.5 text-[11px] font-semibold text-bad">
      <span className="h-1 w-1 rounded-full bg-bad" />High Risk
    </span>
  );
}

export default function DashboardPage() {
  const [records, setRecords] = useState<ScreeningRecord[]>([]);
  const [stats, setStats]     = useState({ total:0, passed:0, review:0, high:0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getScreenings({ limit: 10 }), getAnalytics()])
      .then(([s, a]) => {
        setRecords(s.records);
        setStats({ total: a.total_screened, passed: a.passed, review: a.review_required, high: a.high_risk });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-[980px]">
      {/* Stats */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label:'Total Screened',  value: stats.total,  icon: ScanSearch,   cls: 'text-mist-bright', ring: 'ring-white/10' },
          { label:'Passed',          value: stats.passed, icon: ShieldCheck,  cls: 'text-ok',          ring: 'ring-ok/25' },
          { label:'Review Required', value: stats.review, icon: FileSearch,   cls: 'text-warn',        ring: 'ring-warn/25' },
          { label:'High Risk',       value: stats.high,   icon: ShieldAlert,  cls: 'text-bad',         ring: 'ring-bad/25' },
        ].map((s, i) => (
          <div key={s.label} className={`panel rise rise-${i + 1} group p-5 transition-transform duration-150 hover:-translate-y-0.5`}>
            <div className="flex items-start justify-between">
              <div className={`flex h-9 w-9 items-center justify-center rounded-lg bg-white/[0.04] ring-1 ring-inset ${s.ring}`}>
                <s.icon size={17} className={s.cls} />
              </div>
              <span className="eyebrow pt-1">/{i + 1}</span>
            </div>
            <div className={`mt-4 font-display text-[34px] font-bold leading-none tabular-nums ${s.cls}`}>
              {loading ? '—' : s.value}
            </div>
            <div className="mt-1.5 text-xs text-mist">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Recent screenings */}
      <div className="panel rise rise-3 overflow-hidden">
        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
          <span className="panel-title">Recent Screenings</span>
          <Link to="/history" className="group inline-flex items-center gap-1 text-[13px] font-medium text-vigil-300 hover:text-vigil-200">
            View all
            <ArrowUpRight size={14} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </Link>
        </div>
        {loading ? (
          <div className="p-6 text-[13px] text-mist-dim">Loading…</div>
        ) : records.length === 0 ? (
          <div className="px-6 py-12 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-white/[0.04] ring-1 ring-inset ring-white/10">
              <ScanSearch size={20} className="text-mist-dim" />
            </div>
            <div className="mb-4 text-[13px] text-mist">No screenings yet.</div>
            <Link to="/screening/new" className="btn-primary">Start a Screening</Link>
          </div>
        ) : (
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="bg-white/[0.02]">
                {['Screening ID','Document Type','Risk','Decision','Timestamp'].map(h => (
                  <th key={h} className="eyebrow border-b border-white/[0.06] px-5 py-2.5 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {records.map(r => (
                <tr key={r.screening_id} className="border-b border-white/[0.04] transition-colors last:border-0 hover:bg-white/[0.03]">
                  <td className="px-5 py-3">
                    <Link to={`/screening/${r.screening_id}`} className="font-mono text-xs font-medium text-vigil-300 hover:text-vigil-200 hover:underline">
                      {r.screening_id}
                    </Link>
                    {r.demo_mode && (
                      <span className="ml-2 rounded border border-fuchsia-400/30 bg-fuchsia-400/10 px-1.5 py-px font-mono text-[9px] font-semibold uppercase tracking-wider text-fuchsia-300">
                        demo
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-mist-bright">{docTypeLabel(r.document_type)}</td>
                  <td className="px-5 py-3 font-mono font-semibold tabular-nums" style={{ color: riskColor(r.risk_score) }}>
                    {r.risk_score}<span className="text-mist-dim">/100</span>
                  </td>
                  <td className="px-5 py-3"><Badge d={r.decision} /></td>
                  <td className="px-5 py-3 text-xs text-mist-dim">{formatTs(r.timestamp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
