import { useRef, useState, type FormEvent } from 'react'
import { Loader2, Save, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { APIError, createID, saveReview, type MeetingResult, type ReviewRequest, type WorkerConfig } from './api'

type ActionDraft = ReviewRequest['actions'][number]
type ReviewStatus = ActionDraft['review_status']
type NewAction = NonNullable<ReviewRequest['new_actions']>[number]
type NewActionDraft = Omit<NewAction, 'review_status'> & { draft_id: string; review_status: NewAction['review_status'] | '' }
const status = (value: string): ReviewStatus => value === 'human_confirmed' || value === 'rejected' ? value : 'needs_review'

export function MeetingReviewPanel({ result, config, onSaved, onClose, onReload }: {
  result: MeetingResult; config: WorkerConfig; onSaved: (result: MeetingResult) => void; onClose: () => void; onReload: () => void
}) {
  // Snapshot the revision at opening. Polling must never silently replace a draft.
  const [original] = useState(result)
  const [reviewer, setReviewer] = useState('')
  const [note, setNote] = useState('')
  const [names, setNames] = useState<Record<string, string>>({ ...original.speaker_names })
  const [actions, setActions] = useState<ActionDraft[]>(() => original.protocol.action_items.map(item => ({
    id: item.id, task: item.task, assignee: item.assignee || '', deadline_text: item.deadline_text || '',
    deadline_date: item.deadline_date || null, priority: item.priority, review_status: status(item.review_status),
  })))
  const [changed, setChanged] = useState<Set<string>>(new Set())
  const [newActions, setNewActions] = useState<NewActionDraft[]>([])
  const [findings, setFindings] = useState<Record<string, ReviewStatus>>({})
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [busy, setBusy] = useState(false)
  const request = useRef<{ fingerprint: string; id: string } | null>(null)
  const speakers = [...new Set(original.transcript.segments.map(segment => segment.speaker).filter((value): value is string => Boolean(value)))]
  const passages = original.transcript.segments.filter(segment => segment.text.trim())
  const otherFindings = [
    ...original.protocol.decisions.map(item => ({ ...item, kind: 'Decision' })),
    ...original.protocol.topics.map(item => ({ ...item, kind: 'Topic' })),
    ...original.protocol.open_questions.map(item => ({ ...item, kind: 'Question' })),
    ...original.protocol.risks.map(item => ({ ...item, kind: 'Risk' })),
  ]
  const nameChanges = Object.fromEntries(speakers.filter(speaker => (names[speaker] || '').trim() !== (original.speaker_names?.[speaker] || '')).map(speaker => [speaker, (names[speaker] || '').trim()]))
  const dirty = changed.size > 0 || Object.keys(nameChanges).length > 0 || Object.keys(findings).length > 0 || newActions.length > 0
  const newActionsReady = newActions.every(item => item.task.trim() && item.segment_ids.length && item.review_status)

  function edit(id: string, patch: Partial<ActionDraft>) {
    setActions(previous => previous.map(item => item.id === id ? { ...item, ...patch } : item))
    setChanged(previous => new Set(previous).add(id))
  }
  function editNew(id: string, patch: Partial<NewActionDraft>) {
    setNewActions(previous => previous.map(item => item.draft_id === id ? { ...item, ...patch } : item))
  }
  function addAction() {
    setNewActions(previous => [...previous, { draft_id: createID(), task: '', assignee: '', deadline_text: '',
      deadline_date: null, priority: 'not_specified', segment_ids: [], review_status: '' }])
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!dirty || busy || !newActionsReady) return
    const body = {
      expected_revision: original.review_revision || 0, reviewer: reviewer.trim(), note: note.trim(),
      speaker_names: nameChanges,
      actions: actions.filter(item => changed.has(item.id)).map(item => ({ ...item, assignee: item.assignee?.trim() || null, deadline_text: item.deadline_text?.trim() || null })),
      findings: Object.entries(findings).map(([id, review_status]) => ({ id, review_status })),
      new_actions: newActions.map(item => ({ task: item.task.trim(), assignee: item.assignee?.trim() || null,
        deadline_text: item.deadline_text?.trim() || null, deadline_date: item.deadline_date, priority: item.priority,
        segment_ids: item.segment_ids, review_status: item.review_status as NewAction['review_status'] })),
    }
    const fingerprint = JSON.stringify(body)
    if (request.current?.fingerprint !== fingerprint) request.current = { fingerprint, id: createID() }
    setBusy(true); setError(''); setConflict(false)
    try {
      onSaved(await saveReview(config, original.job.id, { ...body, request_id: request.current.id }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Review could not be saved. Retry the same changes.')
      setConflict(cause instanceof APIError && cause.status === 409)
    } finally { setBusy(false) }
  }

  return <section className="mi-review-panel" aria-labelledby="mi-review-title">
    <div className="mi-review-heading"><div><h3 id="mi-review-title">Review the meeting</h3><p>Confirm who spoke and what was agreed. Every saved change is recorded in the review history.</p></div><button type="button" className="mi-icon-button" onClick={onClose} disabled={busy} aria-label="Close review"><X /></button></div>
    <form className="mi-form" onSubmit={event => void submit(event)}><fieldset disabled={busy}>
      <label>Reviewer name<Input value={reviewer} onChange={event => setReviewer(event.target.value)} required maxLength={100} placeholder="Name for the review history" /></label>
      {speakers.length > 0 && <div className="mi-review-speakers"><h4>Identify participants</h4><p>Listen to the source recording before assigning a name. Naming a speaker does not assign that person every task they mentioned.</p><div className="mi-form-columns">{speakers.map((speaker, index) => <label key={speaker}>Speaker {index + 1}<Input value={names[speaker] || ''} maxLength={200} placeholder="Participant name" onChange={event => setNames(previous => ({ ...previous, [speaker]: event.target.value }))} /><small>{speaker}</small></label>)}</div></div>}
      <div className="mi-review-actions"><h4>Поручения · Action items</h4>{!actions.length && <p className="mi-muted">No actions were extracted. Add any missed commitment from the original transcript before using this report.</p>}
        {actions.map((item, index) => <article key={item.id} className="mi-review-card"><h5>Action {index + 1}</h5>
          <label>Task<Textarea value={item.task} required maxLength={4000} rows={2} onChange={event => edit(item.id, { task: event.target.value })} /></label>
          <div className="mi-form-columns"><label>Owner<Input value={item.assignee || ''} maxLength={200} placeholder="Unassigned" list="mi-participant-names" onChange={event => edit(item.id, { assignee: event.target.value })} /></label><label>Agreed date<Input type="date" value={item.deadline_date || ''} onChange={event => edit(item.id, { deadline_date: event.target.value || null })} /></label></div>
          <label>Deadline as spoken<Input value={item.deadline_text || ''} maxLength={500} placeholder="Not specified" onChange={event => edit(item.id, { deadline_text: event.target.value })} /></label>
          <div className="mi-form-columns"><label>Priority<select value={item.priority} onChange={event => edit(item.id, { priority: event.target.value as ActionDraft['priority'] })}><option value="not_specified">Not specified</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent</option></select></label><label>Review decision<select value={item.review_status} onChange={event => edit(item.id, { review_status: event.target.value as ReviewStatus })}><option value="needs_review">Needs review</option><option value="human_confirmed">I confirm this action</option><option value="rejected">Reject this action</option></select></label></div>
          {original.protocol.action_items[index].evidence.quote && <blockquote dir="auto">{original.protocol.action_items[index].evidence.quote}</blockquote>}
          <small>A calendar date is saved only when you supply one. Check relative dates against the actual meeting date.</small>
        </article>)}
        {newActions.map((item, index) => <article key={item.draft_id} className="mi-review-card" aria-label={`Missed action ${index + 1}`}><div className="mi-review-heading"><h5>Missed action {index + 1}</h5><Button type="button" variant="ghost" size="sm" onClick={() => setNewActions(previous => previous.filter(draft => draft.draft_id !== item.draft_id))} aria-label={`Remove missed action ${index + 1}`}>Remove</Button></div>
          <label>Missed task<Textarea value={item.task} required maxLength={4000} rows={2} onChange={event => editNew(item.draft_id, { task: event.target.value })} /></label>
          <div className="mi-form-columns"><label>Missed action owner<Input value={item.assignee || ''} maxLength={200} placeholder="Unassigned" list="mi-participant-names" onChange={event => editNew(item.draft_id, { assignee: event.target.value })} /></label><label>Missed action date<Input type="date" value={item.deadline_date || ''} onChange={event => editNew(item.draft_id, { deadline_date: event.target.value || null })} /></label></div>
          <label>Missed action deadline as spoken<Input value={item.deadline_text || ''} maxLength={500} placeholder="Not specified" onChange={event => editNew(item.draft_id, { deadline_text: event.target.value })} /></label>
          <label>Source passages<select multiple required size={Math.min(5, Math.max(2, passages.length))} value={item.segment_ids} onChange={event => editNew(item.draft_id, { segment_ids: Array.from(event.target.selectedOptions, option => option.value) })}>{passages.map(segment => <option key={segment.id} value={segment.id}>{segment.start != null ? `${segment.start.toFixed(1)}s · ` : ''}{segment.speaker ? `${names[segment.speaker] || segment.speaker}: ` : ''}{segment.text.slice(0, 180)}</option>)}</select><small>Select the passage establishing the commitment. Include surrounding replies when needed; the original excerpt will be attached unchanged.</small></label>
          {passages.filter(segment => item.segment_ids.includes(segment.id)).map(segment => <blockquote key={segment.id} dir="auto">{segment.text}</blockquote>)}
          <div className="mi-form-columns"><label>Missed action priority<select value={item.priority} onChange={event => editNew(item.draft_id, { priority: event.target.value as NewAction['priority'] })}><option value="not_specified">Not specified</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent</option></select></label><label>Missed action review decision<select required value={item.review_status} onChange={event => editNew(item.draft_id, { review_status: event.target.value as NewActionDraft['review_status'] })}><option value="">Choose a review decision</option><option value="human_confirmed">I confirm this commitment from the source</option><option value="needs_review">Keep for further review</option></select></label></div>
        </article>)}
        <Button type="button" variant="outline" disabled={!passages.length || newActions.length >= 50} onClick={addAction}>Add missed action</Button>
        {!passages.length && <p className="mi-muted">A transcript passage is required before adding an action. Check the recording if no speech was recognized.</p>}
      </div>
      <datalist id="mi-participant-names">{[...new Set(Object.values(names).filter(Boolean))].map(name => <option key={name} value={name} />)}</datalist>
      {otherFindings.length > 0 && <details className="mi-review-findings"><summary>Review decisions, topics, questions and risks ({otherFindings.length})</summary>{otherFindings.map(item => <label key={item.id}><strong>{item.kind}</strong><span dir="auto">{item.text}</span>{item.evidence.quote && <blockquote dir="auto">{item.evidence.quote}</blockquote>}<select value={findings[item.id] || ''} aria-label={`Review ${item.kind}: ${item.text}`} onChange={event => { const value = event.target.value; setFindings(previous => { const next = { ...previous }; if (value) next[item.id] = value as ReviewStatus; else delete next[item.id]; return next }) }}><option value="">Keep current review status</option><option value="human_confirmed">I confirm this finding</option><option value="needs_review">Needs review</option><option value="rejected">Reject this finding</option></select></label>)}</details>}
      <label>Review note<Textarea value={note} maxLength={2000} rows={2} placeholder="Explain any correction or uncertainty" onChange={event => setNote(event.target.value)} /></label>
    </fieldset>
    {error && <p className="mi-error-text" role="alert">{error}</p>}
    {conflict && <Button type="button" variant="outline" onClick={onReload}>Reload report and discard these edits</Button>}
    <div className="mi-review-footer"><Button type="submit" disabled={!dirty || !newActionsReady || !reviewer.trim() || busy || conflict}>{busy ? <Loader2 className="animate-spin" /> : <Save />}{busy ? 'Saving and updating exports…' : 'Save review'}</Button><span>Report revision {original.review_revision || 0}</span></div>
    </form>
  </section>
}
