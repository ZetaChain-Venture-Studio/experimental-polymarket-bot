import { useState, useMemo } from 'react';
import { useOpportunities, useTrades, executeTrade, triggerScan } from '../hooks/useApi';

// Spinner component
function Spinner({ size = 'md', className = '' }) {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-6 h-6',
    lg: 'w-8 h-8'
  };
  return (
    <svg className={`animate-spin ${sizeClasses[size]} ${className}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
  );
}

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
    if (selected.has(marketId)) return;

    setTrading(prev => ({ ...prev, [marketId]: true }));

    try {
      const result = await executeTrade(marketId, 100);

      if (result.success) {
        setSelected(prev => new Set([...prev, marketId]));
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

    const totalInvested = selectedOpps.length * 100;
    const expectedReturn = selectedOpps.reduce((sum, o) => {
      const returnAmt = 100 * (o.potential_return_pct / 100);
      return sum + returnAmt;
    }, 0);
    const avgApy = selectedOpps.reduce((sum, o) => sum + o.annualized_return_pct, 0) / selectedOpps.length;

    return { count: selectedOpps.length, totalInvested, expectedReturn, avgApy };
  }, [sortedOpps, selected]);

  // Format settlement date using actual estimated payout date
  const formatSettlement = (opp) => {
    const days = opp.days_to_resolution;
    const estimatedHours = opp.estimated_resolution_hours || 24;
    const estimatedPayout = opp.estimated_payout_date ? new Date(opp.estimated_payout_date) : null;
    const endDate = opp.end_date ? new Date(opp.end_date) : null;

    const formatDate = (date) => {
      if (!date) return '';
      const options = { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' };
      return date.toLocaleDateString('en-US', options);
    };

    if (days < -1) {
      // Already ended, awaiting settlement
      return {
        status: 'pending',
        label: 'Pending Resolution',
        detail: estimatedPayout
          ? `Payout expected: ${formatDate(estimatedPayout)}`
          : `Ended ${Math.abs(days).toFixed(0)}d ago - awaiting settlement (~${estimatedHours}h resolution)`
      };
    } else if (days < 0) {
      return {
        status: 'pending',
        label: 'Resolving Soon',
        detail: estimatedPayout
          ? `Payout expected: ${formatDate(estimatedPayout)}`
          : `Market ended - resolution in ~${estimatedHours}h`
      };
    } else if (days < 1) {
      const hours = days * 24;
      return {
        status: 'soon',
        label: `${hours.toFixed(0)}h remaining`,
        detail: estimatedPayout
          ? `Payout: ${formatDate(estimatedPayout)}`
          : `Ends today, payout ~${(hours + estimatedHours).toFixed(0)}h`
      };
    } else {
      return {
        status: 'future',
        label: `${days.toFixed(0)} days`,
        detail: estimatedPayout
          ? `Payout: ${formatDate(estimatedPayout)}`
          : endDate
            ? `Ends ${formatDate(endDate)}, +${estimatedHours}h resolution`
            : `Settles in ~${(days * 24 + estimatedHours).toFixed(0)}h`
      };
    }
  };

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-8 border border-gray-700">
        <div className="flex flex-col items-center justify-center py-12">
          <Spinner size="lg" className="text-blue-500 mb-4" />
          <p className="text-gray-400">Loading opportunities...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Polybond Opportunities</h2>
        <p className="text-red-400">Failed to load: {error}</p>
        <button onClick={refetch} className="mt-4 px-4 py-2 bg-blue-600 rounded">Retry</button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Portfolio Stats */}
      {stats.count > 0 && (
        <div className="bg-gradient-to-r from-green-900/40 to-emerald-900/40 rounded-xl p-6 border border-green-600/50">
          <h3 className="text-lg font-bold text-green-400 mb-4">Your Selected Portfolio</h3>
          <div className="grid grid-cols-4 gap-6">
            <div className="text-center">
              <div className="text-3xl font-bold text-white">{stats.count}</div>
              <div className="text-sm text-gray-400 mt-1">Positions</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-white">${stats.totalInvested}</div>
              <div className="text-sm text-gray-400 mt-1">Total Invested</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-green-400">+${stats.expectedReturn.toFixed(2)}</div>
              <div className="text-sm text-gray-400 mt-1">Expected Profit</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-yellow-400">{stats.avgApy.toFixed(0)}%</div>
              <div className="text-sm text-gray-400 mt-1">Average APY</div>
            </div>
          </div>
        </div>
      )}

      {/* Recent Trades Log */}
      {recentTrades.length > 0 && (
        <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
          <h3 className="text-md font-semibold text-gray-300 mb-4">Recent Trades</h3>
          <div className="space-y-3 max-h-40 overflow-y-auto">
            {recentTrades.map((trade, idx) => (
              <div key={idx} className={`p-3 rounded-lg ${trade.status === 'success' ? 'bg-green-900/30 border border-green-800' : 'bg-red-900/30 border border-red-800'}`}>
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold mr-2 ${trade.side === 'YES' ? 'bg-green-600' : 'bg-red-600'}`}>
                      {trade.side}
                    </span>
                    <span className="text-gray-300">${trade.price?.toFixed(3)}</span>
                    <span className="text-gray-500 mx-2">-</span>
                    <span className="text-gray-400 text-sm">{trade.question?.slice(0, 50)}...</span>
                  </div>
                  <span className={`text-sm font-medium ${trade.status === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                    {trade.status === 'success' ? 'SUCCESS' : 'FAILED'}
                  </span>
                </div>
                {trade.order_id && (
                  <div className="text-xs text-gray-500 mt-2 font-mono">
                    Order ID: {trade.order_id}
                  </div>
                )}
                {trade.error && (
                  <div className="text-xs text-red-400 mt-2">{trade.error}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Opportunities List */}
      <div className="bg-gray-800 rounded-xl border border-gray-700">
        <div className="flex items-center justify-between p-5 border-b border-gray-700">
          <div>
            <h2 className="text-xl font-bold text-white">
              Polybond Opportunities
            </h2>
            <p className="text-sm text-gray-400 mt-1">
              {sortedOpps.length} markets with 98%+ probability • Sorted by settlement time
            </p>
          </div>
          <button
            onClick={handleScan}
            disabled={scanning}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-lg text-sm font-medium transition-colors"
          >
            {scanning ? (
              <>
                <Spinner size="sm" className="text-white" />
                Scanning...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Refresh
              </>
            )}
          </button>
        </div>

        {sortedOpps.length === 0 ? (
          <div className="text-center py-16">
            <div className="text-4xl mb-4">🔍</div>
            <p className="text-gray-400 text-lg mb-2">No opportunities found</p>
            <p className="text-gray-500">Markets with 98%+ probability will appear here</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-700/50">
            {sortedOpps.map((opp) => {
              const isSelected = selected.has(opp.market_id);
              const isTrading = trading[opp.market_id];
              const settlement = formatSettlement(opp);

              return (
                <div
                  key={opp.market_id}
                  className={`p-5 cursor-pointer transition-all ${
                    isSelected
                      ? 'bg-green-900/20'
                      : 'hover:bg-gray-700/30'
                  }`}
                  onClick={() => !isSelected && !isTrading && handleSelect(opp)}
                >
                  <div className="flex items-start gap-4">
                    {/* Checkbox */}
                    <div className="pt-1">
                      {isTrading ? (
                        <div className="w-6 h-6 rounded-md border-2 border-yellow-500 flex items-center justify-center">
                          <Spinner size="sm" className="text-yellow-500" />
                        </div>
                      ) : isSelected ? (
                        <div className="w-6 h-6 rounded-md border-2 border-green-500 bg-green-500 flex items-center justify-center">
                          <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        </div>
                      ) : (
                        <div className="w-6 h-6 rounded-md border-2 border-gray-500 hover:border-green-500 transition-colors"></div>
                      )}
                    </div>

                    {/* Main Content */}
                    <div className="flex-1 min-w-0">
                      {/* Title Row */}
                      <div className="flex items-center gap-3 mb-2">
                        <span className={`shrink-0 px-2 py-1 rounded text-xs font-bold ${
                          opp.side === 'YES' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
                        }`}>
                          {opp.side}
                        </span>
                        <h3 className="text-base font-medium text-white truncate" title={opp.question}>
                          {opp.question}
                        </h3>
                      </div>

                      {/* Stats Row */}
                      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                        <div>
                          <span className="text-gray-500">Price:</span>
                          <span className="ml-2 text-white font-mono font-medium">${opp.current_price?.toFixed(4)}</span>
                        </div>
                        <div>
                          <span className="text-gray-500">Return:</span>
                          <span className="ml-2 text-green-400 font-medium">{opp.potential_return_pct?.toFixed(2)}%</span>
                        </div>
                        <div>
                          <span className="text-gray-500">APY:</span>
                          <span className="ml-2 text-yellow-400 font-bold">{opp.annualized_return_pct?.toFixed(0)}%</span>
                        </div>
                        <div>
                          <span className="text-gray-500">Volume:</span>
                          <span className="ml-2 text-gray-300">${(opp.volume_24h / 1000).toFixed(1)}k</span>
                        </div>
                        <div>
                          <span className="text-gray-500">Risk:</span>
                          <span className={`ml-2 font-medium ${
                            opp.risk_score < 30 ? 'text-green-400' :
                            opp.risk_score < 60 ? 'text-yellow-400' : 'text-red-400'
                          }`}>{opp.risk_score}/100</span>
                        </div>
                      </div>

                      {/* Resolution Source & Settlement Info */}
                      <div className="mt-3 flex flex-wrap items-center gap-3">
                        {/* Resolution Source Badge */}
                        {opp.resolution_source && (
                          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-purple-900/30 text-purple-400 text-xs">
                            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                            </svg>
                            <span className="font-medium">Source:</span>
                            <span>{opp.resolution_source.slice(0, 30)}{opp.resolution_source.length > 30 ? '...' : ''}</span>
                          </div>
                        )}

                        {/* Settlement Info */}
                        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
                          settlement.status === 'pending' ? 'bg-orange-900/30 text-orange-400' :
                          settlement.status === 'soon' ? 'bg-yellow-900/30 text-yellow-400' :
                          'bg-blue-900/30 text-blue-400'
                        }`}>
                          {settlement.status === 'pending' && (
                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                            </svg>
                          )}
                          {settlement.status === 'soon' && (
                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                            </svg>
                          )}
                          {settlement.status === 'future' && (
                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clipRule="evenodd" />
                            </svg>
                          )}
                          <span className="font-medium">{settlement.label}</span>
                          <span className="text-gray-400">•</span>
                          <span className="text-xs opacity-80">{settlement.detail}</span>
                        </div>
                      </div>

                      {/* Resolution Rules (expandable) */}
                      {opp.resolution_rules && (
                        <details className="mt-2">
                          <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-400">
                            View resolution criteria...
                          </summary>
                          <p className="mt-1.5 text-xs text-gray-400 leading-relaxed bg-gray-900/50 p-2 rounded">
                            {opp.resolution_rules.slice(0, 200)}{opp.resolution_rules.length > 200 ? '...' : ''}
                          </p>
                        </details>
                      )}
                    </div>

                    {/* Quick Stats Badge */}
                    <div className="shrink-0 text-right">
                      <div className="text-2xl font-bold text-green-400">
                        +${(100 * opp.potential_return_pct / 100).toFixed(2)}
                      </div>
                      <div className="text-xs text-gray-500">on $100</div>
                    </div>
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
