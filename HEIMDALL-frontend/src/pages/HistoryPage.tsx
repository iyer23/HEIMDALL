import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Trash2, RefreshCw, ScanLine } from 'lucide-react';
import { getScreenings, deleteScreening } from '@/services/api';
import type { ScreeningRecord, Decision } from '@/types';
import { riskColor, formatTs, docTypeLabel } from '@/utils';

function Badge({ d }: { d: Decision }) {
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

const FILTERS = [
  { label:'All',       value:'' },
  { label:'Pass',      value:'PASS' },
  { label:'Review',    value:'REVIEW_REQUIRED' },
  { label:'High Risk', value:'HIGH_RISK' },
];

export default function HistoryPage() {
  const [records, setRecords] = useState<ScreeningRecord[]>([]);
  const [total, setTotal]     = useState(0);
  const [filter, setFilter]   = useState('');
  const [page, setPage]       = useState(0);
  const [loading, setLoading] = useState(true);
  const PAGE = 15;

  const load = () => {
    setLoading(true);
    getScreenings({ limit: PAGE, offset: page * PAGE, decision: filter || undefined })
      .then(r => { setRecords(r.records); setTotal(r.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [filter, page]);

  const del = async (id: string) => {
    if (!confirm('Delete this record?')) return;
    await deleteScreening(id).catch(() => {});
    setRecords(r => r.filter(x => x.screening_id !== id));
    setTotal(t => t - 1);
  };

  return (
    <div className="max-w-[980px]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.14em] text-mist-dim">{total} total records</span>
        <div className="flex gap-2.5">
          <button onClick={load} className="btn-ghost !py-1.5 text-xs">
            <RefreshCw size={13} /> Refresh
          </button>
          <Link to="/screening/new" className="btn-primary !py-1.5 text-xs">
            <ScanLine size={13} /> New Screening
          </Link>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="tabbar mb-4">
        {FILTERS.map(f => (
          <button
            key={f.value}
            onClick={() => { setFilter(f.value); setPage(0); }}
            className={`tab ${filter === f.value ? 'tab-active' : ''}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="panel overflow-hidden">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="bg-white/[0.02]">
              {['Screening ID','Type','Risk Score','Decision','Timestamp',''].map(h => (
                <th key={h} className="eyebrow border-b border-white/[0.06] px-4 py-2.5 text-left">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="py-6 text-center text-mist-dim">Loading…</td></tr>
            ) : records.length === 0 ? (
              <tr><td colSpan={6} className="py-10 text-center text-mist-dim">No records found.</td></tr>
            ) : records.map(r => (
              <tr key={r.screening_id} className="group border-b border-white/[0.04] transition-colors last:border-0 hover:bg-white/[0.03]">
                <td className="px-4 py-3">
                  <Link to={`/screening/${r.screening_id}`} className="font-mono text-xs font-medium text-vigil-300 hover:text-vigil-200 hover:underline">
                    {r.screening_id}
                  </Link>
                  {r.demo_mode && (
                    <span className="ml-2 rounded border border-fuchsia-400/30 bg-fuchsia-400/10 px-1.5 py-px font-mono text-[9px] font-semibold uppercase tracking-wider text-fuchsia-300">
                      demo
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-mist-bright">{docTypeLabel(r.document_type)}</td>
                <td className="px-4 py-3 font-mono font-semibold tabular-nums" style={{ color: riskColor(r.risk_score) }}>
                  {r.risk_score}<span className="text-mist-dim">/100</span>
                </td>
                <td className="px-4 py-3"><Badge d={r.decision as Decision} /></td>
                <td className="px-4 py-3 text-xs text-mist-dim">{formatTs(r.timestamp)}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => del(r.screening_id)}
                    className="rounded p-1.5 text-mist-dim opacity-60 transition-all hover:bg-bad/10 hover:text-bad group-hover:opacity-100"
                  >
                    <Trash2 size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {total > PAGE && (
          <div className="flex items-center justify-between border-t border-white/[0.06] px-4 py-3 text-xs text-mist">
            <span className="font-mono">
              Showing {page * PAGE + 1}–{Math.min((page + 1) * PAGE, total)} of {total}
            </span>
            <div className="flex gap-2">
              <button onClick={() => setPage(p => p - 1)} disabled={page === 0} className="btn-ghost !px-3 !py-1 text-xs">← Prev</button>
              <button onClick={() => setPage(p => p + 1)} disabled={(page + 1) * PAGE >= total} className="btn-ghost !px-3 !py-1 text-xs">Next →</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
