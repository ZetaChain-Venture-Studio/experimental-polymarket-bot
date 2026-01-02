import { useSettlements } from '../hooks/useApi';

export default function SettlementLog() {
  const { data: settlements, loading, error } = useSettlements(10);

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">✅ Settlements</h2>
        <div className="animate-pulse space-y-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-8 bg-gray-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">✅ Settlements</h2>
        <p className="text-red-400">Failed to load settlements: {error}</p>
      </div>
    );
  }

  const settlementsList = settlements?.settlements || [];

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString();
  };

  // Calculate summary stats
  const totalPnl = settlementsList.reduce((sum, s) => sum + (s.pnl_usd || 0), 0);
  const wins = settlementsList.filter(s => s.outcome === 'win').length;
  const losses = settlementsList.filter(s => s.outcome === 'loss').length;

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <span>✅</span> Settlements
      </h2>

      {settlementsList.length === 0 ? (
        <p className="text-gray-400 text-center py-4">No settlements yet</p>
      ) : (
        <>
          <div className="space-y-2 mb-4">
            {settlementsList.map((settlement, idx) => (
              <div key={idx} className="flex items-center justify-between py-2 border-b border-gray-700/50 last:border-0">
                <div className="flex items-center gap-3">
                  <span className={`text-lg ${settlement.outcome === 'win' ? '' : ''}`}>
                    {settlement.outcome === 'win' ? '🟢' : '🔴'}
                  </span>
                  <div className="max-w-[150px]">
                    <p className="text-sm text-gray-300 truncate" title={settlement.question}>
                      {settlement.question || 'Market'}
                    </p>
                    <p className="text-xs text-gray-500">{formatDate(settlement.settled_at)}</p>
                  </div>
                </div>
                <div className="text-right">
                  <span className={`font-medium ${settlement.pnl_usd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {settlement.pnl_usd >= 0 ? '+' : ''}${settlement.pnl_usd?.toFixed(2)}
                  </span>
                  <p className="text-xs text-gray-500">
                    {settlement.pnl_pct?.toFixed(1)}%
                  </p>
                </div>
              </div>
            ))}
          </div>

          <div className="border-t border-gray-700 pt-3">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Total P&L:</span>
              <span className={`font-medium ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between text-sm mt-1">
              <span className="text-gray-400">Win Rate:</span>
              <span className="text-gray-300">
                {wins + losses > 0 ? ((wins / (wins + losses)) * 100).toFixed(0) : 0}%
                <span className="text-gray-500 ml-1">({wins}W/{losses}L)</span>
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
