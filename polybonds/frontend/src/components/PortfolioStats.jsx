import { usePortfolio } from '../hooks/useApi';

function StatCard({ title, value, icon, color = 'blue' }) {
  const colors = {
    blue: 'bg-blue-900/50 border-blue-700',
    green: 'bg-green-900/50 border-green-700',
    yellow: 'bg-yellow-900/50 border-yellow-700',
    purple: 'bg-purple-900/50 border-purple-700',
  };

  return (
    <div className={`${colors[color]} border rounded-lg p-4`}>
      <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
        <span>{icon}</span>
        <span>{title}</span>
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
    </div>
  );
}

export default function PortfolioStats() {
  const { data: portfolio, loading, error } = usePortfolio();

  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="bg-gray-800 border border-gray-700 rounded-lg p-4 animate-pulse">
            <div className="h-4 bg-gray-700 rounded w-1/2 mb-2"></div>
            <div className="h-8 bg-gray-700 rounded w-3/4"></div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 mb-6">
        <p className="text-red-400">Failed to load portfolio: {error}</p>
      </div>
    );
  }

  const totalValue = portfolio?.total_value_usd || 0;
  const cashBalance = portfolio?.cash_balance_usd || 0;
  const positionsValue = portfolio?.positions_value_usd || 0;
  const roi = portfolio?.roi_pct || 0;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <StatCard
        title="Total Value"
        value={`$${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
        icon="💰"
        color="blue"
      />
      <StatCard
        title="Cash Balance"
        value={`$${cashBalance.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
        icon="💵"
        color="green"
      />
      <StatCard
        title="Positions"
        value={`$${positionsValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
        icon="📈"
        color="yellow"
      />
      <StatCard
        title="ROI"
        value={`${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%`}
        icon="📊"
        color="purple"
      />
    </div>
  );
}
