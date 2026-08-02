import { BacktestDashboard } from "../../backtest-dashboard";

export default async function FundBacktestPage({ params }: { params: Promise<{ fund: string }> }) {
  const { fund } = await params;
  return <BacktestDashboard fundKey={fund} />;
}
