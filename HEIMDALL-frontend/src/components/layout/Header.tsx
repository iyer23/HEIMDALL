import { useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { getHealth } from '@/services/api';

const TITLES: Record<string, string> = {
  '/dashboard':     'Dashboard',
  '/screening/new': 'New Screening',
  '/history':       'Screening History',
  '/analytics':     'Analytics',
};

export default function Header() {
  const { pathname } = useLocation();
  const title = TITLES[pathname] ?? 'HEIMDALL';
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    getHealth()
      .then(() => setOnline(true))
      .catch(() => setOnline(false));
    const t = setInterval(() => {
      getHealth().then(() => setOnline(true)).catch(() => setOnline(false));
    }, 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-[rgba(31,36,32,0.10)] bg-[rgba(248,249,246,0.8)] px-6 backdrop-blur-xl">
      <h1 className="font-display text-[17px] font-semibold uppercase tracking-[0.16em] text-[#1F2420]">
        {title}
      </h1>
      <div className="flex items-center gap-3">
        {online !== null && (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] ${
              online
                ? 'border-ok/30 bg-ok/10 text-ok'
                : 'border-warn/30 bg-warn/10 text-warn'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${online ? 'bg-ok pulse-dot' : 'bg-warn'}`} />
            {online ? 'AI Engine Online' : 'Demo Mode'}
          </span>
        )}
        <span className="font-mono text-[10px] tracking-[0.14em] text-mist-dim">HEIMDALL v1.0</span>
      </div>
    </header>
  );
}
