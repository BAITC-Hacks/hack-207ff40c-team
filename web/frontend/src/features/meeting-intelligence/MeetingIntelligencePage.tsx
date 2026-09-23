import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { AlertCircle, CheckCheck, ClipboardList, History, ShieldCheck, Download, FileAudio, FileText, Loader2, Mic, RefreshCw, Search, Square, Upload, X } from 'lucide-react'
import { Layout } from '@/components/Layout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { APIError, capabilities, cancelJob, createID, downloadExport, getResult, listJobs, loadAudio, retryJob, startRecording, stopRecording, submitMeeting, type Capabilities, type JobRecord, type JobStage, type MeetingResult, type ProtocolItem, type SourcedItem, type WorkerConfig } from './api'
import './meeting-intelligence.css'
import { MeetingBrowserPanel } from './MeetingBrowserPanel'
import { MeetingReviewPanel } from './MeetingReviewPanel'

const tokenKey = 'mi.stationToken'
const selectionKey = 'mi.selectedJob'
const finished = new Set<JobStage>(['completed', 'failed', 'cancelled'])
const stageNames: Record<JobStage, string> = { recording: "Запись", queued: "В очереди", preprocessing: "Подготовка аудио", transcribing: "Распознавание речи", diarizing: "Разделение голосов", extracting: "Подготовка протокола", validating: "Проверка источников", exporting: "Подготовка документов", completed: "Обработано", failed: "Нужна проверка", cancelled: "Отменено" }
const stages: JobStage[] = ['queued', 'preprocessing', 'transcribing', 'diarizing', 'extracting', 'validating', 'exporting', 'completed']

