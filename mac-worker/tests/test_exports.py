import csv
import json
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import pytest

from meeting_worker.exports import export_csv, export_docx, export_ics, export_json, export_pdf
from meeting_worker.exports import _safe_csv
from meeting_worker.schemas import (
    ActionItem, Evidence, MeetingMetadata, MeetingProtocol, Transcript, TranscriptSegment,
)


def fixture_data():
    transcript = Transcript(
        language="kk", model="fixture", raw_text="Айбек есепті жұмаға дайындайды.",
        segments=[TranscriptSegment(id="seg_00001", text="Айбек есепті жұмаға дайындайды.")],
    )
    protocol = MeetingProtocol(
        metadata=MeetingMetadata(title="Қазақша кездесу"),
        executive_summary=["Есепті дайындау келісілді."],
        action_items=[ActionItem(
            id="action_01", task="=HYPERLINK(\"bad\")", assignee="Айбек",
            deadline_text="жұма", evidence=Evidence(segment_ids=["seg_00001"]),
        )],
    )
    return protocol, transcript


def test_exports_are_unicode_and_safe(tmp_path):
    protocol, transcript = fixture_data()
    json_path, csv_path, pdf_path = tmp_path / "m.json", tmp_path / "a.csv", tmp_path / "m.pdf"
    export_json(json_path, protocol, transcript)
    export_csv(csv_path, protocol)
    export_pdf(pdf_path, protocol)

    assert json.loads(json_path.read_text(encoding="utf-8"))["protocol"]["metadata"]["title"] == "Қазақша кездесу"
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[1][1].startswith("'=")
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_pdf_contains_full_protocol_and_evidence_for_every_section(tmp_path):
    from pypdf import PdfReader
    from meeting_worker.protocol import derive_summary
    from meeting_worker.schemas import JobManifest, ProtocolItem, Topic

    def evidence(index, quote):
        return Evidence(segment_ids=[f'source_{index}'], quote=quote, start=index * 10, end=index * 10 + 3)

    protocol = MeetingProtocol(metadata=MeetingMetadata(title='Complete protocol', meeting_date='2026-09-11', timezone='Asia/Almaty'),
        decisions=[ProtocolItem(id='decision_001', text='Approve the pilot.', source_check='passed',
                                evidence=evidence(1, 'We agree to approve the pilot.'))],
        topics=[Topic(id='topic_001', title='Қаржы жоспары', text='Budget allocation was discussed.', source_check='passed',
                      evidence=evidence(2, 'The budget allocation is our next topic.'))],
        open_questions=[ProtocolItem(id='question_001', text='Which adapter should we use?', source_check='passed',
                                     evidence=evidence(3, 'We have not chosen an adapter.'))],
        action_items=[ActionItem(id='action_001', task='Send the pilot report', assignee='Dana', deadline_date='2026-09-14',
                                 source_check='passed', evidence=evidence(4, 'Dana will send the pilot report on 2026-09-14.'))],
        risks=[ProtocolItem(id='risk_001', text='Adapter throughput remains uncertain.', source_check='failed', review_status='needs_review',
                            evidence=evidence(5, 'We have not measured adapter throughput.'))])
    derive_summary(protocol, JobManifest(meeting_id='complete', output_language='en'))
    path = tmp_path / 'complete.pdf'
    export_pdf(path, protocol)
    reader = PdfReader(path)
    text = ' '.join('\n'.join(page.extract_text() for page in reader.pages).split())
    for heading in ('Executive summary', 'Decisions', 'Topics and key points', 'Open questions', 'Risks', 'Action items', 'Evidence references'):
        assert heading in text
    assert 'Қаржы жоспары' in text and 'Budget allocation was discussed.' in text
    assert 'Meeting date: 2026-09-11' in text and 'Timezone: Asia/Almaty' in text
    assert '2026-09-14' in text and '[Needs review] Adapter throughput remains uncertain.' in text
    for group in (protocol.decisions, protocol.topics, protocol.open_questions, protocol.action_items, protocol.risks):
        for item in group:
            assert item.id in text
            assert item.evidence.segment_ids[0] in text
            assert item.evidence.quote in text
    assert '[10.00–13.00s]' in text
    for index in range(1, len(protocol.executive_summary_sources) + 1):
        assert f'Summary {index}' in text


