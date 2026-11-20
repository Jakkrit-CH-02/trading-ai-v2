import { useState } from 'react'
import { useRealtimeConnection } from '../../lib/realtime'
import { AllocationCard, BotsCard, PortfolioCard, PriceCard, RecentOrders, SentimentCard, WatchlistCard } from './cards'

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']

export default function Dashboard() {
  const [symbol, setSymbol] = useState('BTCUSDT')
  useRealtimeConnection([...SYMBOLS.map((s) => `ticker:${s}`), 'portfolio', 'risk'])
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-12">
      <div className="xl:col-span-3">
        <PortfolioCard />
      </div>
      <div className="md:col-span-2 xl:col-span-9">
        <PriceCard symbol={symbol} />
      </div>
      <div className="xl:col-span-4">
        <WatchlistCard selected={symbol} onSelect={setSymbol} />
      </div>
      <div className="xl:col-span-4">
        <BotsCard symbol={symbol} />
      </div>
      <div className="flex flex-col gap-6 md:col-span-2 xl:col-span-4 xl:grid">
        <SentimentCard />
        <AllocationCard />
      </div>
      <div className="md:col-span-2 xl:col-span-12">
        <RecentOrders />
      </div>
    </div>
  )
}
