from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .schemas import JobResult, MeetingProtocol, Transcript
from .report_language import translator


def _safe_csv(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) else text


def export_json(path: Path, protocol: MeetingProtocol, transcript: Transcript) -> None:
    path.write_text(
        json.dumps(
            {"protocol": protocol.model_dump(mode="json"), "transcript": transcript.model_dump(mode="json")},
            ensure_ascii=False, indent=2,
        ), encoding="utf-8",
    )


def export_csv(path: Path, protocol: MeetingProtocol) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "assignee", "task", "deadline", "deadline_text", "priority",
            "speaker", "start", "end", "quote", "source_check", "review_status", "audio_warning", "speaker_name",
        ])
        for item in protocol.action_items:
            writer.writerow([_safe_csv(value) for value in (
                item.assignee, item.task, item.deadline_date, item.deadline_text,
                item.priority, item.evidence.speaker, item.evidence.start,
                item.evidence.end, item.evidence.quote, item.source_check,
                item.review_status, item.audio_warning, item.evidence.speaker_name,
            )])


def export_ics(path: Path, protocol: MeetingProtocol) -> None:
    """Write source-checked actions as portable RFC 5545 VTODO entries."""
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Meeting Station//Action Items//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    ]
    generated = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    priorities = {"urgent": 1, "high": 3, "medium": 5, "low": 7, "not_specified": 0}
    for item in protocol.action_items:
        if item.review_status != "human_confirmed" and not (item.source_check == "passed" and item.review_status == "unreviewed"):
            continue
        if item.audio_warning and item.review_status != 'human_confirmed':
            continue
        identity = "\0".join((protocol.metadata.meeting_id or protocol.metadata.title, str(protocol.metadata.meeting_date or ""), item.id))
        uid = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24] + "@meeting-station.local"
        details = ["Owner: " + (item.assignee or "Unassigned"), "Review: " + item.review_status]
        if item.deadline_text:
            details.append("Spoken deadline: " + item.deadline_text)
        if item.evidence.quote:
            details.append("Source: “" + item.evidence.quote + "”")
        lines.extend([
            "BEGIN:VTODO", "UID:" + uid, "DTSTAMP:" + generated,
            "SUMMARY:" + _ics_escape(item.task),
            "DESCRIPTION:" + _ics_escape("\n".join(details)),
            "PRIORITY:" + str(priorities.get(item.priority, 0)),
            "STATUS:NEEDS-ACTION",
        ])
        if item.deadline_date:
            lines.append("DUE;VALUE=DATE:" + item.deadline_date.strftime("%Y%m%d"))
        lines.append("END:VTODO")
    lines.append("END:VCALENDAR")
    path.write_bytes(("\r\n".join(_ics_fold(line) for line in lines) + "\r\n").encode("utf-8"))


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _ics_fold(line: str) -> str:
    """Fold a content line at 75 UTF-8 octets without splitting a character."""
    chunks, current, limit = [], "", 75
    for character in line:
        if current and len((current + character).encode("utf-8")) > limit:
            chunks.append(current)
            current, limit = character, 74
        else:
            current += character
    chunks.append(current)
    return "\r\n ".join(chunks)


