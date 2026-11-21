import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Outlet, Route, Routes } from 'react-router-dom'
import Login from './features/auth/Login'
import BacktestLab from './features/backtest/BacktestLab'
import BotDetail from './features/bots/BotDetail'
import Bots from './features/bots/Bots'
import Wizard from './features/bots/Wizard'
import RiskSettings from './features/risk/RiskSettings'
import Trade from './features/trade/Trade'
import Dashboard from './features/dashboard/Dashboard'
import { refresh, useAuth } from './lib/auth'
import Shell from './shell/Shell'
import { Card } from './ui'

const DevUi = lazy(() => import('./features/dev/DevUi'))
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, retry: 1 } } })

function Soon({ name }: { name: string }) {
  return <Card title={name} subtitle="Planned for Phase 6 (AI layer)" />
}

function Gate() {
  const { token, ready, setReady } = useAuth()
  useEffect(() => {
    void refresh().finally(setReady) // restore the session from the httpOnly cookie
  }, [setReady])
  if (!ready) return <div role="status" aria-label="Loading" className="p-8" />
  if (!token) return <Login />
  return <Outlet />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Gate />}>
          <Route element={<Shell />}>
            <Route index element={<Dashboard />} />
            <Route path="bots" element={<Bots />} />
            <Route path="bots/new" element={<Wizard />} />
            <Route path="bots/:id" element={<BotDetail />} />
            <Route path="backtest" element={<BacktestLab />} />
            <Route path="settings" element={<RiskSettings />} />
            <Route path="trade" element={<Trade />} />
            {['ai'].map((p) => (
              <Route key={p} path={p} element={<Soon name={p} />} />
            ))}
            <Route
              path="dev/ui"
              element={
                <Suspense fallback={null}>
                  <DevUi />
                </Suspense>
              }
            />
          </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