def test_ics_contains_only_source_checked_actions_and_explicit_dates(tmp_path):
    protocol = MeetingProtocol(metadata=MeetingMetadata(title='Launch, plan'), action_items=[
        ActionItem(id='a1', task='Send report; notify team', assignee='Айбек', deadline_text='2026-09-14',
                   deadline_date='2026-09-14', priority='high', source_check='passed',
                   evidence=Evidence(segment_ids=['s1'], quote='Айбек sends the report.')),
        ActionItem(id='a2', task='Arrange handover', deadline_text='next week', source_check='passed'),
        ActionItem(id='a3', task='Invented task', source_check='failed', review_status='needs_review'),
    ])
    path = tmp_path / 'actions.ics'
    export_ics(path, protocol)
    content = path.read_bytes()
    text = content.decode('utf-8')
    assert content.endswith(b'\r\n') and '\n' not in text.replace('\r\n', '')
    # RFC 5545 continuation folds are transport formatting, not field content.
    text = text.replace('\r\n ', '')
    assert text.count('BEGIN:VTODO') == 2
    assert 'SUMMARY:Send report\\; notify team' in text
    assert 'Owner: Айбек' in text and 'DUE;VALUE=DATE:20260914' in text
    assert 'PRIORITY:3' in text and 'Spoken deadline: next week' in text
    assert 'Invented task' not in text


def test_empty_protocol_pdf_explains_failure_and_preserves_timestamped_transcript(tmp_path):
    from pypdf import PdfReader
    protocol = MeetingProtocol(metadata=MeetingMetadata(title='Unclear recording'))
    transcript = Transcript(model='fixture', language='kk', raw_text='Есеп дайын.',
        warnings=['Repeated recognition output detected.'],
        segments=[TranscriptSegment(id='s1', text='Есеп дайын.', start=12.5, end=15, needs_review=True)])
    path = tmp_path / 'report.pdf'
    export_pdf(path, protocol, transcript=transcript)
    pages = [page.extract_text() for page in PdfReader(path).pages]
    assert len(pages) == 1
    assert 'Report needs review' in pages[0]
    assert 'No structured meeting findings were extracted.' in pages[0]
    assert 'Repeated recognition output detected.' in pages[0]
    assert 'Executive summary' not in pages[0]
    assert 'Transcript' in pages[0]
    assert '[12.50–15.00s]' in pages[0]
    assert '[Check audio] Есеп дайын.' in pages[0]


def test_no_speech_pdf_is_explicit_instead_of_exporting_empty_headings(tmp_path):
    from pypdf import PdfReader
    path = tmp_path / 'report.pdf'
    export_pdf(path, MeetingProtocol(metadata=MeetingMetadata()), transcript=Transcript(model='fixture', raw_text='', segments=[]))
    text = '\n'.join(page.extract_text() for page in PdfReader(path).pages)
    assert 'No speech was recognized.' in text
    assert 'No structured meeting findings were extracted.' in text


@pytest.mark.parametrize(('language', 'heading'), [('ru', 'Краткий обзор'), ('kk', 'Қысқаша шолу')])
def test_report_language_localizes_pdf_with_summary_evidence(tmp_path, language, heading):
    from pypdf import PdfReader
    from meeting_worker.schemas import SummarySource
    protocol, transcript = fixture_data()
    protocol.metadata.report_language = language
    protocol.executive_summary_sources = [SummarySource(item_id='summary_001',
        evidence=Evidence(segment_ids=['seg_00001'], quote=transcript.raw_text), audio_warning=True)]
    path = tmp_path / 'localized.pdf'
    export_pdf(path, protocol, transcript=transcript)
    text = '\n'.join(page.extract_text() for page in PdfReader(path).pages)
    assert heading in text
    assert 'Executive summary' not in text
    assert 'seg_00001' in text and transcript.raw_text in text
    assert '\u0000' not in text


WORD_NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def read_docx(path):
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        document = ET.fromstring(archive.read('word/document.xml'))
        # Every generated part must be well-formed XML; external relationships
        # must not appear even when a transcript contains URLs or XML markup.
        for name in archive.namelist():
            root = ET.fromstring(archive.read(name))
            if name.endswith('.rels'):
                assert all(link.get('TargetMode') != 'External' for link in root)
    text = '\n'.join(node.text or '' for node in document.findall('.//w:t', WORD_NS))
    return document, text


