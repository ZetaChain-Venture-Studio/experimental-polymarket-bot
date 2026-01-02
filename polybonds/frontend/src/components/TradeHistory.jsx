import { useTrades } from '../hooks/useApi';

export default function TradeHistory() {
  const { data: trades, loading, error } = useTrades(10);

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">📜 Recent Trades</h2>
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
        <h2 className="text-lg font-semibold mb-4">📜 Recent Trades</h2>
        <p className="text-red-400">Failed to load trades: {error}</p>
      </div>
    );
  }

  const tradesList = trades?.trades || [];

  const formatTime = (dateStr) => {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now - date;

    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <span>📜</span> Recent Trades
      </h2>

      {tradesList.length === 0 ? (
        <p className="text-gray-400 text-center py-4">No trades yet</p>
      ) : (
        <div className="space-y-2">
          {tradesList.map((trade, idx) => (
            <div key={idx} className="flex items-center justify-between py-2 border-b border-gray-700/50 last:border-0">
              <div className="flex items-center gap-3">
                <span className="text-gray-500 text-xs w-16">{formatTime(trade.created_at)}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  trade.action === 'BUY' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
                }`}>
                  {trade.action}
                </span>
                <span className={`text-xs ${trade.side === 'YES' ? 'text-green-400' : 'text-red-400'}`}>
                  {trade.side}
                </span>
              </div>
              <div className="text-right">
                <span className="text-white text-sm">${trade.total_usd?.toFixed(2)}</span>
                <span className="text-gray-500 text-xs ml-2">@ ${trade.price?.toFixed(4)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
