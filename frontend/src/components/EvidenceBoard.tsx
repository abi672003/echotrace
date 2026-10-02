import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo, useState } from 'react'
import type { ClusterType, GraphOut } from '../api/types'
import { displaySubmitter, useHideNames } from '../context/HideNamesContext'

const VERDICT_COLOR_VAR: Record<ClusterType, string> = {
  coordinated_paraphrase_campaign: '--campaign',
  form_letter: '--form',
  organic_agreement: '--organic',
  insufficient_evidence: '--unsure',
}

const RADIUS_SCALE = 420
const RADIUS_BASE = 150
const LEX_DASH_THRESHOLD = 0.35
const MAX_NODES = 60

interface SheetNodeData {
  excerpt: string
  submitterLabel: string
  submitterHash: string
  isMedoid: boolean
  aiScore: number | null
  citationNumber: number | null
  verdictColorVar: string
  isSelected: boolean
  [key: string]: unknown
}

function SheetNode({ data }: NodeProps<Node<SheetNodeData>>) {
  const { hideNames } = useHideNames()
  const name = displaySubmitter(data.submitterLabel, hideNames, data.submitterHash)

  return (
    <div
      className="relative rounded-sheet bg-paper p-2 shadow-sheet"
      style={{
        width: data.isMedoid ? 168 : 128,
        border: data.isMedoid ? '2px solid var(--ink)' : '1px solid var(--rule)',
        outline: data.citationNumber
          ? `2px solid var(${data.verdictColorVar})`
          : data.isSelected
            ? '2px solid var(--thread)'
            : undefined,
        outlineOffset: 2,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ visibility: 'hidden' }} />
      <Handle type="source" position={Position.Bottom} style={{ visibility: 'hidden' }} />
      <p
        className="font-serif text-xs leading-snug text-ink"
        style={{
          display: '-webkit-box',
          WebkitLineClamp: 3,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {data.excerpt}
      </p>
      <p className="mt-1 truncate text-[10px] text-ink-soft">{name}</p>
      {data.aiScore !== null && (
        <span
          className="absolute bottom-1 right-1 block h-2 w-2 rounded-chip bg-thread"
          style={{ opacity: Math.max(0.15, data.aiScore) }}
          aria-hidden="true"
          title="AI-style signal (unverified)"
        />
      )}
      {data.citationNumber !== null && (
        <span
          className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-chip bg-paper text-[10px] font-semibold text-ink"
          style={{ border: `2px solid var(${data.verdictColorVar})` }}
        >
          {data.citationNumber}
        </span>
      )}
    </div>
  )
}

const nodeTypes: NodeTypes = { sheet: SheetNode }

interface EvidenceBoardProps {
  graph: GraphOut
  verdictType: ClusterType
  citedDocumentIds: number[]
  selectedId: number | null
  onSelect: (docId: number) => void
  onCompare: (a: number, b: number) => void
}

export function EvidenceBoard({
  graph,
  verdictType,
  citedDocumentIds,
  selectedId,
  onSelect,
  onCompare,
}: EvidenceBoardProps) {
  const [pendingCompareId, setPendingCompareId] = useState<number | null>(null)
  const [settled, setSettled] = useState(false)
  const [viewAsList, setViewAsList] = useState(false)
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null)
  const { hideNames } = useHideNames()

  useEffect(() => {
    setSettled(false)
    const settleTimer = window.setTimeout(() => setSettled(true), 20)
    return () => window.clearTimeout(settleTimer)
  }, [graph])

  // fitView only auto-runs once on mount; nodes are still at the origin then (pre-settle),
  // so re-fit once they've actually spread out to their real positions.
  useEffect(() => {
    if (!settled || !flowInstance) return
    const fitTimer = window.setTimeout(() => flowInstance.fitView({ duration: 400 }), 30)
    return () => window.clearTimeout(fitTimer)
  }, [settled, flowInstance])

  const truncated = graph.nodes.length > MAX_NODES
  const visibleNodes = graph.nodes.slice(0, MAX_NODES)
  const medoid = visibleNodes.find((n) => n.is_medoid) ?? visibleNodes[0]
  const others = visibleNodes.filter((n) => n.id !== medoid?.id)

  const nodes: Node<SheetNodeData>[] = useMemo(() => {
    return visibleNodes.map((n) => {
      let x = 0
      let y = 0
      if (settled && medoid && n.id !== medoid.id) {
        const index = others.findIndex((o) => o.id === n.id)
        const angle = (index / Math.max(1, others.length)) * 2 * Math.PI
        const radius = (1 - n.sim) * RADIUS_SCALE + RADIUS_BASE
        x = Math.cos(angle) * radius
        y = Math.sin(angle) * radius
      }
      const citationIndex = citedDocumentIds.indexOf(n.id)
      return {
        id: String(n.id),
        type: 'sheet',
        position: { x, y },
        data: {
          excerpt: n.excerpt,
          submitterLabel: n.submitter_label,
          submitterHash: String(n.id),
          isMedoid: n.id === medoid?.id,
          aiScore: n.ai_score,
          citationNumber: citationIndex >= 0 ? citationIndex + 1 : null,
          verdictColorVar: VERDICT_COLOR_VAR[verdictType],
          isSelected: n.id === selectedId,
        },
        draggable: false,
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleNodes, medoid, others, citedDocumentIds, verdictType, selectedId, settled])

  const edges: Edge[] = useMemo(() => {
    if (!medoid) return []
    return graph.edges
      .filter((e) => visibleNodes.some((n) => n.id === e.target))
      .map((e) => ({
        id: `${e.source}-${e.target}`,
        source: String(e.source),
        target: String(e.target),
        type: 'straight',
        style: {
          strokeWidth: 1 + e.sim * 3,
          stroke: 'var(--thread)',
          strokeDasharray: e.lex < LEX_DASH_THRESHOLD ? '4 4' : undefined,
        },
      }))
  }, [graph.edges, medoid, visibleNodes])

  const handleNodeClick = (event: React.MouseEvent, node: Node) => {
    const id = Number(node.id)
    if (event.shiftKey && pendingCompareId !== null && pendingCompareId !== id) {
      onCompare(pendingCompareId, id)
      setPendingCompareId(null)
      return
    }
    setPendingCompareId(id)
    onSelect(id)
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        {truncated ? (
          <p className="text-xs text-ink-soft">
            Showing {MAX_NODES} of {graph.nodes.length} — view all in list.
          </p>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={() => setViewAsList((value) => !value)}
          className="rounded-control border border-rule px-2 py-1 text-xs font-semibold text-ink-soft hover:text-ink"
        >
          {viewAsList ? 'View as board' : 'View as list'}
        </button>
      </div>

      {viewAsList ? (
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Family members, an accessible alternative to the evidence board</caption>
          <thead>
            <tr className="text-xs text-ink-soft">
              <th scope="col" className="py-1">Comment</th>
              <th scope="col" className="py-1 text-right">Similarity</th>
              <th scope="col" className="py-1 text-right">Lexical overlap</th>
              <th scope="col" className="py-1 text-right">AI-style signal (unverified)</th>
            </tr>
          </thead>
          <tbody>
            {visibleNodes.map((n) => (
              <tr key={n.id} className="border-t border-rule">
                <td className="py-2 pr-2">
                  <button
                    type="button"
                    onClick={() => onSelect(n.id)}
                    className="text-left text-thread hover:underline"
                  >
                    {n.excerpt.slice(0, 80)}
                    {n.is_medoid ? ' (representative comment)' : ''}
                  </button>
                  <div className="text-xs text-ink-soft">
                    {displaySubmitter(n.submitter_label, hideNames, String(n.id))}
                  </div>
                </td>
                <td className="py-2 text-right" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {n.sim.toFixed(2)}
                </td>
                <td className="py-2 text-right" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {n.lex.toFixed(2)}
                </td>
                <td className="py-2 text-right" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {n.ai_score !== null ? n.ai_score.toFixed(2) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div
          className="evidence-board rounded-sheet border border-rule bg-desk"
          style={{ height: 500 }}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={handleNodeClick}
            onInit={setFlowInstance}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background color="var(--rule)" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      )}
    </div>
  )
}
