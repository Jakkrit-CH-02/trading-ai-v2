import * as Tooltip from '@radix-ui/react-tooltip'
import { Bell, Bot, FlaskConical, LayoutDashboard, LineChart, Moon, Search, Settings, ShieldAlert, Sparkles, Sun } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useTheme } from '../lib/theme'
import { BotStatusPill, IconButton, MarketStatusPill, Toaster, cx } from '../ui'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/trade', label: 'Trade', icon: LineChart },
  { to: '/bots', label: 'Bots', icon: Bot },
  { to: '/ai', label: 'AI Analyst', icon: Sparkles },
  { to: '/backtest', label: 'Backtest Lab', icon: FlaskConical },
  { to: '/settings', label: 'Risk & Settings', icon: Settings },
]

function Rail() {
  return (
    <nav aria-label="Main" className="max-md:bg-surface max-md:shadow-raised-lg fixed z-30 flex gap-3 md:top-0 md:left-0 md:h-full md:w-[72px] md:flex-col md:items-center md:py-6 max-md:inset-x-0 max-md:bottom-0 max-md:justify-around max-md:p-3">
      {NAV.map(({ to, label, icon: Icon }) => (
        <Tooltip.Root key={to}>
          <Tooltip.Trigger asChild>
            <NavLink
              to={to}
              end={to === '/'}
              aria-label={label}
              className={({ isActive }) => cx('bg-surface grid size-11 place-items-center rounded-full', isActive ? 'shadow-pressed' : 'shadow-raised-sm')}
            >
              <Icon size={18} />
            </NavLink>
          </Tooltip.Trigger>
          <Tooltip.Portal>
            <Tooltip.Content side="right" className="bg-ink text-on-ink rounded-lg px-3 py-1 text-[11px]">
              {label}
            </Tooltip.Content>
          </Tooltip.Portal>
        </Tooltip.Root>
      ))}
    </nav>
  )
}

function Header({ paper }: { paper: boolean }) {
  const { theme, toggle } = useTheme()
  const date = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
  const [weekday, ...rest] = date.split(', ')
  return (
    <header className="flex flex-wrap items-center gap-4">
      <span className="bg-surface shadow-raised-sm flex items-center gap-2 rounded-full px-5 py-3 text-[15px] font-semibold">
        <LineChart size={16} /> Softtrade
      </span>
      <span className="text-secondary hidden text-[13px] lg:block">
        {weekday} | <strong className="text-primary font-semibold">{rest.join(', ')}</strong>
      </span>
      <label className="shadow-inset rounded-full flex min-w-[200px] flex-1 items-center gap-2 px-4 py-2.5">
        <Search size={14} className="text-secondary" aria-hidden />
        <input aria-label="Search markets" placeholder="Search markets, e.g. BTC" className="w-full bg-transparent outline-none" />
      </label>
      <MarketStatusPill />
      <BotStatusPill status="RUNNING" label="0 bots running" />
      <IconButton icon={<ShieldAlert size={16} />} label="Kill switch" className="text-down" />
      <IconButton icon={<Bell size={16} />} label="Notifications" />
      <IconButton icon={theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />} label="Toggle theme" onClick={toggle} />
      <span className="bg-surface shadow-raised-sm flex items-center gap-3 rounded-full py-1.5 pr-5 pl-1.5">
        <span className="bg-ink text-on-ink grid size-8 place-items-center rounded-full text-[13px] font-semibold">T</span>
        <span className="leading-4">
          <span className="block text-[13px] font-semibold">Hi, Teng</span>
          <span className="text-secondary block text-[11px]">{paper ? 'Paper account' : 'Pro account'}</span>
        </span>
      </span>
    </header>
  )
}

export default function Shell({ paper = true }: { paper?: boolean }) {
  return (
    <Tooltip.Provider delayDuration={150}>
      {paper && (
        <div role="status" className="bg-accent text-on-accent sticky top-0 z-40 py-0.5 text-center text-[11px] font-semibold tracking-widest">
          PAPER TRADING
        </div>
      )}
      <Rail />
      <div className="mx-auto flex max-w-[1440px] flex-col gap-6 p-6 pb-24 md:pl-[96px]">
        <Header paper={paper} />
        <main>
          <Outlet />
        </main>
      </div>
      <Toaster />
    </Tooltip.Provider>
  )
}
