// Dagre-based layout for the dependency graph. Converts a GraphPayload from
// the API into positioned React Flow nodes/edges. Only 'flow' edges feed the
// dagre hierarchy; 'integrated' edges are rendered but impose no ranking.

import * as dagre from '@dagrejs/dagre'
import { MarkerType, type Edge, type Node } from '@xyflow/react'
import type { GraphPayload, Status } from '../../api/types'

export const NODE_WIDTH = 200
export const NODE_HEIGHT = 56

export type IntegrationNodeData = {
  /** Integration id, duplicated into data so the node component can navigate. */
  id: string
  name: string
  status: Status
  isRoot: boolean
}

export type IntegrationFlowNode = Node<IntegrationNodeData, 'integration'>

export function layoutGraph(payload: GraphPayload): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setGraph({
    rankdir: 'LR',
    nodesep: 30,
    ranksep: 90,
    acyclicer: 'greedy',
    ranker: 'network-simplex',
  })
  g.setDefaultEdgeLabel(() => ({}))

  for (const node of payload.nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  // Only data-flow edges define the left-to-right hierarchy.
  for (const edge of payload.edges) {
    if (edge.kind === 'flow') g.setEdge(edge.source, edge.target)
  }

  dagre.layout(g)

  const nodes: Node[] = payload.nodes.map((n) => {
    const pos = g.node(n.id)
    return {
      id: n.id,
      type: 'integration',
      // dagre returns center coordinates; React Flow wants the top-left corner.
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { id: n.id, name: n.name, status: n.status, isRoot: n.is_root },
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    } satisfies IntegrationFlowNode
  })

  const edges: Edge[] = payload.edges.map((e) =>
    e.kind === 'flow'
      ? {
          id: `flow:${e.source}->${e.target}`,
          source: e.source,
          target: e.target,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: 'var(--ts-primary)', strokeWidth: 2 },
        }
      : {
          id: `integrated:${e.source}->${e.target}`,
          source: e.source,
          target: e.target,
          style: { stroke: '#8a9aa4', strokeWidth: 2, strokeDasharray: '6 4' },
        },
  )

  return { nodes, edges }
}
