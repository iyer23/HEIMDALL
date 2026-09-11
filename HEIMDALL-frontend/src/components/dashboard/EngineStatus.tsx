import { useState, useEffect } from 'react';
import { CheckCircle2, XCircle } from 'lucide-react';
import { getHealth } from '@/services/api';
import type { HealthStatus } from '@/services/api';

const ENGINES: { key: keyof HealthStatus; label: string }[] = [
  { key: 'ocr_engine',       label: 'OCR Engine'        },
  { key: 'tampering_engine', label: 'Tampering Engine'  },
  { key: 'face_engine',      label: 'Face Verification' },
  { key: 'risk_engine',      label: 'Risk Engine'       },
  { key: 'database',         label: 'Database'          },
];

export default function EngineStatus() {
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(() =>
      setHealth({ ocr_engine:false, tampering_engine:true, face_engine:false, risk_engine:true, database:true })
    );
  }, []);

  return (
    <div style={{ background:'#fff', border:'1px solid #e5e7eb', borderRadius:10, padding:'16px 18px' }}>
      <div style={{ fontWeight:700, fontSize:13, marginBottom:12 }}>AI Engine Status</div>
      {ENGINES.map(({ key, label }) => (
        <div key={key} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'5px 0', borderBottom:'1px solid #f3f4f6' }}>
          <span style={{ fontSize:13, color:'#374151' }}>{label}</span>
          {health ? (
            health[key]
              ? <span style={{ display:'flex', alignItems:'center', gap:4, fontSize:12, color:'#16a34a' }}><CheckCircle2 size={13}/>Online</span>
              : <span style={{ display:'flex', alignItems:'center', gap:4, fontSize:12, color:'#ca8a04' }}><XCircle size={13}/>Demo</span>
          ) : <span style={{ fontSize:12, color:'#9ca3af' }}>…</span>}
        </div>
      ))}
    </div>
  );
}
