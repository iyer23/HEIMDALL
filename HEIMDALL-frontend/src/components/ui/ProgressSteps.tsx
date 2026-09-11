import { CheckCircle2, Circle, AlertCircle, Loader2 } from 'lucide-react';

interface Step { id: string; label: string; status: 'pending' | 'running' | 'done' | 'error'; duration_ms?: number; }

export default function ProgressSteps({ steps }: { steps: Step[] }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {steps.map(s => (
        <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {s.status === 'pending' && <Circle size={16} color="#d1d5db" />}
          {s.status === 'running' && <Loader2 size={16} color="#2563eb" className="animate-spin" />}
          {s.status === 'done'    && <CheckCircle2 size={16} color="#16a34a" />}
          {s.status === 'error'   && <AlertCircle size={16} color="#dc2626" />}
          <span style={{ fontSize: 13, color: s.status === 'pending' ? '#9ca3af' : s.status === 'running' ? '#2563eb' : '#374151' }}>
            {s.label}
          </span>
          {s.duration_ms != null && s.status === 'done' && (
            <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 'auto' }}>{s.duration_ms}ms</span>
          )}
        </div>
      ))}
    </div>
  );
}
