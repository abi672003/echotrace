import { useEffect, useState } from "react";
import { fetchArticle, fetchSampleArticles, investigate, type InvestigateResult, type SampleArticle } from "./api";
import CaseBoard from "./components/CaseBoard";
import VerdictStamp from "./components/VerdictStamp";
import "./app.css";

export default function App() {
  const [samples, setSamples] = useState<SampleArticle[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [targetText, setTargetText] = useState<string>("");
  const [result, setResult] = useState<InvestigateResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSampleArticles(14).then(setSamples).catch((e) => setError(String(e)));
  }, []);

  async function openCase(sample: SampleArticle) {
    setLoading(true);
    setError(null);
    setSelectedId(sample.id);
    setResult(null);
    try {
      const article = await fetchArticle(sample.id);
      setTargetText(article.text);
      const inv = await investigate(article.text, article.id, 6);
      setResult(inv);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="case-drawer">
        <h1 className="typewriter drawer-title">ECHOTRACE</h1>
        <p className="drawer-sub">open case file</p>
        <div className="case-list">
          {samples.map((s) => (
            <button
              key={s.id}
              className={`case-item ${selectedId === s.id ? "case-item-active" : ""}`}
              onClick={() => openCase(s)}
            >
              <span className="case-item-preview">{s.preview.slice(0, 90)}…</span>
            </button>
          ))}
        </div>
      </aside>

      <main className="board-area">
        {!selectedId && (
          <div className="empty-state typewriter">SELECT A CASE FILE FROM THE DRAWER</div>
        )}
        {loading && <div className="empty-state typewriter">RETRIEVING EVIDENCE…</div>}
        {error && <div className="empty-state error">{error}</div>}

        {result && !loading && (
          <>
            <VerdictStamp
              modelAvailable={result.model_available}
              aggregatedScore={result.aggregated_score}
              singleInstanceScore={result.single_instance_score}
            />
            <CaseBoard
              targetId={selectedId!}
              targetPreview={targetText.slice(0, 220)}
              evidence={result.evidence}
              modelAvailable={result.model_available}
            />
          </>
        )}
      </main>
    </div>
  );
}