def test_docx_contains_full_protocol_action_table_and_timestamped_evidence(tmp_path):
    from meeting_worker.schemas import ProtocolItem, SummarySource, Topic

    evidence = Evidence(segment_ids=['source_1'], quote='Айбек: отчёт <готов> & проверен.',
                        speaker='Айбек', start=1.5, end=4)
    protocol = MeetingProtocol(
        metadata=MeetingMetadata(title='Совещание — Қаржы', meeting_date='2026-09-23', timezone='Asia/Almaty'),
        executive_summary=['Отчёт подготовит Айбек.'],
        executive_summary_sources=[SummarySource(item_id='a1', evidence=evidence, audio_warning=True)],
        decisions=[ProtocolItem(id='d1', text='Approve the report.', evidence=evidence, source_check='passed')],
        topics=[Topic(id='t1', title='Қаржы', text='Budget allocation.', evidence=evidence, source_check='passed')],
        open_questions=[ProtocolItem(id='q1', text='Who approves?', evidence=evidence)],
        risks=[ProtocolItem(id='r1', text='Late delivery.', evidence=evidence, source_check='failed', review_status='needs_review')],
        action_items=[ActionItem(id='a1', task='Подготовить отчёт', assignee='Айбек', deadline_text='жұма',
                                 deadline_date='2026-09-25', priority='high', evidence=evidence,
                                 source_check='passed', review_status='human_confirmed')])
    transcript = Transcript(model='synthetic-fixture', raw_text=evidence.quote, warnings=['Uncertain speech.'],
        segments=[TranscriptSegment(id='source_1', text=evidence.quote, speaker='Айбек', start=1.5, end=4, needs_review=True)])
    path = tmp_path / 'complete.docx'
    export_docx(path, protocol, transcript=transcript)
    document, text = read_docx(path)
    for heading in ('Executive summary', 'Decisions', 'Topics and key points', 'Open questions',
                    'Risks', 'Action items', 'Evidence references', 'Transcript'):
        assert heading in text
    assert 'Совещание — Қаржы' in text
    assert 'Meeting date: 2026-09-23' in text and 'Timezone: Asia/Almaty' in text
    assert 'Summary 1 → a1: source_1' in text
    assert 'Some cited passages have uncertain recognition.' in text
    for group in (protocol.decisions, protocol.topics, protocol.open_questions, protocol.risks, protocol.action_items):
        for item in group:
            assert item.id + ': source_1' in text
            assert getattr(item, 'text', getattr(item, 'task', '')) in text
    assert evidence.quote in text and '[1.50–4.00s]' in text
    assert '[Check audio]' in text and 'Uncertain speech.' in text
    assert 'Human confirmed' in text and 'Not supported by transcript · Needs review' in text
    rows = document.findall('.//w:tbl/w:tr', WORD_NS)
    assert len(rows) == 2 and len(rows[1].findall('w:tc', WORD_NS)) == 4
    action_text = ' '.join(node.text or '' for node in rows[1].findall('.//w:t', WORD_NS))
    for value in ('Айбек', 'Подготовить отчёт', 'жұма', '2026-09-25', 'high'):
        assert value in action_text
    assert rows[0].find('w:trPr/w:tblHeader', WORD_NS) is not None


def test_docx_package_is_self_contained_and_escapes_untrusted_text(tmp_path):
    text = '  Ә ғ қ ң ө ұ ү һ і <w:hyperlink> & "quotes"\tTab\nNext\x00\ud800\ufffe'
    protocol = MeetingProtocol(metadata=MeetingMetadata(title=text),
                               executive_summary=['https://example.invalid/never-fetch'])
    path = tmp_path / 'escaped.docx'
    export_docx(path, protocol)
    document, rendered = read_docx(path)
    assert 'Ә ғ қ ң ө ұ ү һ і <w:hyperlink> & "quotes"' in rendered
    assert 'Next\ufffd\ufffd\ufffd' in rendered
    assert document.find('.//w:hyperlink', WORD_NS) is None
    assert document.find('.//w:tab', WORD_NS) is not None
    assert document.find('.//w:br', WORD_NS) is not None
    assert document.find('.//w:t', WORD_NS).get('{http://www.w3.org/XML/1998/namespace}space') == 'preserve'
    with ZipFile(path) as archive:
        root_links = ET.fromstring(archive.read('_rels/.rels'))
        main_link = next(link for link in root_links if link.get('Type').endswith('/officeDocument'))
        assert main_link.get('Target') == 'word/document.xml'
        document_links = ET.fromstring(archive.read('word/_rels/document.xml.rels'))
        assert all('word/' + link.get('Target') in archive.namelist() for link in document_links)
        types = ET.fromstring(archive.read('[Content_Types].xml'))
        overrides = {node.get('PartName'): node.get('ContentType') for node in types if node.get('PartName')}
        assert overrides['/word/document.xml'].endswith('wordprocessingml.document.main+xml')
        assert '/word/styles.xml' in overrides
        assert not any('macro' in name.lower() or 'vba' in name.lower() for name in archive.namelist())


