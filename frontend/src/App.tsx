import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Dashboard from './features/dashboard/Dashboard'
import Shell from './shell/Shell'
import { Card } from './ui'

const DevUi = lazy(() => import('./features/dev/DevUi'))
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, retry: 1 } } })

function Soon({ name }: { name: string }) {
  return <Card title={name} subtitle="Planned for Phase 5" />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<Dashboard />} />
            {['trade', 'bots', 'ai', 'backtest', 'settings'].map((p) => (
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
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