function readSession(key: string) { try { return sessionStorage.getItem(key) || '' } catch { return '' } }
function saveSession(key: string, value: string) { try { if (value) sessionStorage.setItem(key, value); else sessionStorage.removeItem(key) } catch { /* The current page still works when browser storage is unavailable. */ } }
function message(error: unknown) { return error instanceof Error ? error.message : "Станция не смогла выполнить запрос." }
function time(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  const value = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(value / 3600)
  return `${hours ? `${hours}:` : ''}${Math.floor(value / 60 % 60).toString().padStart(2, '0')}:${(value % 60).toString().padStart(2, '0')}`
}
function date(value: string, full = false) { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleString('ru-RU', { month: 'short', day: 'numeric', ...(full ? { year: 'numeric', hour: '2-digit', minute: '2-digit' } : {}) }) }
function size(bytes: number) { return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} КБ` : `${(bytes / 1024 / 1024).toFixed(1)} МБ` }
function title(job: JobRecord) { return job.station?.generated_title || job.manifest?.title || "Совещание без названия" }
function Badge({ stage }: { stage: JobStage }) { return stage === 'completed' ? null : <span className={`mi-badge mi-stage-${stage}`}><span />{stageNames[stage] || stage}</span> }
function isVerified(item: SourcedItem) {
  return item.review_status === 'human_confirmed' || (item.source_check === 'passed' && item.review_status === 'unreviewed')
}

export function MeetingIntelligencePage() {
  const [token, setToken] = useState(() => readSession(tokenKey))
  const [pairOpen, setPairOpen] = useState(() => !readSession(tokenKey))
  const [caps, setCaps] = useState<Capabilities>()
  const [jobs, setJobs] = useState<JobRecord[]>([])
  const [selected, setSelected] = useState(() => readSession(selectionKey))
  const [connected, setConnected] = useState(false)
  const [connectionError, setConnectionError] = useState('')
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [archiveOffset, setArchiveOffset] = useState(0)
  const archivePageSize = 50
  const [refreshKey, setRefreshKey] = useState(0)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [recordOpen, setRecordOpen] = useState(false)
  const [joinOpen, setJoinOpen] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const config = useMemo<WorkerConfig>(() => ({ token }), [token])
  const choose = useCallback((id: string) => { setSelected(id); saveSession(selectionKey, id) }, [])
  const refresh = useCallback(() => setRefreshKey(value => value + 1), [])
  const selectedJob = jobs.find(job => job.id === selected)
  const activeId = caps?.station.active_recording_id
  const activeJob = jobs.find(job => job.id === activeId)
  const missingSpeechModels = caps?.station.worker_connected && caps.selected_profiles && caps.readiness
    ? Object.values(caps.selected_profiles).some(profile => !caps.readiness?.[profile]?.ready) : false
  const diarizationAvailable = caps?.station.worker_connected ? caps.diarization : undefined

  useEffect(() => {
    document.title = "Meeting Station · Локальные протоколы совещаний"
    document.documentElement.lang = 'ru'
    // Older versions saved the Mac worker secret in localStorage. The station
    // now keeps that secret server-side and uses a separate tab-session token.
    try { localStorage.removeItem('mi.token'); localStorage.removeItem('mi.workerUrl') } catch { /* Storage may be disabled. */ }
  }, [])

  useEffect(() => {
    if (!token) return
    let disposed = false
    let pending = false
    async function poll() {
      if (pending || document.hidden) return
      pending = true
      try {
        const results = await Promise.allSettled([capabilities(config), listJobs(config, archivePageSize, archiveOffset)])
        if (disposed) return
        const rejected = results.find(result => result.status === 'rejected')
        if (rejected?.status === 'rejected') throw rejected.reason
        const station = results[0]
        const archive = results[1]
        if (station.status === 'fulfilled') setCaps(station.value)
        if (archive.status === 'fulfilled') {
          setJobs(archive.value)
          setSelected(previous => {
            const next = archive.value.some(job => job.id === previous) ? previous : archive.value[0]?.id || ''
            saveSession(selectionKey, next)
            return next
          })
        }
        setConnected(true)
        setConnectionError('')
      } catch (cause) {
        if (disposed) return
        setConnected(false)
        setConnectionError(message(cause))
        if (cause instanceof APIError && cause.status === 401) {
          saveSession(tokenKey, ''); setToken(''); setJobs([]); setCaps(undefined); setPairOpen(true)
        }
      } finally { pending = false }
    }
    void poll()
    const timer = window.setInterval(() => { void poll() }, 4000)
    const onVisible = () => { if (!document.hidden) void poll() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { disposed = true; window.clearInterval(timer); document.removeEventListener('visibilitychange', onVisible) }
  }, [token, config, archiveOffset, refreshKey])

  const acceptJob = useCallback((job: JobRecord) => {
    setJobs(previous => [job, ...previous.filter(item => item.id !== job.id)])
    setArchiveOffset(0)
    choose(job.id)
    refresh()
  }, [choose, refresh])

  async function perform(action: () => Promise<JobRecord>) {
    setActionBusy(true); setError('')
    try { acceptJob(await action()) } catch (cause) { setError(message(cause)) } finally { setActionBusy(false) }
  }
  function disconnect() {
    saveSession(tokenKey, ''); setToken(''); setConnected(false); setJobs([]); setCaps(undefined); choose(''); setArchiveOffset(0); setPairOpen(false)
  }
  const visible = jobs.filter(job => title(job).toLocaleLowerCase().includes(search.toLocaleLowerCase()))

  return <Layout><div className="mi-page">
    <div className="mi-station-strip" aria-label="Состояние системы">
      <div className="mi-station-device"><strong>Meeting Station</strong><span className={`mi-status-dot ${connected ? 'is-online' : ''}`} /><span>{connected ? "На связи" : token ? "Подключение…" : "Не подключена"}</span></div>
      <div className="mi-station-device"><strong>Вычислитель</strong><span className={`mi-status-dot ${connected && caps?.station.worker_connected ? 'is-online' : ''}`} /><span>{connected && caps?.station.worker_connected ? "На связи" : "Недоступен"}</span></div>
      <span className="mi-network-label"><ShieldCheck />Локальная сеть</span>
      <button type="button" className="mi-pair-button" onClick={() => setPairOpen(true)}>{token ? "Доступ к станции" : "Подключить станцию"}</button>
    </div>
    <header className="mi-heading">
      <div className="mi-heading-copy"><span className="mi-eyebrow">АРХИВ И ПРОТОКОЛЫ</span><h1>Совещания</h1><p>От записи — к решениям, которые можно проверить.</p></div>
      <div className="mi-heading-actions">
        <Button variant="outline" onClick={() => setRecordOpen(true)} disabled={!connected || !caps?.station.recording_available || Boolean(activeId)} title={!caps?.station.recording_available ? "Подключите и настройте микрофон станции" : undefined}><Mic />Записать</Button>
        <Button variant="outline" onClick={() => setJoinOpen(true)} disabled={!connected}>Онлайн-встреча</Button>
        <Button onClick={() => setUploadOpen(true)} disabled={!connected}><Upload />Добавить запись</Button>
      </div>
    </header>

    {connected && !caps?.station.worker_connected && <div className="mi-notice"><div><strong>Вычислитель недоступен.</strong> Записи сохранены. Обработка продолжится после восстановления связи.</div></div>}
    {connected && missingSpeechModels && <div className="mi-notice mi-warning"><AlertCircle /><div><strong>Речевая модель не установлена.</strong> Записи можно сохранить в архив. Для обработки подготовьте локальные модели и повторите запуск.</div></div>}
    {connectionError && <div className="mi-notice mi-warning" role="status"><AlertCircle /><span>{connectionError} {token ? "Соединение восстановится автоматически." : ''}</span><Button variant="ghost" size="sm" onClick={token ? refresh : () => setPairOpen(true)}>{token ? "Повторить" : "Подключить"}</Button></div>}
    {error && <div className="mi-notice mi-warning" role="alert"><AlertCircle /><span>{error}</span><button className="mi-icon-button" aria-label="Закрыть сообщение" onClick={() => setError('')}><X /></button></div>}
    {activeId && <div className="mi-recording-banner"><span className="mi-recording-dot" /><div><strong>{activeJob ? title(activeJob) : "Запись на станции"}</strong><small>Аудио сохраняется на станции.</small></div><RecordingClock started={activeJob?.created_at} /><Button variant="outline" onClick={() => void perform(() => stopRecording(config, activeId))} disabled={actionBusy || !connected}><Square />Завершить и обработать</Button></div>}
    <MeetingBrowserPanel open={joinOpen} onOpenChange={setJoinOpen} config={config} connected={connected} jobs={jobs} onCreated={acceptJob} diarizationAvailable={diarizationAvailable} />

    <div className="mi-workspace">
      <aside className="mi-archive" aria-label="Архив совещаний">
        <div className="mi-archive-heading"><h2>Все совещания <span>{jobs.length}</span></h2><button className="mi-icon-button" aria-label="Обновить архив" title="Обновить архив" onClick={refresh} disabled={!token}><RefreshCw /></button></div>
        <label className="mi-search"><Search /><input type="search" placeholder="Найти совещание…" aria-label="Поиск по названию на этой странице" value={search} onChange={event => setSearch(event.target.value)} /></label>
        <div className="mi-meeting-list">{visible.map(job => <button key={job.id} className={`mi-meeting ${job.id === selected ? 'is-selected' : ''}`} aria-pressed={job.id === selected} onClick={() => choose(job.id)}><span className="mi-meeting-copy"><strong>{title(job)}</strong><span>{date(job.created_at)}<span className="mi-list-divider">·</span>{job.source_kind === 'text' ? "Расшифровка" : "Запись"}</span><Badge stage={job.stage} /></span></button>)}
          {!visible.length && <div className="mi-list-empty"><strong>{search ? "Ничего не найдено" : "Пока нет совещаний"}</strong><p>{search ? "Измените запрос или откройте предыдущие записи." : token && !connected ? "Подключаемся к станции…" : "Загрузите файл или начните запись."}</p></div>}
        </div>
        <div aria-label="Страницы архива">{archiveOffset > 0 && <button className="mi-load-more" onClick={() => { setArchiveOffset(value => Math.max(0, value - archivePageSize)); setSearch('') }}>Более новые записи</button>}<p className="mi-list-empty">Страница {archiveOffset / archivePageSize + 1} · Поиск по этой странице.</p>{jobs.length === archivePageSize && <button className="mi-load-more" onClick={() => { setArchiveOffset(value => value + archivePageSize); setSearch('') }}>Более ранние записи</button>}</div>
      </aside>
      <section className="mi-detail" aria-label="Протокол совещания">
        {selectedJob ? <MeetingDetail key={selectedJob.id} job={selectedJob} config={config} connected={connected} onError={setError} onRetry={() => void perform(() => retryJob(config, selectedJob.id))} onCancel={() => void perform(() => cancelJob(config, selectedJob.id))} busy={actionBusy} /> : <div className="mi-welcome"><div className="mi-welcome-icon"><FileText /></div><h2>Ваш следующий протокол — здесь</h2><p>Выберите совещание в архиве или добавьте запись. Расшифровка, поручения и их источники будут собраны в одном месте.</p></div>}
      </section>
    </div>

    <PairDialog open={pairOpen} onOpenChange={setPairOpen} connected={connected} onDisconnect={disconnect} onConnect={(value, station) => { saveSession(tokenKey, value); setToken(value); setCaps(station); setConnected(true); setConnectionError(''); setPairOpen(false); refresh() }} />
    <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} config={config} maxBytes={caps?.station.max_upload_bytes} diarizationAvailable={diarizationAvailable} onCreated={acceptJob} />
    <RecordDialog open={recordOpen} onOpenChange={setRecordOpen} config={config} diarizationAvailable={diarizationAvailable} onCreated={acceptJob} />
  </div></Layout>
}

function PairDialog({ open, onOpenChange, connected, onConnect, onDisconnect }: { open: boolean; onOpenChange: (value: boolean) => void; connected: boolean; onConnect: (value: string, caps: Capabilities) => void; onDisconnect: () => void }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function connect(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { const station = await capabilities({ token: value.trim() }); onConnect(value.trim(), station); setValue('') } catch (cause) { setError(message(cause)) } finally { setBusy(false) }
  }
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent closeLabel="Закрыть" className="mi-dialog"><DialogHeader><DialogTitle>Доступ к станции</DialogTitle><DialogDescription>Введите токен, созданный при настройке локальной станции.</DialogDescription></DialogHeader><form onSubmit={event => void connect(event)} className="mi-form"><label htmlFor="mi-token">Токен станции</label><Input id="mi-token" type="password" required autoComplete="off" spellCheck={false} placeholder="Вставьте токен станции" value={value} onChange={event => setValue(event.target.value)} /><ErrorText error={error} /><Button type="submit" disabled={busy || !value.trim()}>{busy && <Loader2 className="animate-spin" />}Подключить</Button>{connected && <Button type="button" variant="ghost" onClick={onDisconnect}>Отключить этот браузер</Button>}<small>Токен хранится только в текущей сессии вкладки.</small></form></DialogContent></Dialog>
}

function UploadDialog({ open, onOpenChange, config, maxBytes, diarizationAvailable, onCreated }: { open: boolean; onOpenChange: (value: boolean) => void; config: WorkerConfig; maxBytes?: number; diarizationAvailable?: boolean; onCreated: (job: JobRecord) => void }) {
  const [meetingTitle, setMeetingTitle] = useState('')
  const [language, setLanguage] = useState('kk_ru')
  const [outputLanguage, setOutputLanguage] = useState('same')
  const [vocabulary, setVocabulary] = useState('')
  const [diarization, setDiarization] = useState(true)
  const [file, setFile] = useState<File>()
  const [transcript, setTranscript] = useState('')
  const [mode, setMode] = useState<'audio' | 'text'>('audio')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [percent, setPercent] = useState(0)
  const [dragging, setDragging] = useState(false)
  const submission = useRef('')
  const uploadController = useRef<AbortController | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  useEffect(() => () => uploadController.current?.abort(), [])
  function chooseFile(value?: File) {
    setError(''); submission.current = ''
    if (value && !/\.(mp3|wav|m4a|webm|caf|ogg|flac|mp4|mkv)$/i.test(value.name)) { setError("Выберите запись MP3, WAV, M4A, WebM, CAF, OGG, FLAC, MP4 или MKV."); return }
    if (value && maxBytes && value.size > maxBytes) { setError(`Размер записи превышает лимит станции: ${size(maxBytes)} .`); return }
    setFile(value)
    if (value && !meetingTitle.trim()) setMeetingTitle(value.name.replace(/\.[^.]+$/, '').slice(0, 200))
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('')
    if (mode === 'audio' && !file) { setError("Выберите запись для загрузки."); return }
    if (mode === 'text' && !transcript.trim()) { setError("Вставьте расшифровку для обработки."); return }
    setBusy(true); setPercent(0)
    const controller = new AbortController(); uploadController.current = controller
    try {
      if (!submission.current) submission.current = createID()
      const job = await submitMeeting(config, { id: submission.current, title: meetingTitle.trim(), languageMode: language, outputLanguage, vocabulary: mode === 'audio' ? vocabulary : '', diarization: diarization && diarizationAvailable !== false, file: mode === 'audio' ? file : undefined, transcript: mode === 'text' ? transcript : undefined }, setPercent, controller.signal)
      onCreated(job); onOpenChange(false); setFile(undefined); setTranscript(''); setMeetingTitle(''); setVocabulary(''); submission.current = ''
      if (fileInput.current) fileInput.current.value = ''
    } catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(message(cause)) } finally { setBusy(false); uploadController.current = null }
  }
  return <Dialog open={open} onOpenChange={value => { if (!busy) onOpenChange(value) }}><DialogContent closeLabel="Закрыть" className="mi-dialog" showCloseButton={!busy}><DialogHeader><DialogTitle>Добавить совещание</DialogTitle><DialogDescription>Загрузите аудио, видео или готовую расшифровку. Участники должны быть уведомлены о записи и локальной обработке с помощью ИИ.</DialogDescription></DialogHeader><form className="mi-form" onSubmit={event => void submit(event)}><fieldset disabled={busy}>
    <label htmlFor="mi-meeting-title">Название совещания</label><Input id="mi-meeting-title" required maxLength={200} placeholder="Например, планирование проекта" value={meetingTitle} onChange={event => { setMeetingTitle(event.target.value); submission.current = '' }} />
    <div className="mi-input-mode"><button type="button" className={mode === 'audio' ? 'is-active' : ''} onClick={() => { setMode('audio'); submission.current = '' }}><FileAudio />Аудио или видео</button><button type="button" className={mode === 'text' ? 'is-active' : ''} onClick={() => { setMode('text'); submission.current = '' }}><FileText />Готовая расшифровка</button></div>
    {mode === 'audio' ? <label className={`mi-dropzone ${dragging ? 'is-dragging' : ''}`} onDragOver={event => { event.preventDefault(); if (!busy) setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); if (!busy) chooseFile(event.dataTransfer.files[0]) }}><input ref={fileInput} type="file" accept=".mp3,.wav,.m4a,.webm,.caf,.ogg,.flac,.mp4,.mkv" aria-label="Выбрать запись" onChange={event => chooseFile(event.target.files?.[0])} /><Upload /><strong>{file ? file.name : "Перетащите запись сюда или выберите файл"}</strong><span>{file ? size(file.size) : "MP3, WAV, M4A, WebM, CAF, OGG, FLAC, MP4 или MKV"}</span></label> : <Textarea aria-label="Текст совещания" rows={6} placeholder="Вставьте текст разговора…" value={transcript} onChange={event => { setTranscript(event.target.value); submission.current = '' }} />}
    <div className="mi-form-columns"><label>Язык записи<select value={language} onChange={event => { setLanguage(event.target.value); submission.current = '' }}><option value="kk_ru">Казахский + русский</option><option value="kk">Казахский</option><option value="ru">Русский</option><option value="en">Английский</option><option value="auto">Определить автоматически</option></select></label><label>Язык протокола<select value={outputLanguage} onChange={event => { setOutputLanguage(event.target.value); submission.current = '' }}><option value="same">Как в записи</option><option value="kk">Казахский</option><option value="ru">Русский</option><option value="en">Английский</option></select></label></div>
    {mode === 'audio' && <label>Имена и термины (необязательно)<Input value={vocabulary} maxLength={400} placeholder="Айдана, Тимур, Самрук-Казына" onChange={event => { setVocabulary(event.target.value); submission.current = '' }} /><small>Подсказки для распознавания. Проверьте имена по записи.</small></label>}
    {mode === 'audio' && <label className="mi-checkbox"><input type="checkbox" checked={diarization && diarizationAvailable !== false} disabled={diarizationAvailable === false} onChange={event => { setDiarization(event.target.checked); submission.current = '' }} /><span>Разделить говорящих<small>{diarizationAvailable === false ? "Модели разделения говорящих пока недоступны." : "Метки голосов помогут определить участников при проверке."}</small></span></label>}
    </fieldset>
    {busy && <div className="mi-upload-progress" role="status"><div><span>{percent >= 100 ? "Сохранение на станции…" : "Загрузка на станцию…"}</span><span>{percent}%</span></div><progress value={percent} max={100} aria-label="Ход загрузки" /></div>}
    <ErrorText error={error} /><Button type="submit" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Upload />}Сохранить и обработать</Button><small>{maxBytes ? `До ${size(maxBytes)}. ` : ''}Аудио обрабатывается в вашей локальной сети.</small>
  </form></DialogContent></Dialog>
}

function RecordDialog({ open, onOpenChange, config, diarizationAvailable, onCreated }: { open: boolean; onOpenChange: (value: boolean) => void; config: WorkerConfig; diarizationAvailable?: boolean; onCreated: (job: JobRecord) => void }) {
  const [meetingTitle, setMeetingTitle] = useState('')
  const [language, setLanguage] = useState('kk_ru')
  const [diarization, setDiarization] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function record(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { onCreated(await startRecording(config, meetingTitle.trim(), language, diarization && diarizationAvailable !== false)); onOpenChange(false); setMeetingTitle('') } catch (cause) { setError(message(cause)) } finally { setBusy(false) }
  }
  return <Dialog open={open} onOpenChange={value => { if (!busy) onOpenChange(value) }}><DialogContent closeLabel="Закрыть" className="mi-dialog" showCloseButton={!busy}><DialogHeader><DialogTitle>Записать совещание</DialogTitle><DialogDescription>Используется микрофон комнатной станции. До начала уведомите участников о записи и локальной ИИ-расшифровке.</DialogDescription></DialogHeader><form className="mi-form" onSubmit={event => void record(event)}><fieldset disabled={busy}><label htmlFor="mi-record-title">Название совещания</label><Input id="mi-record-title" required maxLength={200} placeholder="Например, встреча команды" value={meetingTitle} onChange={event => setMeetingTitle(event.target.value)} /><label>Язык записи<select value={language} onChange={event => setLanguage(event.target.value)}><option value="kk_ru">Казахский + русский</option><option value="kk">Казахский</option><option value="ru">Русский</option><option value="en">Английский</option><option value="auto">Определить автоматически</option></select></label><label className="mi-checkbox"><input type="checkbox" checked={diarization && diarizationAvailable !== false} disabled={diarizationAvailable === false} onChange={event => setDiarization(event.target.checked)} /><span>Разделить говорящих<small>{diarizationAvailable === false ? "Модели разделения говорящих пока недоступны." : "Метки голосов помогут определить участников при проверке."}</small></span></label><div className="mi-record-source"><strong>Микрофон станции</strong><span>Подключён к комнатной станции</span></div></fieldset><ErrorText error={error} /><Button type="submit" disabled={busy || !meetingTitle.trim()}>{busy ? <Loader2 className="animate-spin" /> : <Mic />}Начать запись</Button></form></DialogContent></Dialog>
}

function RecordingClock({ started }: { started?: string }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [])
  return <span className="mi-recording-clock">{started ? time((now - new Date(started).getTime()) / 1000) : "Запись"}</span>
}
function ErrorText({ error }: { error: string }) { return error ? <p className="mi-form-error" role="alert"><AlertCircle />{error}</p> : null }

function MeetingDetail({ job, config, connected, onError, onRetry, onCancel, busy }: { job: JobRecord; config: WorkerConfig; connected: boolean; onError: (value: string) => void; onRetry: () => void; onCancel: () => void; busy: boolean }) {
  const [result, setResult] = useState<MeetingResult>()
  const [resultError, setResultError] = useState('')
  const [loading, setLoading] = useState(false)
  const [reload, setReload] = useState(0)
  const [tab, setTab] = useState<'overview' | 'transcript'>('overview')
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState<string[]>([])
  const [audioURL, setAudioURL] = useState('')
  const [audioLoading, setAudioLoading] = useState(false)
  const [audioError, setAudioError] = useState('')
  const [audioRetry, setAudioRetry] = useState(0)
  const [exporting, setExporting] = useState(false)
  const [format, setFormat] = useState<'json' | 'csv' | 'pdf' | 'docx' | 'ics'>('pdf')
  const [reviewOpen, setReviewOpen] = useState(false)
  const audio = useRef<HTMLAudioElement>(null)
  const segmentElements = useRef(new Map<string, HTMLDivElement>())
  const isRecording = job.stage === 'recording'

  useEffect(() => {
    if (job.stage !== 'completed') { setResult(undefined); return }
    let disposed = false
    setLoading(true); setResultError('')
    getResult(config, job.id).then(value => { if (!disposed) setResult(value) }).catch(cause => { if (!disposed) setResultError(message(cause)) }).finally(() => { if (!disposed) setLoading(false) })
    return () => { disposed = true }
  }, [config, job.id, job.stage, job.updated_at, reload])
  useEffect(() => {
    setAudioURL(''); setAudioError(''); setAudioLoading(false)
    if (!connected || job.source_kind !== 'audio' || isRecording) return
    const controller = new AbortController()
    let objectURL = ''
    setAudioLoading(true)
    loadAudio(config, job.id, controller.signal).then(blob => {
      if (controller.signal.aborted) return
      objectURL = URL.createObjectURL(blob)
      setAudioURL(objectURL)
    }).catch(cause => { if (!controller.signal.aborted) setAudioError(message(cause)) })
      .finally(() => { if (!controller.signal.aborted) setAudioLoading(false) })
    return () => { controller.abort(); if (objectURL) URL.revokeObjectURL(objectURL) }
  }, [config, connected, job.id, job.source_kind, isRecording, audioRetry])

  function seek(seconds: number | null | undefined) {
    if (seconds == null || !audio.current) return
    audio.current.currentTime = seconds
    void audio.current.play().catch(() => setAudioError("Нажмите воспроизведение, чтобы прослушать запись с этого момента."))
  }
  function jump(item: SourcedItem) {
    const ids = item.evidence.segment_ids || []
    setTab('transcript'); setQuery(''); setHighlight(ids)
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
      const first = ids.map(id => segmentElements.current.get(id)).find(Boolean)
      first?.scrollIntoView({ behavior: 'smooth', block: 'center' }); first?.focus({ preventScroll: true })
    }))
    if (item.evidence.start != null && audioURL) seek(item.evidence.start)
  }
  async function exportFile() {
    setExporting(true); onError('')
    try { await downloadExport(config, job.id, format) } catch (cause) { onError(message(cause)) } finally { setExporting(false) }
  }
  const segments = useMemo(() => (result?.transcript.segments || []).slice().sort((a, b) => (a.start ?? 0) - (b.start ?? 0)), [result])
  const speakers = useMemo(() => Array.from(new Set(segments.map(segment => segment.speaker).filter((speaker): speaker is string => Boolean(speaker)))), [segments])
  const filtered = segments.filter(segment => segment.text.toLocaleLowerCase().includes(query.toLocaleLowerCase()))
  const processing = !finished.has(job.stage) && job.stage !== 'recording'
  const verifiedTopics = result?.protocol.topics.filter(isVerified) || []
  const verifiedDecisions = result?.protocol.decisions.filter(isVerified) || []
  const verifiedActions = result?.protocol.action_items.filter(isVerified) || []
  const verifiedQuestions = result?.protocol.open_questions.filter(isVerified) || []
  const verifiedRisks = result?.protocol.risks.filter(isVerified) || []
  const noFindings = result && ![...result.protocol.topics, ...result.protocol.decisions, ...result.protocol.action_items, ...result.protocol.open_questions, ...result.protocol.risks].length
  const reviewItems = result ? [
    ...result.protocol.topics.filter(item => !isVerified(item)).map(item => ({ kind: "Тема", text: `${item.title}: ${item.text}`, item })),
    ...result.protocol.decisions.filter(item => !isVerified(item)).map(item => ({ kind: "Решение", text: item.text, item })),
    ...result.protocol.action_items.filter(item => !isVerified(item)).map(item => ({ kind: "Поручение", text: item.task, item })),
    ...result.protocol.open_questions.filter(item => !isVerified(item)).map(item => ({ kind: "Вопрос", text: item.text, item })),
    ...result.protocol.risks.filter(item => !isVerified(item)).map(item => ({ kind: "Риск", text: item.text, item })),
  ] : []
  const tabKeys = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft' || event.key === 'Home' || event.key === 'End') {
      event.preventDefault(); const next = event.key === 'Home' ? 'overview' : event.key === 'End' ? 'transcript' : tab === 'overview' ? 'transcript' : 'overview'; setTab(next); document.getElementById(`mi-tab-${next}`)?.focus()
    }
  }
  return <div>
    <header className="mi-detail-header"><div className="mi-detail-topline"><span>{date(job.created_at, true)}</span><Badge stage={job.stage} /></div><h2>{title(job)}</h2><div className="mi-detail-meta"><span>{job.source_kind === 'text' ? "Импортированная расшифровка" : "Аудио или видео"}</span>{job.station?.source_bytes ? <span>{size(job.station.source_bytes)}</span> : null}{result?.protocol.metadata.duration_seconds != null && <span>{time(result.protocol.metadata.duration_seconds)}</span>}{result?.transcript.language && <span>{result.transcript.language.toUpperCase()}</span>}</div>{result && <div className="mi-exports"><select aria-label="Формат экспорта" value={format} onChange={event => setFormat(event.target.value as typeof format)}><option value="pdf">Протокол PDF</option>{result.exports.docx && <option value="docx">Документ Word (.docx)</option>}<option value="csv">Таблица поручений CSV</option><option value="json">Данные JSON</option><option value="ics">Задачи календаря (.ics)</option></select><Button variant="outline" size="sm" disabled={exporting || !connected} onClick={() => void exportFile()}>{exporting ? <Loader2 className="animate-spin" /> : <Download />}Скачать</Button><Button size="sm" variant="outline" disabled={!connected || reviewOpen} onClick={() => setReviewOpen(true)}>Проверить и исправить</Button></div>}</header>

    {result && <div className="mi-report-stats" aria-label="Состояние протокола"><div><ClipboardList /><span>Поручения<strong>{result.protocol.action_items.length}</strong></span></div><div className={reviewItems.length ? 'needs-review' : ''}><CheckCheck /><span>Спорные факты<strong>{reviewItems.length}</strong></span></div><div><History /><span>Версия протокола<strong>{result.review_revision || 0}</strong></span></div></div>}

    {job.error_message && <div className="mi-job-error" role="status"><AlertCircle /><div><strong>{job.error_code === 'ENGINE_OFFLINE' ? "Ожидание локального вычислителя" : "Обработка требует внимания"}</strong><p>{job.error_message}</p></div>{(job.stage === 'failed' || job.stage === 'cancelled') && <Button variant="outline" size="sm" disabled={busy || !connected} onClick={onRetry}><RefreshCw />Повторить</Button>}</div>}
    {(job.stage === 'failed' || job.stage === 'cancelled') && !job.error_message && <div className="mi-job-error"><AlertCircle /><span>{job.stage === 'cancelled' ? "Обработка отменена. Исходная запись сохранена." : "Обработка завершилась ошибкой. Исходная запись сохранена."}</span><Button variant="outline" size="sm" disabled={busy || !connected} onClick={onRetry}><RefreshCw />Повторить</Button></div>}
    {processing && <div className="mi-processing"><div><Loader2 className="animate-spin" /><strong>{stageNames[job.stage]}</strong><Button variant="ghost" size="sm" disabled={busy || !connected} onClick={onCancel}>Отменить обработку</Button></div><div className="mi-processing-track" aria-label={`Этап обработки: ${stageNames[job.stage]}`}>{stages.filter(stage => stage !== 'diarizing' || job.manifest?.diarization).map(stage => <span key={stage} className={stages.indexOf(stage) <= stages.indexOf(job.stage) ? 'is-done' : ''} />)}</div><p>{job.stage === 'queued' ? "Источник сохранён. Вычислитель обрабатывает встречи по очереди." : "Обработка идёт на локальном вычислителе. Можно закрыть страницу и вернуться позже."}</p></div>}
    {job.source_kind === 'audio' && !isRecording && <div className="mi-audio"><div className="mi-audio-top"><div><strong>Исходная запись</strong><small>{job.station?.filename || "Сохранено на станции"}</small></div>{audioLoading && <small role="status">Загрузка записи…</small>}</div>{audioURL && <audio ref={audio} src={audioURL} controls preload="metadata" aria-label="Запись совещания" onError={() => setAudioError("Браузер не воспроизводит этот формат. Исходная запись сохранена.")} />}<ErrorText error={audioError} />{audioError && <Button variant="outline" size="sm" disabled={!connected || audioLoading} onClick={() => setAudioRetry(value => value + 1)}>Загрузить запись повторно</Button>}</div>}

    <div className="mi-tabs" role="tablist" aria-label="Материалы совещания"><button id="mi-tab-overview" role="tab" aria-selected={tab === 'overview'} aria-controls="mi-overview" tabIndex={tab === 'overview' ? 0 : -1} onKeyDown={tabKeys} onClick={() => setTab('overview')}>Протокол</button><button id="mi-tab-transcript" role="tab" aria-selected={tab === 'transcript'} aria-controls="mi-transcript" tabIndex={tab === 'transcript' ? 0 : -1} onKeyDown={tabKeys} onClick={() => setTab('transcript')}>Расшифровка <span>{segments.length}</span></button></div>
    {loading && <div className="mi-detail-empty" role="status"><Loader2 className="animate-spin" /><strong>Открываем протокол…</strong></div>}
    {resultError && <div className="mi-detail-empty" role="alert"><AlertCircle /><p>{resultError}</p><Button variant="outline" onClick={() => setReload(value => value + 1)}>Попробовать снова</Button></div>}
    {!loading && !result && !resultError && <div className="mi-detail-empty"><strong>{job.stage === 'recording' ? "Идёт запись" : "Протокол готовится"}</strong><p>{job.stage === 'recording' ? "Завершите запись, чтобы подготовить расшифровку и протокол." : job.stage === 'failed' || job.stage === 'cancelled' ? "Повторите обработку для подготовки расшифровки и протокола." : "Расшифровка и протокол появятся после обработки."}</p></div>}
    {result && <>
      {reviewOpen && <MeetingReviewPanel result={result} config={config} onSaved={value => { setResult(value); setReviewOpen(false) }} onClose={() => setReviewOpen(false)} onReload={() => { setReviewOpen(false); setReload(value => value + 1) }} />}
      {Boolean(result.review_history?.length) && <details className="mi-review-history"><summary>История проверки · версия {result.review_revision}</summary>{result.review_history?.slice().reverse().map(event => <article key={event.revision}><strong>{event.reviewer}</strong><span>{date(event.reviewed_at, true)} · {event.changes.length} изменений</span>{event.note && <p>{event.note}</p>}</article>)}</details>}
      {(noFindings || Boolean(result.transcript.warnings?.length)) && <div className="mi-quality-notice" role="status"><strong>Протокол требует проверки</strong>{noFindings && <p>Поручения и решения не извлечены. Проверьте расшифровку и исходную запись перед использованием протокола.</p>}{result.transcript.warnings?.map(warning => <p key={warning}>{warning}</p>)}</div>}
      <div id="mi-overview" role="tabpanel" aria-labelledby="mi-tab-overview" hidden={tab !== 'overview'} className="mi-report">
        <ReportSection title="Поручения" count={verifiedActions.length}>{verifiedActions.length ? <div className="mi-action-table-wrap" role="region" aria-label="Таблица поручений" tabIndex={0}><table className="mi-action-table"><thead><tr><th scope="col">Ответственный</th><th scope="col">Поручение</th><th scope="col">Срок</th><th scope="col">Приоритет</th></tr></thead><tbody>{verifiedActions.map(item => <tr key={item.id}><td><span className="mi-owner">{item.assignee || "Не назначен"}</span></td><td><p>{item.task}</p><EvidenceView item={item} onJump={jump} /></td><td>{item.deadline_date && <strong className="mi-due-date">{item.deadline_date}</strong>}{item.deadline_text || (!item.deadline_date && "Не указан")}</td><td><span className={`mi-table-priority mi-priority-${item.priority}`}>{({ low: 'Низкий', medium: 'Средний', high: 'Высокий', urgent: 'Срочный', not_specified: 'Не указан' })[item.priority]}</span></td></tr>)}</tbody></table></div> : <p className="mi-muted">Подтверждённых поручений пока нет.</p>}</ReportSection>
        <ReportSection title="Краткое содержание"><div className="mi-summary">{result.protocol.executive_summary.length ? result.protocol.executive_summary.map((line, index) => {
          const reference = result.protocol.executive_summary_sources?.[index]
          const source: SourcedItem | undefined = reference && ([...result.protocol.decisions, ...result.protocol.action_items, ...result.protocol.topics, ...result.protocol.open_questions, ...result.protocol.risks].find(item => item.id === reference.item_id) || { id: reference.item_id, evidence: reference.evidence, source_check: 'passed', review_status: 'unreviewed', audio_warning: reference.audio_warning })
          return <div className="mi-summary-item" key={index}><p>{line}</p>{source ? <EvidenceView item={source} onJump={jump} /> : <small className="mi-muted">Сверьте содержание с расшифровкой и записью.</small>}</div>
        }) : <p className="mi-muted">Проверенного содержания пока нет. Проверьте решения и расшифровку.</p>}</div></ReportSection>
        <ReportSection title="Темы встречи" count={verifiedTopics.length}><div className="mi-topic-list">{verifiedTopics.length ? verifiedTopics.map(topic => <article className="mi-topic-card" key={topic.id}><h4>{topic.title}</h4><p>{topic.text}</p><EvidenceView item={topic} onJump={jump} /></article>) : <p className="mi-muted">Подтверждённых тем пока нет.</p>}</div></ReportSection>
        <ReportSection title="Решения" count={verifiedDecisions.length}><ItemList items={verifiedDecisions} onJump={jump} empty="Подтверждённых решений пока нет." /></ReportSection>
        <div className="mi-report-columns"><ReportSection title="Открытые вопросы" count={verifiedQuestions.length}><ItemList items={verifiedQuestions} onJump={jump} empty="Подтверждённых открытых вопросов нет." /></ReportSection><ReportSection title="Риски" count={verifiedRisks.length}><ItemList items={verifiedRisks} onJump={jump} empty="Подтверждённых рисков нет." /></ReportSection></div>
        {reviewItems.length > 0 && <ReportSection title="Нужна проверка" count={reviewItems.length}><div className="mi-items">{reviewItems.map(({ kind, text, item }) => <article className="mi-report-item" key={item.id}><small className="mi-review-kind">{kind}</small><p>{text}</p><EvidenceView item={item} onJump={jump} /></article>)}</div></ReportSection>}
        <p className="mi-report-footnote">Сформировано локально. Перед отправкой проверьте имена, сроки и источники. Сомнительные факты остаются в разделе «Нужна проверка».</p>
      </div>
      <div id="mi-transcript" role="tabpanel" aria-labelledby="mi-tab-transcript" hidden={tab !== 'transcript'} className="mi-transcript"><label className="mi-search"><Search /><input aria-label="Поиск по расшифровке" type="search" placeholder="Найти фразу в расшифровке…" value={query} onChange={event => setQuery(event.target.value)} /></label>{segments.length ? <><div className="mi-transcript-rows">{filtered.map(segment => <div key={segment.id} ref={element => { if (element) segmentElements.current.set(segment.id, element); else segmentElements.current.delete(segment.id) }} tabIndex={-1} className={`mi-segment ${highlight.includes(segment.id) ? 'is-highlighted' : ''}`}><div className="mi-segment-meta"><span className={`mi-speaker mi-speaker-${segment.speaker ? speakers.indexOf(segment.speaker) % 4 : 0}`}>{segment.speaker_name || (segment.speaker ? `Участник ${speakers.indexOf(segment.speaker) + 1}` : "Говорящий не определён")}</span>{segment.start != null && <button className="mi-timestamp" title={audioURL ? "Воспроизвести с этого момента" : "Запись загружается"} disabled={!audioURL} onClick={() => seek(segment.start)}>{time(segment.start)}{segment.end != null ? ` – ${time(segment.end)}` : ''}</button>}</div><p dir="auto">{segment.tokens?.length && segment.tokens.map(token => token.text).join('').trim() === segment.text.trim() ? segment.tokens.map((token, index) => token.probability < 0.6 && /[\p{L}\p{N}]/u.test(token.text) ? <mark key={index} className="mi-uncertain-word" title="Низкая уверенность распознавания — проверьте аудио">{token.text}</mark> : token.text) : segment.text}</p>{segment.needs_review && <small className="mi-muted">Проверьте аудио</small>}</div>)}</div>{!filtered.length && <p className="mi-muted mi-no-matches">Подходящих реплик не найдено.</p>}</> : <p className="mi-raw-transcript" dir="auto">{result.transcript.raw_text || "Речь в записи не обнаружена."}</p>}<p className="mi-report-footnote">Выделены фрагменты с низкой уверенностью распознавания. Ошибки возможны и в остальном тексте. Метки различают голоса; имена подтверждает человек.</p></div>
    </>}
  </div>
}

function ReportSection({ title: heading, count, children }: { title: string; count?: number; children: ReactNode }) {
  return <section className="mi-report-section"><h3>{heading}{count !== undefined && <span>{count}</span>}</h3>{children}</section>
}
function ItemList({ items, onJump, empty }: { items: ProtocolItem[]; onJump: (item: SourcedItem) => void; empty: string }) {
  return <div className="mi-items">{items.length ? items.map(item => <article className="mi-report-item" key={item.id}><p>{item.text}</p><EvidenceView item={item} onJump={onJump} /></article>) : <p className="mi-muted">{empty}</p>}</div>
}
function EvidenceView({ item, onJump }: { item: SourcedItem; onJump: (item: SourcedItem) => void }) {
  const hasSource = Boolean(item.evidence.segment_ids?.length)
  const reviewRequired = item.review_status === 'needs_review' || item.review_status === 'rejected'
  return <div className={`mi-evidence ${(item.source_check === 'passed' || item.review_status === 'human_confirmed') && !reviewRequired ? 'is-checked' : 'needs-review'}`}><div><i aria-hidden="true" /><span>{item.review_status === 'human_confirmed' ? "Проверено человеком" : item.source_check === 'passed' ? "Соответствует расшифровке" : "Проверьте источник"}</span>{item.audio_warning && <span className="mi-review-label">Прослушайте цитату</span>}{reviewRequired && <span className="mi-review-label">{item.review_status === 'rejected' ? "Отклонено при проверке" : "Нужна проверка"}</span>}{item.review_status === 'human_confirmed' && <span className="mi-review-label is-confirmed">Подтверждено</span>}{hasSource && <button onClick={() => onJump(item)}>{item.evidence.start != null ? time(item.evidence.start) : "Открыть реплику"}</button>}</div>{item.evidence.quote && <blockquote dir="auto">“{item.evidence.quote}”</blockquote>}</div>
}
