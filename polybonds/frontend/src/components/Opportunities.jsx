import { useState, useMemo } from 'react';
import { useOpportunities, useTrades, executeTrade, triggerScan } from '../hooks/useApi';

export default function Opportunities() {
  const { data: opportunities, loading, error, refetch } = useOpportunities(100);
  const { data: tradesData, refetch: refetchTrades } = useTrades(10);
  const [scanning, setScanning] = useState(false);
  const [trading, setTrading] = useState({});
  const [selected, setSelected] = useState(new Set());
  const [recentTrades, setRecentTrades] = useState([]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await triggerScan();
      await refetch();
    } catch (e) {
      console.error('Scan failed:', e);
    } finally {
      setScanning(false);
    }
  };

  const handleSelect = async (opp) => {
    const marketId = opp.market_id;

    // If already selected, do nothing (can't deselect after trading)
    if (selected.has(marketId)) return;

    // Mark as trading
    setTrading(prev => ({ ...prev, [marketId]: true }));

    try {
      // Execute trade immediately with max position size ($100)
      const result = await executeTrade(marketId, 100);

      if (result.success) {
        // Add to selected
        setSelected(prev => new Set([...prev, marketId]));

        // Add to recent trades
        setRecentTrades(prev => [{
          market_id: marketId,
          question: opp.question,
          side: opp.side,
          price: opp.current_price,
          amount: 100,
          order_id: result.order_id,
          trade_id: result.trade_id,
          timestamp: new Date().toISOString(),
          status: 'success'
        }, ...prev.slice(0, 9)]);

        await refetch();
        await refetchTrades();
      } else {
        // Add failed trade to log
        setRecentTrades(prev => [{
          market_id: marketId,
          question: opp.question,
          side: opp.side,
          price: opp.current_price,
          amount: 100,
          error: result.message || result.error || 'Trade failed',
          timestamp: new Date().toISOString(),
          status: 'failed'
        }, ...prev.slice(0, 9)]);
      }
    } catch (e) {
      setRecentTrades(prev => [{
        market_id: marketId,
        question: opp.question,
        side: opp.side,
        price: opp.current_price,
        amount: 100,
        error: e.message,
        timestamp: new Date().toISOString(),
        status: 'failed'
      }, ...prev.slice(0, 9)]);
    } finally {
      setTrading(prev => ({ ...prev, [marketId]: false }));
    }
  };

  // Sort by days to resolution (soonest first)
  const sortedOpps = useMemo(() => {
    const oppList = opportunities?.opportunities || [];
    return [...oppList].sort((a, b) => a.days_to_resolution - b.days_to_resolution);
  }, [opportunities]);

  // Calculate portfolio statistics
  const stats = useMemo(() => {
    const selectedOpps = sortedOpps.filter(o => selected.has(o.market_id));
    if (selectedOpps.length === 0) {
      return { count: 0, totalInvested: 0, expectedReturn: 0, avgApy: 0 };
    }

    const totalInvested = selectedOpps.length * 100; // $100 per position
    const expectedReturn = selectedOpps.reduce((sum, o) => {
      const returnAmt = 100 * (o.potential_return_pct / 100);
      return sum + returnAmt;
    }, 0);
    const avgApy = selectedOpps.reduce((sum, o) => sum + o.annualized_return_pct, 0) / selectedOpps.length;

    return {
      count: selectedOpps.length,
      totalInvested,
      expectedReturn,
      avgApy
    };
  }, [sortedOpps, selected]);

  // Format days to resolution
  const formatDays = (days) => {
    if (days < 0) {
      const hours = Math.abs(days * 24);
      if (hours < 24) return `${hours.toFixed(0)}h ago`;
      return `${Math.abs(days).toFixed(0)}d ago`;
    }
    if (days < 1) {
      const hours = days * 24;
      return `${hours.toFixed(0)}h`;
    }
    return `${days.toFixed(0)}d`;
  };

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Polybond Opportunities</h2>
        <div className="animate-pulse space-y-3">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-12 bg-gray-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Polybond Opportunities</h2>
        <p className="text-red-400">Failed to load: {error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Portfolio Stats */}
      {stats.count > 0 && (
        <div className="bg-green-900/30 rounded-lg p-4 border border-green-700">
          <h3 className="text-sm font-semibold text-green-400 mb-3">Selected Portfolio</h3>
          <div className="grid grid-cols-4 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold text-white">{stats.count}</div>
              <div className="text-xs text-gray-400">Positions</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-white">${stats.totalInvested}</div>
              <div className="text-xs text-gray-400">Invested</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-green-400">+${stats.expectedReturn.toFixed(2)}</div>
              <div className="text-xs text-gray-400">Expected Gain</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-yellow-400">{stats.avgApy.toFixed(0)}%</div>
              <div className="text-xs text-gray-400">Avg APY</div>
            </div>
          </div>
        </div>
      )}

      {/* Recent Trades Log */}
      {recentTrades.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Recent Trades</h3>
          <div className="space-y-2 max-h-32 overflow-y-auto">
            {recentTrades.map((trade, idx) => (
              <div key={idx} className={`text-xs p-2 rounded ${trade.status === 'success' ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                <div className="flex justify-between items-start">
                  <span className="text-gray-300 truncate flex-1" title={trade.question}>
                    {trade.side} @ ${trade.price?.toFixed(3)} - {trade.question?.slice(0, 40)}...
                  </span>
                  <span className={trade.status === 'success' ? 'text-green-400' : 'text-red-400'}>
                    {trade.status === 'success' ? 'OK' : 'FAIL'}
                  </span>
                </div>
                {trade.order_id && (
                  <div className="text-gray-500 mt-1">
                    Order: <span className="font-mono">{trade.order_id.slice(0, 16)}...</span>
                  </div>
                )}
                {trade.error && (
                  <div className="text-red-400 mt-1">{trade.error}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Opportunities List */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">
            Opportunities ({sortedOpps.length})
          </h2>
          <button
            onClick={handleScan}
            disabled={scanning}
            className="px-3 py-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded text-sm font-medium transition-colors"
          >
            {scanning ? 'Scanning...' : 'Refresh'}
          </button>
        </div>

        {sortedOpps.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-400 mb-2">No opportunities found</p>
            <p className="text-gray-500 text-sm">Markets with 98%+ probability will appear here</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[500px] overflow-y-auto">
            {/* Header */}
            <div className="grid grid-cols-12 gap-2 text-xs text-gray-500 px-2 py-1 border-b border-gray-700">
              <div className="col-span-1"></div>
              <div className="col-span-5">Market</div>
              <div className="col-span-1 text-center">Time</div>
              <div className="col-span-1 text-right">Price</div>
              <div className="col-span-1 text-right">Return</div>
              <div className="col-span-1 text-right">APY</div>
              <div className="col-span-2 text-right">Volume</div>
            </div>

            {sortedOpps.map((opp) => {
              const isSelected = selected.has(opp.market_id);
              const isTrading = trading[opp.market_id];

              return (
                <div
                  key={opp.market_id}
                  className={`grid grid-cols-12 gap-2 items-center p-2 rounded cursor-pointer transition-colors ${
                    isSelected
                      ? 'bg-green-900/30 border border-green-700'
                      : 'bg-gray-700/30 hover:bg-gray-700/50 border border-transparent'
                  }`}
                  onClick={() => !isSelected && !isTrading && handleSelect(opp)}
                >
                  {/* Checkbox */}
                  <div className="col-span-1 flex justify-center">
                    {isTrading ? (
                      <div className="w-5 h-5 rounded border-2 border-yellow-500 flex items-center justify-center">
                        <div className="w-3 h-3 bg-yellow-500 rounded-sm animate-pulse"></div>
                      </div>
                    ) : isSelected ? (
                      <div className="w-5 h-5 rounded border-2 border-green-500 bg-green-500 flex items-center justify-center">
                        <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      </div>
                    ) : (
                      <div className="w-5 h-5 rounded border-2 border-gray-500 hover:border-green-500 transition-colors"></div>
                    )}
                  </div>

                  {/* Market Name + Side */}
                  <div className="col-span-5 flex items-center gap-2 min-w-0">
                    <span className={`shrink-0 px-1.5 py-0.5 rounded text-xs font-bold ${
                      opp.side === 'YES' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
                    }`}>
                      {opp.side}
                    </span>
                    <span className="text-sm text-gray-200 truncate" title={opp.question}>
                      {opp.question}
                    </span>
                  </div>

                  {/* Time to Resolution */}
                  <div className={`col-span-1 text-center text-sm font-medium ${
                    opp.days_to_resolution < 0 ? 'text-orange-400' :
                    opp.days_to_resolution < 1 ? 'text-yellow-400' : 'text-gray-300'
                  }`}>
                    {formatDays(opp.days_to_resolution)}
                  </div>

                  {/* Price */}
                  <div className="col-span-1 text-right text-sm text-white font-mono">
                    ${opp.current_price?.toFixed(3)}
                  </div>

                  {/* Return */}
                  <div className="col-span-1 text-right text-sm text-green-400">
                    {opp.potential_return_pct?.toFixed(2)}%
                  </div>

                  {/* APY */}
                  <div className="col-span-1 text-right text-sm text-yellow-400 font-medium">
                    {opp.annualized_return_pct?.toFixed(0)}%
                  </div>

                  {/* Volume */}
                  <div className="col-span-2 text-right text-sm text-gray-400">
                    ${(opp.volume_24h / 1000).toFixed(1)}k
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