def test_docx_preserves_rejected_uncertain_and_unknown_action_statuses(tmp_path):
    protocol = MeetingProtocol(metadata=MeetingMetadata(), action_items=[
        ActionItem(id='rejected', task='Rejected obligation', source_check='passed', review_status='rejected', audio_warning=True),
        ActionItem(id='uncertain', task='Uncertain obligation', source_check='failed', review_status='needs_review'),
        ActionItem(id='unchecked', task='Unchecked obligation'),
    ])
    path = tmp_path / 'review.docx'
    export_docx(path, protocol)
    document, text = read_docx(path)
    assert '[Rejected] Rejected obligation' in text
    assert 'Matches transcript · Rejected · Check audio' in text
    assert '[Needs review] Uncertain obligation' in text
    assert 'Not supported by transcript · Needs review' in text
    assert 'Source not checked · Not reviewed by a person' in text
    rows = document.findall('.//w:tbl/w:tr', WORD_NS)
    assert len(rows) == 4
    for row in rows[1:]:
        cells = row.findall('w:tc', WORD_NS)
        assert cells[0].find('.//w:t', WORD_NS).text == '—'
        assert cells[2].find('.//w:t', WORD_NS).text == '—'


def test_docx_displays_mapped_names_without_losing_voice_ids_or_human_review(tmp_path):
    evidence = Evidence(segment_ids=['s1'], speaker='SPEAKER_00', quote='Я подготовлю отчёт.').model_copy(
        update={'speaker_name': 'Айбек'})
    segment = TranscriptSegment(id='s1', text=evidence.quote, speaker='SPEAKER_00').model_copy(
        update={'speaker_name': 'Айбек'})
    protocol = MeetingProtocol(metadata=MeetingMetadata(), action_items=[
        ActionItem(id='a1', task='Corrected obligation', assignee='Айбек', evidence=evidence,
                   source_check='unavailable', review_status='human_confirmed')])
    path = tmp_path / 'human-review.docx'
    export_docx(path, protocol, transcript=Transcript(model='fixture', raw_text=evidence.quote, segments=[segment]))
    _, text = read_docx(path)
    assert text.count('Айбек (SPEAKER_00)') == 2
    assert 'Source not checked · Human confirmed' in text
    assert '[Needs review] Corrected obligation' not in text


@pytest.mark.parametrize(('language', 'heading', 'status'), [
    ('ru', 'Краткий обзор', 'Не проверено человеком'), ('kk', 'Қысқаша шолу', 'Адам тексермеген')])
def test_docx_localizes_report_headings_and_review_status(tmp_path, language, heading, status):
    protocol, transcript = fixture_data()
    protocol.metadata.report_language = language
    path = tmp_path / 'localized.docx'
    export_docx(path, protocol, transcript=transcript)
    _, text = read_docx(path)
    assert heading in text and status in text
    assert 'Executive summary' not in text
    assert 'Қазақша кездесу' in text and transcript.raw_text in text


@pytest.mark.parametrize('raw_text', ['', 'Есеп дайын.'])
def test_docx_empty_protocol_is_explicit_and_preserves_unsegmented_transcript(tmp_path, raw_text):
    path = tmp_path / 'empty.docx'
    export_docx(path, MeetingProtocol(metadata=MeetingMetadata()),
                transcript=Transcript(model='fixture', raw_text=raw_text, segments=[]))
    document, text = read_docx(path)
    assert 'Report needs review' in text and 'No structured meeting findings were extracted.' in text
    assert 'Transcript' in text
    assert 'Executive summary' not in text
    assert document.find('.//w:pageBreakBefore', WORD_NS) is None
    assert (raw_text or 'No speech was recognized.') in text
def test_calendar_identity_is_stable_per_job_but_distinct_between_meetings(tmp_path):
    from uuid import uuid4
    protocol = MeetingProtocol(metadata=MeetingMetadata(meeting_id=str(uuid4()), title="Meeting"),
        action_items=[ActionItem(id="action_001", task="First task", source_check="passed")])
    path = tmp_path / "task.ics"
    def uid():
        export_ics(path, protocol)
        return next(line for line in path.read_text().splitlines() if line.startswith("UID:"))
    initial = uid()
    protocol.action_items[0].task = "Corrected task"
    assert uid() == initial
    protocol.metadata.meeting_id = str(uuid4())
    assert uid() != initial
def test_csv_neutralizes_formulas_with_leading_whitespace():
    for value in ("=1+1", " \t=1+1", "\n@SUM(A1)", "\r+2"):
        assert _safe_csv(value) == "'" + value
    assert _safe_csv("Қазақша / русский") == "Қазақша / русский"
