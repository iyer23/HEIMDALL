/**
 * HEIMDALL — lightweight custom SVG artwork.
 * Minimal line vectors, stroke = currentColor, subtle CSS animations.
 */

export function DocScanArt({ size = 96, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 96 96" fill="none" className={className} aria-hidden="true">
      {/* document */}
      <rect x="24" y="12" width="48" height="72" rx="6" stroke="currentColor" strokeWidth="2.5" />
      {/* photo box */}
      <rect x="32" y="22" width="16" height="20" rx="2.5" stroke="currentColor" strokeWidth="2" opacity="0.55" />
      <circle cx="40" cy="30" r="3.5" stroke="currentColor" strokeWidth="2" opacity="0.55" />
      <path d="M34 39c1.5-3.5 10.5-3.5 12 0" stroke="currentColor" strokeWidth="2" opacity="0.55" strokeLinecap="round" />
      {/* text lines */}
      <line x1="54" y1="26" x2="66" y2="26" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" opacity="0.55" />
      <line x1="54" y1="33" x2="64" y2="33" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" opacity="0.4" />
      <line x1="32" y1="50" x2="64" y2="50" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" opacity="0.55" />
      <line x1="32" y1="57" x2="60" y2="57" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" opacity="0.4" />
      <line x1="32" y1="64" x2="64" y2="64" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" opacity="0.4" />
      <line x1="32" y1="71" x2="52" y2="71" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" opacity="0.3" />
      {/* animated scan line */}
      <g className="art-scanline">
        <line x1="22" y1="0" x2="74" y2="0" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="26" y1="0" x2="30" y2="0" stroke="currentColor" strokeWidth="4" strokeLinecap="round" opacity="0.4" />
        <line x1="66" y1="0" x2="70" y2="0" stroke="currentColor" strokeWidth="4" strokeLinecap="round" opacity="0.4" />
      </g>
    </svg>
  );
}

export function ShieldArt({ size = 28, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" fill="none" className={className} aria-hidden="true">
      <path
        d="M14 2.5 24 6v7c0 6.2-4.2 10.7-10 12.5C8.2 23.7 4 19.2 4 13V6l10-3.5Z"
        stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round"
      />
      <path d="m9.5 13.5 3 3 6-6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function FaceScanArt({ size = 40, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" className={className} aria-hidden="true">
      <path d="M4 12V8a4 4 0 0 1 4-4h4" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M28 4h4a4 4 0 0 1 4 4v4" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M36 28v4a4 4 0 0 1-4 4h-4" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M12 36H8a4 4 0 0 1-4-4v-4" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="15" cy="17" r="1.6" fill="currentColor" />
      <circle cx="25" cy="17" r="1.6" fill="currentColor" />
      <path d="M15 25c2.8 2.4 7.2 2.4 10 0" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M20 12v4" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.5" />
    </svg>
  );
}

export function FingerprintArt({ size = 40, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" className={className} aria-hidden="true">
      <path d="M20 6c-7.7 0-14 6.3-14 14 0 3 .5 5.6 1.4 8" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.9" />
      <path d="M34 20c0-7.7-6.3-14-14-14" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.45" />
      <path d="M11 20a9 9 0 0 1 18 0c0 4.4-.7 8.6-2 12" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.75" />
      <path d="M20 14a6 6 0 0 0-6 6c0 4.6.6 8.8 1.8 12" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.6" />
      <path d="M26 20a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.4" />
      <path d="M20 22v10" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.8" />
    </svg>
  );
}

export function OcrArt({ size = 40, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" className={className} aria-hidden="true">
      <rect x="6" y="6" width="28" height="28" rx="4" stroke="currentColor" strokeWidth="2.2" />
      <line x1="12" y1="14" x2="24" y2="14" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      <line x1="12" y1="20" x2="28" y2="20" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" opacity="0.55" />
      <line x1="12" y1="26" x2="20" y2="26" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" opacity="0.35" />
      <path d="M28 24l3 3 5-5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" transform="translate(-4 4)" />
    </svg>
  );
}

export function RiskGaugeArt({ size = 40, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" className={className} aria-hidden="true">
      <path d="M8 28a12 12 0 0 1 24 0" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.35" />
      <path d="M8 28a12 12 0 0 1 7.5-11.1" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <line x1="20" y1="28" x2="26.5" y2="21.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="20" cy="28" r="2.2" fill="currentColor" />
    </svg>
  );
}
