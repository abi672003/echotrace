import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import * as api from "../api";
import type { InvestigationSummary } from "../api";
import VerdictStamp from "../components/VerdictStamp";
import CaseBoard from "../components/CaseBoard";

function verdictLabel(v: string | null): string {
  if (v === "ai_reworded_copy") return "AI-REWORDED COPY";
  if (v === "independent_reporting") return "INDEPENDENT REPORTING";
  return "PENDING";
}

function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return "TARGET";
  }
}

export default function History() {
  const [items, setItems] = useState<InvestigationSummary[]>([]);
  const [selected, setSelected] = useState<InvestigationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .fetchInvestigations(30)
      .then(setItems)
      .catch((e) => setError(e instanceof api.ApiError ? e.message : "Could not load history."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="history-page">
      <aside className="history-list">
        <h2 className="typewriter history-title">CASE HISTORY</h2>
        {loading && <p className="empty-state">Loading…</p>}
        {error && <p className="empty-state error">{error}</p>}
        {!loading && items.length === 0 && <p className="empty-state">No investigations yet.</p>}

        {items.map((item) => (
          <button
            key={item.id}
            className={`history-item ${selected?.id === item.id ? "history-item-active" : ""}`}
            onClick={() => setSelected(item)}
          >
            <span className={`history-verdict-tag verdict-${item.verdict ?? "pending"}`}>
              {verdictLabel(item.verdict)}
            </span>
            <span className="history-item-preview mono">
              {item.target_url ?? item.target_text_preview.slice(0, 70)}
            </span>
            <span className="history-item-date mono">{new Date(item.created_at).toLocaleString()}</span>
          </button>
        ))}
      </aside>

      <main className="history-detail">
        {!selected && <div className="empty-state typewriter">SELECT A CASE FROM THE HISTORY</div>}
        {selected && (
          <motion.div key={selected.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>
            <VerdictStamp
              modelAvailable={selected.aggregated_score !== null}
              aggregatedScore={selected.aggregated_score ?? undefined}
              singleInstanceScore={selected.single_instance_score ?? undefined}
            />
            <CaseBoard
              targetLabel={selected.target_url ? hostnameOf(selected.target_url) : "PASTED TEXT"}
              targetPreview={selected.target_text_preview}
              evidence={selected.evidence}
              modelAvailable={selected.aggregated_score !== null}
            />
          </motion.div>
        )}
      </main>
    </div>
  );
}
