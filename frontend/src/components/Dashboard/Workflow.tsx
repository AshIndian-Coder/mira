type WorkflowProps = {
  totalMaterials: number
  candidatePairs: number
  pendingReview: number
  approved: number
  mappings: number
  loading: boolean
}

type WorkflowStep = {
  number: string
  title: string
  description: string
  value: number
}

function Workflow({
  totalMaterials,
  candidatePairs,
  pendingReview,
  approved,
  mappings,
  loading,
}: WorkflowProps) {
  const steps: WorkflowStep[] = [
    {
      number: '01',
      title: 'Ingest',
      description: 'Materials available',
      value: totalMaterials,
    },
    {
      number: '02',
      title: 'Match',
      description: 'Candidate relationships',
      value: candidatePairs,
    },
    {
      number: '03',
      title: 'Review',
      description: 'Awaiting validation',
      value: pendingReview,
    },
    {
      number: '04',
      title: 'Harmonize',
      description: 'Approved relationships',
      value: approved,
    },
    {
      number: '05',
      title: 'Map',
      description: 'Common mappings',
      value: mappings,
    },
  ]

  return (
    <div className="workflow workflow-enhanced">
      {steps.map((step, index) => (
        <div key={step.number} className="workflow-group">
          <div className="workflow-step">
            <span>{step.number}</span>
            <strong>{step.title}</strong>
            <small>{step.description}</small>
            <b>{loading ? '—' : step.value.toLocaleString()}</b>
          </div>

          {index < steps.length - 1 && (
            <div className="workflow-line" />
          )}
        </div>
      ))}
    </div>
  )
}

export default Workflow
