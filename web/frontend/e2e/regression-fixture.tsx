/* eslint-disable react-refresh/only-export-components -- Deliberately isolated browser test entry point. */
// Isolated browser fixture for real components. Included only in the Vite dev
// test server, never the production entry point. All API/model data is synthetic.
import { StrictMode, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider, useTheme } from '../src/contexts/ThemeContext'
import { ToastProvider } from '../src/components/ui/toast'
import { TooltipProvider } from '../src/components/ui/tooltip'
import { ChatEventsProvider } from '../src/contexts/ChatEventsContext'
import { GlobalUploadProvider, useGlobalUpload } from '../src/contexts/GlobalUploadContext'
import { useAuthStore } from '../src/features/auth/store/authStore'
import { AudioRecorder } from '../src/components/AudioRecorder'
import { SystemAudioRecorder } from '../src/components/SystemAudioRecorder'
import { SummaryDialog } from '../src/features/transcription/components/audio-detail/SummaryDialog'
import { useSummarizer } from '../src/features/transcription/hooks/useTranscriptionSummary'
import { ChatInterface } from '../src/components/ChatInterface'
import { TranscriptView } from '../src/components/transcript/TranscriptView'
import { TranscriptSection } from '../src/features/transcription/components/audio-detail/TranscriptSection'
import { QuickTranscriptionDialog } from '../src/features/transcription/components/QuickTranscriptionDialog'
import { AudioVisualizer } from '../src/components/audio/AudioVisualizer'
import { MeetingIntelligencePage } from '../src/features/meeting-intelligence/MeetingIntelligencePage'
import { CLIAuthConfirmation } from '../src/features/auth/components/CLIAuthConfirmation'
import { Settings } from '../src/features/settings/pages/SettingsPage'
import { AudioFilesTable } from '../src/features/transcription/components/AudioFilesTable'
import { TranscriptionConfigDialog } from '../src/components/transcription/TranscriptionConfigDialog'
import '../src/index.css'

const scenario = new URLSearchParams(location.search).get('case') || 'storage'
function VisualizerOwner() {
  const audioRef = useRef<HTMLAudioElement>(null)
  return <><AudioVisualizer audioRef={audioRef} isPlaying={false} /><audio ref={audioRef} /></>
}
function Fixture() {
  const { theme, toggleTheme } = useTheme()
  const [open, setOpen] = useState(true)
  const [seek, setSeek] = useState<number>()
  const [notesOpen, setNotesOpen] = useState(false)
  const { handleRecordingComplete } = useGlobalUpload()
  const summary = useSummarizer('recording')
  const transcript = { text: 'Айгерім жібереді.', language: 'kk', segments: [{ start: 12, end: 15, text: 'Айгерім жібереді.', speaker: 'SPEAKER_0' }], word_segments: [{ start: 12, end: 13, word: 'Айгерім', score: 1, speaker: 'SPEAKER_0' }, { start: 13, end: 15, word: 'жібереді.', score: 1, speaker: 'SPEAKER_0' }] }
  const close = () => setOpen(false)
  if (scenario === 'microphone' || scenario === 'system') return <>{scenario === 'microphone' ? <AudioRecorder isOpen={open} onClose={close} onRecordingComplete={handleRecordingComplete} /> : <SystemAudioRecorder isOpen={open} onClose={close} onRecordingComplete={handleRecordingComplete} />}<button onClick={close}>Unmount recorder</button></>
  if (scenario === 'summary') return <SummaryDialog audioId="recording" isOpen={open} onClose={setOpen} llmReady />
  if (scenario === 'summary-request') return <><button onClick={() => void summary.generateSummary('template', 'local', 'Summarize', 'Synthetic text')}>Generate</button><output data-testid="summary">{summary.streamContent}</output><p role="alert">{summary.error}</p></>
  if (scenario === 'chat') return <ChatInterface transcriptionId="recording" activeSessionId="session" />
  if (scenario === 'segments') return <><TranscriptView transcript={{ ...transcript, word_segments: undefined }} mode="expanded" currentTime={0} currentWordIndex={null} isPlaying={false} notes={[]} highlightedWordRef={{ current: null }} speakerMappings={{}} autoScrollEnabled={false} onSeek={setSeek} /><output>{seek}</output></>
  if (scenario === 'notes') return <TranscriptSection audioId="recording" transcript={transcript} currentTime={0} currentWordIndex={null} isPlaying={false} onSeek={setSeek} speakerMappings={{}} transcriptMode="compact" autoScrollEnabled={false} notesOpen={notesOpen} setNotesOpen={setNotesOpen} speakerRenameOpen={false} setSpeakerRenameOpen={() => {}} downloadDialogOpen={false} setDownloadDialogOpen={() => {}} downloadFormat="txt" />
  if (scenario === 'quick') return <QuickTranscriptionDialog isOpen={open} onClose={close} />
  if (scenario === 'visualizer') return <><button onClick={() => setOpen(value => !value)}>Toggle visualizer</button>{open && <VisualizerOwner />}</>
  if (scenario === 'archive') return <MeetingIntelligencePage />
  if (scenario === 'cli-auth') return <CLIAuthConfirmation />
  if (scenario === 'settings') return <Settings />
  if (scenario === 'table') return <AudioFilesTable />
  if (scenario === 'profile') return <TranscriptionConfigDialog open={open} onOpenChange={setOpen} isMultiTrack={new URLSearchParams(location.search).get('multi') === 'true'} onStartTranscription={params => { document.querySelector('output')!.textContent = JSON.stringify(params) }} />
  return <><h1>Storage-independent application</h1><button onClick={toggleTheme}>Theme: {theme}</button><button onClick={() => useAuthStore.getState().logout()}>Logout</button></>
}
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
createRoot(document.getElementById('root')!).render(<StrictMode><QueryClientProvider client={client}><BrowserRouter><ThemeProvider><TooltipProvider><ToastProvider><ChatEventsProvider><GlobalUploadProvider><Fixture /><output data-testid="fixture-output" /></GlobalUploadProvider></ChatEventsProvider></ToastProvider></TooltipProvider></ThemeProvider></BrowserRouter></QueryClientProvider></StrictMode>)
