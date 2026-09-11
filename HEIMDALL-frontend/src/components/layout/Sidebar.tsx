import { NavLink } from 'react-router-dom';
import { LayoutDashboard, ScanLine, History, BarChart2, LogOut } from 'lucide-react';
import { ShieldArt } from '@/components/art/Art';

const nav = [
  { to: '/dashboard',     icon: LayoutDashboard, label: 'Dashboard'      },
  { to: '/screening/new', icon: ScanLine,         label: 'New Screening'  },
  { to: '/history',       icon: History,          label: 'History'        },
  { to: '/analytics',     icon: BarChart2,        label: 'Analytics'      },
];

export default function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 z-50 flex w-60 flex-col border-r border-[rgba(31,36,32,0.15)] bg-[#3F4A32]">
      {/* Brand */}
      <div className="border-b border-white/10 px-5 py-[18px]">
        <div className="flex items-center gap-3">
          <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#F8F9F6] shadow-md">
            <ShieldArt size={20} className="text-[#3F4A32]" />
          </div>
          <div>
            <div className="font-display text-[19px] font-bold uppercase leading-none tracking-[0.18em] text-[#F8F9F6]">
              Heimdall
            </div>
            <div className="mt-1 font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-[#C9D1C0]">
              Identity Screening
            </div>
          </div>
        </div>
      </div>

      {/* Nav links */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {nav.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] transition-all duration-150 ${
                isActive
                  ? 'bg-[#F8F9F6] font-semibold text-[#3F4A32] shadow-sm'
                  : 'font-medium text-[#DDE2D6] hover:bg-white/10 hover:text-white'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={`absolute left-0 top-1/2 h-5 w-[2.5px] -translate-y-1/2 rounded-full transition-opacity ${
                    isActive ? 'bg-[#3F4A32] opacity-100' : 'opacity-0'
                  }`}
                />
                <Icon size={16} className={isActive ? 'text-[#3F4A32]' : 'text-[#C9D1C0] group-hover:text-white'} />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-white/10 px-5 py-3.5">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-[#C9D1C0]">
              PS 26188 · MHA · SSB
            </div>
            <div className="mt-1 text-[10px] text-[#9FAB90]">SIH 2026 · v1.0.0</div>
          </div>
          <button
            onClick={() => { localStorage.removeItem('heimdall_token'); localStorage.removeItem('heimdall_email'); location.reload(); }}
            title="Sign out"
            className="rounded-lg p-2 text-[#C9D1C0] transition-colors hover:bg-white/10 hover:text-white"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </aside>
  );
}
