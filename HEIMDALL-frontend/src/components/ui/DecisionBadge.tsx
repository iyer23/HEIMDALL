import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';
import type { Decision } from '@/types';

interface DecisionBadgeProps { decision: Decision; size?: 'sm' | 'md' | 'lg'; }

const LABEL: Record<Decision, string> = {
  PASS: 'PASS', REVIEW_REQUIRED: 'REVIEW REQUIRED', HIGH_RISK: 'HIGH RISK',
};

export default function DecisionBadge({ decision, size = 'md' }: DecisionBadgeProps) {
  const isPass = decision === 'PASS';
  const isReview = decision === 'REVIEW_REQUIRED';
  const color = isPass ? '#16a34a' : isReview ? '#ca8a04' : '#dc2626';
  const bg    = isPass ? '#dcfce7' : isReview ? '#fef9c3' : '#fee2e2';
  const Icon  = isPass ? CheckCircle2 : isReview ? AlertTriangle : XCircle;
  const pad   = size === 'sm' ? '2px 8px' : size === 'lg' ? '6px 16px' : '4px 12px';
  const fs    = size === 'sm' ? 11 : size === 'lg' ? 15 : 13;
  return (
    <span style={{ display:'inline-flex', alignItems:'center', gap:5, background:bg, color, fontWeight:700, fontSize:fs, padding:pad, borderRadius:20 }}>
      <Icon size={fs} />{LABEL[decision]}
    </span>
  );
}
