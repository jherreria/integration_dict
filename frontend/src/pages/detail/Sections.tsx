// Renders the section cards of the detail page (Overview, Systems & Data
// Flow, …) with one FieldRow per registered field.
import type { IntegrationDetail } from '../../api/types'
import type { EditOptions } from './fields'
import { SECTIONS, fieldsForSection } from './fields'
import FieldRow from './FieldRow'
import type { FormValues } from './useIntegrationForm'

interface SectionsProps {
  detail: IntegrationDetail
  editing: boolean
  draft: FormValues
  set: <K extends keyof FormValues>(field: K, value: FormValues[K]) => void
  options: EditOptions | null
  fieldErrors: Record<string, string>
}

export default function Sections({ detail, editing, draft, set, options, fieldErrors }: SectionsProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {SECTIONS.map((section) => (
        <section className="card" key={section.key}>
          <h2>{section.title}</h2>
          {fieldsForSection(section.key).map((def) => (
            <FieldRow
              key={def.key}
              def={def}
              detail={detail}
              editing={editing}
              draft={draft}
              set={set}
              options={options}
              error={fieldErrors[def.key]}
            />
          ))}
        </section>
      ))}
    </div>
  )
}
