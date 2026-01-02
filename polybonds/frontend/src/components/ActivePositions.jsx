import { usePositions } from '../hooks/useApi';

export default function ActivePositions() {
  const { data: positions, loading, error } = usePositions();

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span>📊</span> Active Positions
        </h2>
        <div className="animate-pulse space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-12 bg-gray-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">📊 Active Positions</h2>
        <p className="text-red-400">Failed to load positions: {error}</p>
      </div>
    );
  }

  const positionsList = positions?.positions || [];

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <span>📊</span> Active Positions ({positionsList.length})
      </h2>

      {positionsList.length === 0 ? (
        <p className="text-gray-400 text-center py-4">No open positions</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-700">
                <th className="text-left py-2">Market</th>
                <th className="text-left py-2">Side</th>
                <th className="text-right py-2">Entry</th>
                <th className="text-right py-2">Current</th>
                <th className="text-right py-2">P&L</th>
              </tr>
            </thead>
            <tbody>
              {positionsList.map((pos, idx) => {
                const pnl = pos.unrealized_pnl || 0;
                const pnlPct = pos.unrealized_pnl_pct || 0;
                const isProfit = pnl >= 0;

                return (
                  <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                    <td className="py-2 max-w-[200px] truncate" title={pos.question}>
                      {pos.question || pos.market_id?.slice(0, 20) + '...'}
                    </td>
                    <td className="py-2">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        pos.side === 'YES' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
                      }`}>
                        {pos.side}
                      </span>
                    </td>
                    <td className="py-2 text-right">${pos.avg_entry_price?.toFixed(4)}</td>
                    <td className="py-2 text-right">${pos.current_price?.toFixed(4)}</td>
                    <td className={`py-2 text-right font-medium ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                      {isProfit ? '+' : ''}{pnl.toFixed(2)} ({pnlPct.toFixed(1)}%)
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
