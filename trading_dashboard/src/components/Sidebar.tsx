"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Activity, ListOrdered, Building2, Gauge, Wrench, CloudDownload, HeartPulse, Briefcase, Target, CandlestickChart } from "lucide-react";

const NAV_ITEMS: { href: string; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { href: "/",            label: "Overview",       icon: LayoutDashboard },
  { href: "/signals",     label: "Signals",        icon: Activity        },
  { href: "/orders",      label: "Orders",         icon: ListOrdered     },
  { href: "/portfolio",   label: "My Portfolio",   icon: Briefcase       },
  { href: "/low-float",   label: "Low Float",      icon: Target          },
  { href: "/stocks",      label: "Stocks",         icon: Building2       },
  { href: "/rv",          label: "Rel. Volume",    icon: Gauge           },
  { href: "/minute-candles", label: "Minute Candles", icon: CandlestickChart },
  { href: "/raw-trades",  label: "Raw Tape",       icon: CloudDownload   },
  { href: "/run-status",  label: "System Status",  icon: HeartPulse      },
  { href: "/utils",       label: "Data Pipeline",  icon: Wrench          },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 shrink-0 border-r border-zinc-900/5 dark:border-white/5 backdrop-blur-md bg-white/40 dark:bg-zinc-950/40 flex flex-col">
      <div className="px-6 py-7 border-b border-zinc-900/5 dark:border-white/5">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-zinc-500 dark:text-zinc-400">
          <span className="size-1.5 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 shadow-[0_0_8px_rgba(251,146,60,0.6)]" />
          <span>Polygon · Algo Trading</span>
        </div>
        <div
          style={{ fontFamily: "var(--font-display)", fontFeatureSettings: '"ss01", "ss02"' }}
          className="mt-2 text-[28px] leading-[1.05] font-semibold tracking-tight text-zinc-900 dark:text-white"
        >
          Quant <span className="italic font-normal text-amber-600 dark:text-amber-400">Console</span>
        </div>
        <div className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400 font-medium">
          Real-time signals & execution
        </div>
        <div className="mt-3 h-0.5 w-12 rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
      </div>

      <nav className="flex-1 px-3 py-5 flex flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={[
                "group flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-300",
                active
                  ? "bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/20"
                  : "text-zinc-600 dark:text-zinc-400 border border-transparent hover:bg-zinc-900/[0.03] dark:hover:bg-white/[0.03] hover:text-zinc-900 dark:hover:text-white hover:border-zinc-900/5 dark:hover:border-white/5",
              ].join(" ")}
            >
              <Icon
                className={[
                  "size-4 transition-colors",
                  active ? "text-amber-500 dark:text-amber-400" : "text-zinc-400 dark:text-zinc-500 group-hover:text-zinc-700 dark:group-hover:text-zinc-300",
                ].join(" ")}
              />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="px-6 py-5 border-t border-zinc-900/5 dark:border-white/5 text-[10px] uppercase tracking-widest text-zinc-500">
        Read-only · Local
      </div>
    </aside>
  );
}
