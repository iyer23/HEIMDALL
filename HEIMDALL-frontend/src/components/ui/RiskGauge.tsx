import { riskColor } from '@/utils';

interface RiskGaugeProps { score: number; size?: number; }

export default function RiskGauge({ score, size = 120 }: RiskGaugeProps) {
  const color = riskColor(score);
  const label = score > 60 ? 'High Risk' : score > 30 ? 'Review' : 'Pass';
  return (
    <div style={{ textAlign: 'center', width: size }}>
      <div style={{ fontSize: size * 0.28, fontWeight: 700, color }}>{score}</div>
      <div style={{ fontSize: size * 0.1, color: '#6b7280', marginTop: 2 }}>/100</div>
      <div style={{ height: 6, background: '#f3f4f6', borderRadius: 3, marginTop: 6 }}>
        <div style={{ height: '100%', width: `${score}%`, background: color, borderRadius: 3 }} />
      </div>
      <div style={{ fontSize: size * 0.09, color, fontWeight: 600, marginTop: 4 }}>{label}</div>
    </div>
  );
}
