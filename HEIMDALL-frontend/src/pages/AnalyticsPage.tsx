import { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts';
import { getAnalytics } from '@/services/api';
import type { AnalyticsSummary } from '@/services/api';
import { Loader2 } from 'lucide-react';

const TOOLTIP_STYLE = {
  background: 'rgba(255,255,255,0.96)',
  border: '1px solid rgba(31,36,32,0.12)',
  borderRadius: 12,
  fontSize: 12,
  color: '#1F2420',
  boxShadow: '0 12px 32px -12px rgba(31,36,32,0.25)',
};

export default function AnalyticsPage() {
  const [data, setData]     = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAnalytics().then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex items-center gap-2.5 p-6 text-sm text-mist">
      <Loader2 size={15} className="animate-spin text-vigil-400" /> Loading analytics…
    </div>
  );
  if (!data)   return <p className="p-6 text-sm text-bad">Could not load analytics.</p>;

  const total = data.total_screened || 1;

  return (
    <div className="max-w-[920px]">
      {/* Stat cards */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label:'Total Screened',   value: data.total_screened,  color:'#3F4A32' },
          { label:'Passed',           value: data.passed,          color:'#356859' },
          { label:'Review Required',  value: data.review_required, color:'#C47A2C' },
          { label:'High Risk',        value: data.high_risk,       color:'#B54848' },
        ].map((s, i) => (
          <div key={s.label} className={`panel rise rise-${i + 1} p-5 text-center transition-transform duration-150 hover:-translate-y-0.5`}>
            <div className="font-display text-[34px] font-bold leading-none tabular-nums" style={{ color: s.color }}>{s.value}</div>
            <div className="mt-1.5 text-xs text-mist">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Activity bar chart */}
        <div className="panel rise rise-2 p-5">
          <div className="panel-title mb-4">Screening Activity (This Week)</div>
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={data.recent_trend} margin={{ top: 5, right: 5, left: -22, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(31,36,32,0.08)" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#8A9080', fontFamily: 'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#8A9080' }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(63,74,50,0.06)' }} />
              <Bar dataKey="count" name="Screenings" fill="#3F4A32" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Risk pie */}
        <div className="panel rise rise-2 p-5">
          <div className="panel-title mb-4">Risk Distribution</div>
          <ResponsiveContainer width="100%" height={210}>
            <PieChart>
              <Pie data={data.risk_distribution} cx="50%" cy="45%" innerRadius={58} outerRadius={84} paddingAngle={3} dataKey="value" stroke="transparent">
                {data.risk_distribution.map((e, i) => <Cell key={i} fill={e.color} />)}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend formatter={v => <span style={{ fontSize: 12, color: '#5A6153' }}>{v}</span>} iconSize={8} iconType="circle" />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Breakdown */}
      <div className="panel rise rise-3 p-5">
        <div className="panel-title mb-5">Breakdown by Decision</div>
        {[
          { label:'Passed',          value: data.passed,          color:'#356859' },
          { label:'Review Required', value: data.review_required, color:'#C47A2C' },
          { label:'High Risk',       value: data.high_risk,       color:'#B54848' },
        ].map(b => (
          <div key={b.label} className="mb-4 last:mb-0">
            <div className="mb-1.5 flex justify-between text-[13px]">
              <span className="font-medium text-mist-bright">{b.label}</span>
              <span className="font-mono tabular-nums text-mist">{b.value} ({((b.value / total) * 100).toFixed(1)}%)</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
              <div className="h-full rounded-full transition-all duration-700" style={{ width: `${(b.value / total) * 100}%`, background: b.color }} />
            </div>
          </div>
        ))}

        <div className="mt-5 flex gap-10 border-t border-white/[0.07] pt-4">
          <div>
            <div className="font-display text-[26px] font-bold leading-none text-vigil-300 tabular-nums">
              {data.avg_processing_time_ms > 0 ? `${(data.avg_processing_time_ms / 1000).toFixed(1)}s` : '—'}
            </div>
            <div className="mt-1 text-xs text-mist">Avg. processing time</div>
          </div>
          <div>
            <div className="font-display text-[26px] font-bold leading-none text-ok tabular-nums">
              {total > 0 ? `${((data.passed / total) * 100).toFixed(1)}%` : '—'}
            </div>
            <div className="mt-1 text-xs text-mist">Pass rate</div>
          </div>
        </div>
      </div>
    </div>
  );
}