def export_pdf(path: Path, protocol: MeetingProtocol, font_path: str | None = None, transcript: Transcript | None = None) -> None:
    language = protocol.metadata.report_language or protocol.metadata.language
    t = translator(language)
    font_name = _pdf_font(font_path)
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font_name
    story = [Paragraph(escape(protocol.metadata.title), styles["Title"]), Spacer(1, 12)]
    if protocol.metadata.meeting_date:
        story.append(Paragraph(t("Meeting date: ") + protocol.metadata.meeting_date.isoformat(), styles["BodyText"]))
    if protocol.metadata.timezone:
        story.append(Paragraph(t("Timezone: ") + escape(protocol.metadata.timezone), styles["BodyText"]))
    findings = protocol.decisions + protocol.topics + protocol.open_questions + protocol.action_items + protocol.risks
    if not findings and not protocol.executive_summary:
        story.append(Paragraph(t("Report needs review"), styles["Heading2"]))
        story.append(Paragraph(t("No structured meeting findings were extracted. This is not a complete meeting protocol. Check the transcript and original recording before relying on this report."), styles["BodyText"]))
    if transcript and transcript.warnings:
        story.append(Paragraph(t("Transcription needs review"), styles["Heading2"]))
        story.extend(Paragraph(escape(warning), styles["BodyText"]) for warning in transcript.warnings)
    if not findings and not protocol.executive_summary:
        _append_transcript(story, styles, transcript, new_page=False, language=language)
        SimpleDocTemplate(str(path), pagesize=A4, leftMargin=36, rightMargin=36).build(story)
        return
    sections = [
        ("Executive summary", protocol.executive_summary),
        ("Decisions", [_qualified(item.text, item, t) for item in protocol.decisions]),
        ("Topics and key points", [_qualified(item.title + ": " + item.text, item, t) for item in protocol.topics]),
        ("Open questions", [_qualified(item.text, item, t) for item in protocol.open_questions]),
        ("Risks", [_qualified(item.text, item, t) for item in protocol.risks]),
    ]
    for title, lines in sections:
        story.append(Paragraph(t(title), styles["Heading2"]))
        if lines:
            story.extend(Paragraph(f"• {escape(line)}", styles["BodyText"]) for line in lines)
        else:
            story.append(Paragraph(t("No source-checked summary is available." if title == "Executive summary" else "No items were extracted for this section."), styles["BodyText"]))
        story.append(Spacer(1, 8))
    if any(source.audio_warning for source in protocol.executive_summary_sources):
        story.append(Paragraph(t("Some cited passages have uncertain recognition. Check the recording for names and numbers."), styles["BodyText"]))
    story.append(Paragraph(t("Action items"), styles["Heading2"]))
    rows = [[Paragraph(t(key), styles['BodyText']) for key in ("Assignee", "Task", "Deadline", "Priority")]]
    rows.extend([
        [Paragraph(escape(item.assignee or "—"), styles["BodyText"]),
         Paragraph(escape(_qualified(item.task, item, t)), styles["BodyText"]),
         Paragraph(escape(" · ".join(dict.fromkeys(value for value in (item.deadline_date.isoformat() if item.deadline_date else None, item.deadline_text) if value)) or "—"), styles["BodyText"]), Paragraph(t(item.priority), styles['BodyText'])]
        for item in protocol.action_items
    ])
    table = Table(rows, repeatRows=1, colWidths=[90, 250, 90, 70])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeec")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
    ]))
    story.append(table)
    if not protocol.action_items:
        story.append(Paragraph(t("No action items were extracted. Owners and deadlines have not been invented."), styles["BodyText"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(t("Evidence references"), styles["Heading2"]))
    for index, source in enumerate(protocol.executive_summary_sources, 1):
        label = f'{t("Summary")} {index} → {source.item_id}: ' + ', '.join(source.evidence.segment_ids)
        if source.evidence.quote: label += ' — ' + source.evidence.quote
        story.append(Paragraph(escape(label), styles["BodyText"]))
    for item in protocol.decisions + protocol.topics + protocol.open_questions + protocol.action_items + protocol.risks:
        quote = item.evidence.quote or t("No verified source excerpt")
        citation = "{}: {} — {}".format(item.id, ", ".join(item.evidence.segment_ids) or t("No references"), quote)
        if item.evidence.start is not None and item.evidence.end is not None:
            citation += " [{:.2f}–{:.2f}s]".format(item.evidence.start, item.evidence.end)
        if item.evidence.speaker_name:
            citation += " — " + item.evidence.speaker_name + " (" + (item.evidence.speaker or "") + ")"
        citation += " — " + item.review_status
        story.append(Paragraph(escape(citation), styles["BodyText"]))
    _append_transcript(story, styles, transcript, new_page=True, language=language)
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=36, rightMargin=36).build(story)


def _append_transcript(story, styles, transcript, new_page, language='en'):
    t = translator(language)
    if transcript is not None:
        story.extend([PageBreak() if new_page else Spacer(1, 14), Paragraph(t("Transcript"), styles["Heading1"]),
            Paragraph(t("Speech recognition output for review. It may contain errors; timestamps refer to the original recording."), styles["BodyText"]), Spacer(1, 10)])
        for warning in transcript.warnings:
            story.append(Paragraph(escape(warning), styles["BodyText"]))
        for segment in transcript.segments:
            prefix = "[{:.2f}–{:.2f}s] ".format(segment.start, segment.end) if segment.start is not None and segment.end is not None else ""
            if segment.speaker:
                prefix += ((segment.speaker_name + " (" + segment.speaker + ")") if segment.speaker_name else segment.speaker) + ": "
            if segment.needs_review:
                prefix += t("[Check audio] ")
            story.append(Paragraph(escape(prefix + segment.text), styles["BodyText"]))
        if not transcript.segments:
            story.append(Paragraph(escape(transcript.raw_text or t("No speech was recognized. Check the recording and input audio source.")), styles["BodyText"]))


def _qualified(text, item, t=lambda value: value):
    if item.review_status == "rejected":
        return t("[Rejected] ") + text
    if item.review_status == "human_confirmed":
        return t("[Human confirmed] ") + text
    if item.review_status == "needs_review" or item.source_check in {"failed", "unavailable"}:
        return t("[Needs review] ") + text
    if item.audio_warning:
        return t("[Check audio] ") + text
    return text


def export_docx(path: Path, protocol: MeetingProtocol, transcript: Transcript | None = None) -> None:
    """Write a self-contained Word document using only local report data.

    OOXML stores text as Unicode and XML-escapes it rather than interpreting
    transcript content as markup. No external relationships or macros are used.
    """
    language = protocol.metadata.report_language or protocol.metadata.language
    t = translator(language)
    word = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    relationship = 'http://schemas.openxmlformats.org/package/2006/relationships'
    office = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
    content_type = 'http://schemas.openxmlformats.org/package/2006/content-types'

    def node(parent, name, attributes=None):
        return ET.SubElement(parent, '{' + word + '}' + name,
                             {'{' + word + '}' + key: str(value) for key, value in (attributes or {}).items()})

    def paragraph(parent, text, style=None, page_break=False):
        p = node(parent, 'p')
        if style or page_break:
            properties = node(p, 'pPr')
            if style:
                node(properties, 'pStyle', {'val': style})
            if page_break:
                node(properties, 'pageBreakBefore')
        # XML 1.0 cannot represent control characters or lone surrogates. Make
        # replacements visible rather than creating an unreadable document.
        clean = ''.join(char if char in '\t\n\r' or 0x20 <= ord(char) <= 0xD7FF
                        or 0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF
                        else '\uFFFD' for char in str(text))
        run = node(p, 'r')
        for line_index, line in enumerate(clean.replace('\r\n', '\n').replace('\r', '\n').split('\n')):
            if line_index:
                node(run, 'br')
            for part_index, part in enumerate(line.split('\t')):
                if part_index:
                    node(run, 'tab')
                element = node(run, 't')
                element.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                element.text = part
        return p

    document = ET.Element('{' + word + '}document')
    body = node(document, 'body')
    paragraph(body, protocol.metadata.title, 'Title')
    if protocol.metadata.meeting_date:
        paragraph(body, t('Meeting date: ') + protocol.metadata.meeting_date.isoformat())
    if protocol.metadata.timezone:
        paragraph(body, t('Timezone: ') + protocol.metadata.timezone)
    findings = protocol.decisions + protocol.topics + protocol.open_questions + protocol.action_items + protocol.risks
    has_report = bool(findings or protocol.executive_summary)
    if not has_report:
        paragraph(body, t('Report needs review'), 'Heading1')
        paragraph(body, t('No structured meeting findings were extracted. This is not a complete meeting protocol. Check the transcript and original recording before relying on this report.'))
    if transcript and transcript.warnings:
        paragraph(body, t('Transcription needs review'), 'Heading2')
        for warning in transcript.warnings:
            paragraph(body, warning)
    if has_report:
        paragraph(body, t('Executive summary'), 'Heading1')
        for line in protocol.executive_summary or [t('No source-checked summary is available.')]:
            paragraph(body, line)
        if any(source.audio_warning for source in protocol.executive_summary_sources):
            paragraph(body, t('Some cited passages have uncertain recognition. Check the recording for names and numbers.'))
        for title, items in (
            ('Decisions', protocol.decisions), ('Topics and key points', protocol.topics),
            ('Open questions', protocol.open_questions), ('Risks', protocol.risks),
        ):
            paragraph(body, t(title), 'Heading1')
            for item in items:
                text = item.title + ': ' + item.text if hasattr(item, 'title') else item.text
                paragraph(body, text if item.review_status == 'human_confirmed' else _qualified(text, item, t))
                paragraph(body, _docx_status(item, language))
            if not items:
                paragraph(body, t('No items were extracted for this section.'))
        paragraph(body, t('Action items'), 'Heading1')
        if protocol.action_items:
            table = node(body, 'tbl')
            properties = node(table, 'tblPr')
            node(properties, 'tblW', {'w': 10466, 'type': 'dxa'})
            borders = node(properties, 'tblBorders')
            for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
                node(borders, edge, {'val': 'single', 'sz': 4, 'color': 'AAAAAA'})
            grid = node(table, 'tblGrid')
            widths = (1700, 5366, 2000, 1400)
            for width in widths:
                node(grid, 'gridCol', {'w': width})
            rows = [[t(key) for key in ('Assignee', 'Task', 'Deadline', 'Priority')]]
            for item in protocol.action_items:
                deadline = item.deadline_text or ''
                if item.deadline_date and item.deadline_date.isoformat() not in deadline:
                    deadline += ('\n' if deadline else '') + item.deadline_date.isoformat()
                task = item.task if item.review_status == 'human_confirmed' else _qualified(item.task, item, t)
                rows.append([item.assignee or '—', task + '\n' + _docx_status(item, language),
                             deadline or '—', t(item.priority)])
            for index, row in enumerate(rows):
                tr = node(table, 'tr')
                if index == 0:
                    node(node(tr, 'trPr'), 'tblHeader')
                for width, text in zip(widths, row):
                    cell = node(tr, 'tc')
                    properties = node(cell, 'tcPr')
                    node(properties, 'tcW', {'w': width, 'type': 'dxa'})
                    if index == 0:
                        node(properties, 'shd', {'fill': 'EEEEEC', 'val': 'clear'})
                    paragraph(cell, text)
        else:
            paragraph(body, t('No action items were extracted. Owners and deadlines have not been invented.'))
        paragraph(body, t('Evidence references'), 'Heading1')
        for index, source in enumerate(protocol.executive_summary_sources, 1):
            label = f'{t("Summary")} {index} → {source.item_id}: ' + ', '.join(source.evidence.segment_ids)
            if source.evidence.quote:
                label += ' — ' + source.evidence.quote
            if source.audio_warning:
                label = t('[Check audio] ') + label
            paragraph(body, label)
        for item in findings:
            citation = '{}: {} — {}'.format(item.id, ', '.join(item.evidence.segment_ids) or t('No references'),
                                           item.evidence.quote or t('No verified source excerpt'))
            if _docx_speaker(item.evidence):
                citation += ' — ' + _docx_speaker(item.evidence)
            if item.evidence.start is not None and item.evidence.end is not None:
                citation += ' [{:.2f}–{:.2f}s]'.format(item.evidence.start, item.evidence.end)
            paragraph(body, citation)
    if transcript is not None:
        paragraph(body, t('Transcript'), 'Heading1', page_break=has_report)
        paragraph(body, t('Speech recognition output for review. It may contain errors; timestamps refer to the original recording.'))
        for segment in transcript.segments:
            prefix = '[{}] '.format(segment.id)
            if segment.start is not None and segment.end is not None:
                prefix += '[{:.2f}–{:.2f}s] '.format(segment.start, segment.end)
            if _docx_speaker(segment):
                prefix += _docx_speaker(segment) + ': '
            if segment.needs_review:
                prefix += t('[Check audio] ')
            paragraph(body, prefix + segment.text)
        if not transcript.segments:
            paragraph(body, transcript.raw_text or t('No speech was recognized. Check the recording and input audio source.'))
    section = node(body, 'sectPr')
    node(section, 'pgSz', {'w': 11906, 'h': 16838})
    node(section, 'pgMar', {'top': 720, 'right': 720, 'bottom': 720, 'left': 720, 'header': 360, 'footer': 360, 'gutter': 0})

    styles = ET.Element('{' + word + '}styles')
    defaults = node(node(styles, 'docDefaults'), 'rPrDefault')
    run_properties = node(defaults, 'rPr')
    node(run_properties, 'rFonts', {'ascii': 'Arial', 'hAnsi': 'Arial', 'cs': 'Arial', 'eastAsia': 'Arial'})
    node(run_properties, 'sz', {'val': 22})
    node(run_properties, 'lang', {'val': {'ru': 'ru-RU', 'kk': 'kk-KZ'}.get(language, 'en-US')})
    for name, size in (('Normal', 22), ('Title', 36), ('Heading1', 28), ('Heading2', 24)):
        attributes = {'type': 'paragraph', 'styleId': name}
        if name == 'Normal':
            attributes['default'] = '1'
        style = node(styles, 'style', attributes)
        node(style, 'name', {'val': name})
        if name != 'Normal':
            node(style, 'basedOn', {'val': 'Normal'})
            node(style, 'next', {'val': 'Normal'})
        properties = node(style, 'pPr')
        if name != 'Normal':
            node(properties, 'keepNext')
        node(properties, 'spacing', {'before': 160 if name != 'Normal' else 0, 'after': 100})
        run_properties = node(style, 'rPr')
        if name != 'Normal':
            node(run_properties, 'b')
        node(run_properties, 'sz', {'val': size})
    types = ET.Element('{' + content_type + '}Types')
    ET.SubElement(types, '{' + content_type + '}Default', Extension='rels', ContentType='application/vnd.openxmlformats-package.relationships+xml')
    ET.SubElement(types, '{' + content_type + '}Default', Extension='xml', ContentType='application/xml')
    for name, kind in (('document', 'document.main'), ('styles', 'styles')):
        ET.SubElement(types, '{' + content_type + '}Override', PartName='/word/' + name + '.xml',
                      ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.' + kind + '+xml')
    package_links = ET.Element('{' + relationship + '}Relationships')
    ET.SubElement(package_links, '{' + relationship + '}Relationship', Id='rId1', Type=office + 'officeDocument', Target='word/document.xml')
    document_links = ET.Element('{' + relationship + '}Relationships')
    ET.SubElement(document_links, '{' + relationship + '}Relationship', Id='rId1', Type=office + 'styles', Target='styles.xml')
    with ZipFile(path, 'w', compression=ZIP_DEFLATED) as archive:
        for name, root in (('[Content_Types].xml', types), ('_rels/.rels', package_links),
                           ('word/document.xml', document), ('word/styles.xml', styles), ('word/_rels/document.xml.rels', document_links)):
            archive.writestr(name, ET.tostring(root, encoding='utf-8', xml_declaration=True))


def _docx_speaker(source):
    name = getattr(source, 'speaker_name', None)
    if name and source.speaker and name != source.speaker:
        return f'{name} ({source.speaker})'
    return name or source.speaker


def _docx_status(item, language):
    """Keep automated source matching distinct from a person's review."""
    source, review, audio = {
        'ru': (
            {'passed': 'Соответствует расшифровке', 'failed': 'Не подтверждено расшифровкой', 'unavailable': 'Источник не проверен'},
            {'unreviewed': 'Не проверено человеком', 'needs_review': 'Требуется проверка', 'human_confirmed': 'Подтверждено человеком', 'rejected': 'Отклонено'},
            'Проверьте аудио'),
        'kk': (
            {'passed': 'Транскриптке сәйкес', 'failed': 'Транскриптпен расталмады', 'unavailable': 'Дереккөз тексерілмеген'},
            {'unreviewed': 'Адам тексермеген', 'needs_review': 'Тексеру қажет', 'human_confirmed': 'Адам растаған', 'rejected': 'Қабылданбады'},
            'Аудионы тексеріңіз'),
    }.get(language, (
        {'passed': 'Matches transcript', 'failed': 'Not supported by transcript', 'unavailable': 'Source not checked'},
        {'unreviewed': 'Not reviewed by a person', 'needs_review': 'Needs review', 'human_confirmed': 'Human confirmed', 'rejected': 'Rejected'},
        'Check audio'))
    labels = [source[item.source_check], review[item.review_status]]
    if item.audio_warning:
        labels.append(audio)
    return ' · '.join(labels)


def _pdf_font(font_path: str | None = None) -> str:
    """Register a Unicode font available on macOS, Linux/Radxa, or Windows."""
    candidates = [Path(font_path)] if font_path else [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            if "MeetingUnicode" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("MeetingUnicode", str(candidate)))
            return "MeetingUnicode"
    raise RuntimeError("No Unicode PDF font found; install DejaVu Sans or Arial")
