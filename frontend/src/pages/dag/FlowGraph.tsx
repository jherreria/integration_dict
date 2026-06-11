// React Flow canvas for a GraphPayload, laid out with dagre.

import {
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  useNodesState,
  type NodeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo } from 'react'
import type { GraphPayload } from '../../api/types'
import DagLegend from './DagLegend'
import IntegrationNode from './IntegrationNode'
import { layoutGraph, type IntegrationFlowNode } from './useDagLayout'

// Declared at module scope so React Flow does not warn about re-created types.
const nodeTypes: NodeTypes = { integration: IntegrationNode }

export default function FlowGraph({ payload }: { payload: GraphPayload }) {
  const layout = useMemo(() => layoutGraph(payload), [payload])
  const [nodes, setNodes, onNodesChange] = useNodesState<IntegrationFlowNode>(
    layout.nodes as IntegrationFlowNode[],
  )

  useEffect(() => {
    setNodes(layout.nodes as IntegrationFlowNode[])
  }, [layout, setNodes])

  return (
    <div className="card" style={{ height: 'calc(100vh - 210px)', minHeight: 420, padding: 0, overflow: 'hidden' }}>
      <ReactFlow
        nodes={nodes}
        edges={layout.edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        fitView
        nodesConnectable={false}
        nodesDraggable
        elementsSelectable
        proOptions={{ hideAttribution: true }}
        onlyRenderVisibleElements={nodes.length > 150}
        minZoom={0.1}
      >
        <Background />
        <Controls />
        <MiniMap />
        <Panel position="top-right">
          <DagLegend />
        </Panel>
      </ReactFlow>
    </div>
  )
}
