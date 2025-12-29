import { useState } from 'react';
import { useOpportunities, executeTrade, triggerScan } from '../hooks/useApi';

export default function Opportunities() {
  const { data: opportunities, loading, error, refetch } = useOpportunities(20);
  const [scanning, setScanning] = useState(false);
  const [trading, setTrading] = useState({});

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

  const handleTrade = async (marketId, amount) => {
    setTrading(prev => ({ ...prev, [marketId]: true }));
    try {
      const result = await executeTrade(marketId, amount);
      if (result.success) {
        await refetch();
      } else {
        alert(`Trade failed: ${result.error || 'Unknown error'}`);
      }
    } catch (e) {
      alert(`Trade failed: ${e.message}`);
    } finally {
      setTrading(prev => ({ ...prev, [marketId]: false }));
    }
  };

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">🔒 Polybond Opportunities</h2>
        <div className="animate-pulse space-y-3">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-16 bg-gray-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">🔒 Polybond Opportunities</h2>
        <p className="text-red-400">Failed to load opportunities: {error}</p>
      </div>
    );
  }

  const oppList = opportunities || [];

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <span>🔒</span> Polybond Opportunities
        </h2>
        <button
          onClick={handleScan}
          disabled={scanning}
          className="px-3 py-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded text-sm font-medium transition-colors"
        >
          {scanning ? 'Scanning...' : 'Refresh'}
        </button>
      </div>

      {oppList.length === 0 ? (
        <div className="text-center py-8">
          <p className="text-gray-400 mb-2">No opportunities found</p>
          <p className="text-gray-500 text-sm">Markets with 98%+ probability will appear here</p>
        </div>
      ) : (
        <div className="space-y-3 max-h-[400px] overflow-y-auto">
          {oppList.map((opp, idx) => (
            <div key={idx} className="bg-gray-700/50 rounded-lg p-3 border border-gray-600">
              <div className="flex justify-between items-start gap-2 mb-2">
                <p className="text-sm font-medium text-gray-200 line-clamp-2" title={opp.question}>
                  {opp.question}
                </p>
                <span className={`shrink-0 px-2 py-0.5 rounded text-xs font-medium ${
                  opp.side === 'YES' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
                }`}>
                  {opp.side}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 text-xs mb-3">
                <div>
                  <span className="text-gray-400">Price:</span>
                  <span className="ml-1 text-white">${opp.current_price?.toFixed(3)}</span>
                </div>
                <div>
                  <span className="text-gray-400">Return:</span>
                  <span className="ml-1 text-green-400">{opp.potential_return_pct?.toFixed(2)}%</span>
                </div>
                <div>
                  <span className="text-gray-400">APY:</span>
                  <span className="ml-1 text-yellow-400">{opp.annualized_return_pct?.toFixed(0)}%</span>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="text-xs">
                  <span className="text-gray-400">Risk:</span>
                  <span className={`ml-1 ${opp.risk_score < 30 ? 'text-green-400' : opp.risk_score < 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                    {opp.risk_score}/100
                  </span>
                  <span className="mx-2 text-gray-600">|</span>
                  <span className="text-gray-400">Vol:</span>
                  <span className="ml-1 text-gray-300">${(opp.volume_24h / 1000).toFixed(1)}k</span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleTrade(opp.market_id, 50)}
                    disabled={trading[opp.market_id]}
                    className="px-2 py-1 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 rounded text-xs font-medium transition-colors"
                  >
                    $50
                  </button>
                  <button
                    onClick={() => handleTrade(opp.market_id, 100)}
                    disabled={trading[opp.market_id]}
                    className="px-2 py-1 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 rounded text-xs font-medium transition-colors"
                  >
                    $100
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
