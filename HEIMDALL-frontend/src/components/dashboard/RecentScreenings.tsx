import { Link } from 'react-router-dom';
import type { ScreeningRecord } from '@/types';
import { riskColor, docTypeLabel, formatTs } from '@/utils';
import DecisionBadge from '@/components/ui/DecisionBadge';

export default function RecentScreenings({ records, loading }: { records: ScreeningRecord[]; loading?: boolean }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'14px 18px', borderBottom:'1px solid #e5e7eb' }}>
        <span style={{ fontWeight:700, fontSize:14 }}>Recent Screenings</span>
        <Link to="/history" style={{ fontSize:12, color:'#2563eb', textDecoration:'none' }}>View all →</Link>
      </div>
      {loading ? <div style={{ padding:20, color:'#9ca3af' }}>Loading…</div> : records.length === 0 ? (
        <div style={{ padding:'24px', textAlign:'center', color:'#9ca3af', fontSize:13 }}>No screenings yet.</div>
      ) : (
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:13 }}>
          <thead>
            <tr style={{ background:'#f9fafb' }}>
              {['ID','Type','Risk','Decision','Time'].map(h => (
                <th key={h} style={{ textAlign:'left', padding:'8px 14px', fontSize:11, fontWeight:600, color:'#6b7280', textTransform:'uppercase' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map(r => (
              <tr key={r.screening_id} style={{ borderBottom:'1px solid #f3f4f6' }}>
                <td style={{ padding:'9px 14px' }}>
                  <Link to={`/screening/${r.screening_id}`} style={{ color:'#2563eb', textDecoration:'none', fontFamily:'monospace', fontSize:11 }}>{r.screening_id}</Link>
                  {r.demo_mode && <span style={{ marginLeft:5, fontSize:10, background:'#f3e8ff', color:'#7e22ce', padding:'1px 5px', borderRadius:10 }}>demo</span>}
                </td>
                <td style={{ padding:'9px 14px', color:'#374151' }}>{docTypeLabel(r.document_type)}</td>
                <td style={{ padding:'9px 14px', fontWeight:700, color:riskColor(r.risk_score) }}>{r.risk_score}/100</td>
                <td style={{ padding:'9px 14px' }}><DecisionBadge decision={r.decision} size="sm"/></td>
                <td style={{ padding:'9px 14px', color:'#9ca3af', fontSize:11 }}>{formatTs(r.timestamp)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
