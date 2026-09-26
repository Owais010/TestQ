import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { TestCase } from "../lib/types";
import { Empty, ErrorState, Loading } from "./ui";
interface Strategy {
  summary?: string;
  items?: {
    id: string;
    category: string;
    target: string;
    description: string;
    risk_level: string;
    priority: string;
  }[];
}
export default function TestPlan({
  id,
  active,
  view,
}: {
  id: string;
  active: boolean;
  view: "Strategy" | "Test plan";
}) {
  const endpoint = view === "Strategy" ? "strategy" : "test-cases";
  const query = useQuery({
    queryKey: ["plan", id, endpoint],
    queryFn: ({ signal }) =>
      api<Strategy | { test_cases: TestCase[] }>(
        `/api/test-runs/${id}/${endpoint}`,
        { signal },
      ),
    refetchInterval: active ? 5000 : false,
  });
  if (query.isPending) return <Loading />;
  if (query.error)
    return <ErrorState error={query.error} retry={() => query.refetch()} />;
  if (view === "Strategy") {
    const strategy = query.data as Strategy;
    return strategy.items?.length ? (
      <>
        <div className="context-note">
          <strong>Planning, with context.</strong>
          <p>{strategy.summary}</p>
          <p>
            Backend-generated strategy. Validate priorities against your
            application’s intended behavior.
          </p>
        </div>
        <div className="map-grid">
          {strategy.items.map((item) => (
            <article className="page-card" key={item.id}>
              <div>
                <span className="eyebrow">{item.category}</span>
                <span className="tag">{item.risk_level} risk</span>
              </div>
              <h3>{item.target}</h3>
              <p>{item.description}</p>
              <div className="page-counts">
                <span>{item.id}</span>
                <span>Priority: {item.priority}</span>
              </div>
            </article>
          ))}
        </div>
      </>
    ) : (
      <Empty
        title="No strategy recorded."
        text="Planning output appears here when it is available from the backend."
      />
    );
  }
  const cases = (query.data as { test_cases: TestCase[] }).test_cases;
  return cases.length ? (
    <section className="panel compact">
      <h2>{cases.length} test definitions</h2>
      {cases.map((item) => (
        <details key={item.id}>
          <summary>
            <span className="tag">{item.type}</span>
            <strong>{item.title}</strong>
            <small>
              {item.source} · {item.priority}
            </small>
          </summary>
          <pre>{JSON.stringify(item.definition, null, 2)}</pre>
        </details>
      ))}
    </section>
  ) : (
    <Empty
      title="The plan is still taking shape."
      text="Generated and baseline test definitions appear here, including tests not yet executed."
    />
  );
}
