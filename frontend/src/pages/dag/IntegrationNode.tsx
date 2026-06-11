// Custom React Flow node: a status-tinted card that links to the integration.

import { Handle, Position, type NodeProps } from '@xyflow/react'
import { memo, type CSSProperties, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { STATUS_LABELS, statusColors } from '../../components/StatusBadge'
import { NODE_HEIGHT, NODE_WIDTH, type IntegrationFlowNode } from './useDagLayout'

const invisibleHandle: CSSProperties = { opacity: 0 }

function IntegrationNode({ data }: NodeProps<IntegrationFlowNode>) {
  const navigate = useNavigate()
  const { bg, fg } = statusColors(data.status)

  const open = () => navigate(`/integrations/${data.id}`)
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter') open()
  }

  const cardStyle: CSSProperties = {
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    boxSizing: 'border-box',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    gap: 2,
    padding: '6px 10px',
    background: 'var(--color-surface)',
    border: '1px solid var(--color-border)',
    borderLeft: `6px solid ${fg}`,
    borderRadius: 'var(--radius-md)',
    boxShadow: 'var(--shadow-card)',
    cursor: 'pointer',
    font: 'inherit',
  }
  if (data.isRoot) {
    cardStyle.outline = '3px solid var(--ts-accent)'
    cardStyle.outlineOffset = 2
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Open integration ${data.name}`}
      onClick={open}
      onKeyDown={onKeyDown}
      style={cardStyle}
    >
      <Handle type="target" position={Position.Left} style={invisibleHandle} isConnectable={false} />
      <div
        title={data.name}
        style={{
          fontWeight: 600,
          fontSize: 13,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          color: 'var(--color-text)',
        }}
      >
        {data.name}
      </div>
      <div
        style={{
          alignSelf: 'flex-start',
          fontSize: 11,
          fontWeight: 600,
          lineHeight: 1.2,
          padding: '1px 6px',
          borderRadius: 'var(--radius-sm)',
          background: bg,
          color: fg,
        }}
      >
        {STATUS_LABELS[data.status] ?? data.status}
      </div>
      <Handle type="source" position={Position.Right} style={invisibleHandle} isConnectable={false} />
    </div>
  )
}

export default memo(IntegrationNode)
