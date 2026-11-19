"""Generates a structured, personalized Word (.docx) course handbook with copyright and distribution policies."""

from __future__ import annotations

import io
import re
import time
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor


_BRAND_PRIMARY = RGBColor(0x0F, 0x76, 0x6E)
_BRAND_DARK = RGBColor(0x0F, 0x17, 0x2A)
_BRAND_MUTED = RGBColor(0x47, 0x55, 0x69)
_BRAND_ACCENT = RGBColor(0x1E, 0x3A, 0x8A)
_CODE_TEXT = RGBColor(0x1E, 0x29, 0x3B)


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', str(name or 'Course_Handbook')).strip('_')
    return cleaned[:80] or 'Course_Handbook'


def _as_list(val: Any) -> list:
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    return []


def _shade_paragraph(paragraph, fill_hex: str = 'F1F5F9', left_border_hex: str | None = None) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    p_pr.append(shd)
    if left_border_hex:
        p_bdr = parse_xml(
            f'<w:pBdr {nsdecls("w")}>'
            f'<w:left w:val="single" w:sz="18" w:space="8" w:color="{left_border_hex}"/>'
            f'</w:pBdr>'
        )
        p_pr.append(p_bdr)


def _shade_cell(cell, fill_hex: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tc_pr.append(shd)


def _add_heading_styled(doc: Document, text: str, level: int = 1, color: RGBColor = _BRAND_DARK):
    h = doc.add_heading(str(text or '').strip(), level=level)
    for run in h.runs:
        run.font.color.rgb = color
        run.font.name = 'Calibri'
    return h


def _add_callout(doc: Document, label: str, body: str, fill_hex: str = 'F0FDFA', border_hex: str = '0F766E') -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.left_indent = Inches(0.15)
    p.paragraph_format.right_indent = Inches(0.15)
    _shade_paragraph(p, fill_hex=fill_hex, left_border_hex=border_hex)
    r_lbl = p.add_run(f'{label}: ')
    r_lbl.bold = True
    r_lbl.font.size = Pt(10)
    r_lbl.font.color.rgb = _BRAND_DARK
    r_body = p.add_run(str(body).strip())
    r_body.font.size = Pt(10)
    r_body.font.color.rgb = _BRAND_DARK


def _add_code_block(doc: Document, code_text: str, title: str | None = None) -> None:
    if title:
        tp = doc.add_paragraph()
        tp.paragraph_format.space_before = Pt(6)
        tp.paragraph_format.space_after = Pt(2)
        tr = tp.add_run(str(title).strip())
        tr.bold = True
        tr.font.size = Pt(9.5)
        tr.font.color.rgb = _BRAND_MUTED
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.left_indent = Inches(0.15)
    p.paragraph_format.right_indent = Inches(0.15)
    _shade_paragraph(p, fill_hex='F1F5F9', left_border_hex='64748B')
    run = p.add_run(str(code_text).rstrip())
    run.font.name = 'Consolas'
    run.font.size = Pt(9)
    run.font.color.rgb = _CODE_TEXT


def _add_bullet_list(doc: Document, items: list[str]) -> None:
    for item in items:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(item)
        r.font.size = Pt(10.5)


def _add_kv_table(doc: Document, rows: list[tuple[str, str]], col1_header: str = 'Term', col2_header: str = 'Explanation') -> None:
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    hdr[0].text = col1_header
    hdr[1].text = col2_header
    for idx, cell in enumerate(hdr):
        _shade_cell(cell, '0F766E')
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(9.5)
                r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        cell.width = Inches(2.1 if idx == 0 else 4.4)
    for k, v in rows:
        row_cells = table.add_row().cells
        row_cells[0].text = str(k)
        row_cells[1].text = str(v)
        row_cells[0].width = Inches(2.1)
        row_cells[1].width = Inches(4.4)
        for p in row_cells[0].paragraphs:
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(9.5)
        for p in row_cells[1].paragraphs:
            for r in p.runs:
                r.font.size = Pt(9.5)
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)


def _format_breakdown_rows(raw_breakdown: Any) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(raw_breakdown, dict):
        for k, v in raw_breakdown.items():
            rows.append((str(k).strip(), str(v).strip()))
    elif isinstance(raw_breakdown, list):
        for item in raw_breakdown:
            if isinstance(item, dict):
                term = str(item.get('term') or item.get('token') or item.get('word') or item.get('name') or '').strip()
                desc = str(item.get('meaning') or item.get('description') or item.get('explanation') or '').strip()
                if term or desc:
                    rows.append((term or 'Item', desc))
            elif isinstance(item, str) and item.strip():
                if ':' in item:
                    left, right = item.split(':', 1)
                    rows.append((left.strip(), right.strip()))
                elif ' - ' in item:
                    left, right = item.split(' - ', 1)
                    rows.append((left.strip(), right.strip()))
                else:
                    rows.append(('Note', item.strip()))
    return rows


def _configure_page_chrome(doc: Document, course_title: str, learner_name: str, year_str: str) -> None:
    for section in doc.sections:
        section.top_margin = Inches(0.85)
        section.bottom_margin = Inches(0.85)
        section.left_margin = Inches(0.9)
        section.right_margin = Inches(0.9)
        section.different_first_page_header_footer = True

        header = section.header
        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hr = hp.add_run(f'{course_title} — Personal Course Handbook')
        hr.font.size = Pt(8.5)
        hr.font.color.rgb = _BRAND_MUTED

        footer = section.footer
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.LEFT
        fr = fp.add_run(
            f'© {year_str} Siraugga / DevCore Academy  |  Licensed to {learner_name} for personal study  |  Redistribution restricted'
        )
        fr.font.size = Pt(8)
        fr.font.color.rgb = _BRAND_MUTED


def _add_copyright_and_distribution_section(doc: Document, course_title: str, learner_name: str, year_str: str) -> None:
    _add_heading_styled(doc, 'Copyright & Distribution Policy', level=1, color=_BRAND_PRIMARY)

    _add_callout(
        doc,
        'Copyright Notice',
        f'© {year_str} Siraugga / DevCore Academy (https://siraugga.mikeytech.dev). '
        f'All rights reserved. "{course_title}" and its curriculum structure, explanations, '
        'assessments, and supporting materials are the intellectual property of Siraugga / DevCore Academy.',
        fill_hex='F8FAFC',
        border_hex='1E3A8A',
    )

    _add_heading_styled(doc, '1. Personal Use License (What You May Do)', level=2, color=_BRAND_DARK)
    _add_bullet_list(doc, [
        f'This personal reference copy is licensed to {learner_name} upon course completion for individual study, revision, and offline reference.',
        'You may store copies on your own personal devices, print copies for personal or accessibility use, and annotate this document with your own notes.',
        'You may adapt and reuse the commands, configuration patterns, and code snippets taught in the labs within your own personal or workplace projects.',
        'You may quote brief excerpts for non-commercial educational discussion or personal notes, provided you retain attribution to Siraugga / DevCore Academy.',
    ])

    _add_heading_styled(doc, '2. Distribution & Redistribution Restrictions', level=2, color=_BRAND_DARK)
    _add_bullet_list(doc, [
        'No Public Redistribution: You may not upload, publish, mirror, resell, or share this full handbook or substantial portions of it on public websites, repositories, file-sharing services, or third-party platforms without prior written permission from Siraugga / DevCore Academy.',
        'No Commercial Resale or Rebranding: You may not sell this document, bundle it into paid training products, or present Siraugga curriculum materials as your own original courseware.',
        'Preserve Notices: You must not remove, alter, or obscure this copyright notice, learner attribution, or distribution policy from any copy.',
        'Team & Organizational Licensing: If your team, classroom, or organization wishes to distribute this handbook internally to multiple learners, please request an organizational license through the Siraugga portal.',
    ])

    _add_heading_styled(doc, '3. Educational Disclaimer', level=2, color=_BRAND_DARK)
    p = doc.add_paragraph(
        'This handbook is provided "as is" for educational and reference purposes. Always review and test '
        'commands, scripts, and infrastructure configurations in a safe, isolated environment before applying '
        'them to production systems.'
    )
    p.paragraph_format.space_after = Pt(10)


def build_course_handbook_docx(
    course_obj: dict,
    progress: dict | None = None,
    learner_name: str | None = None,
) -> tuple[bytes, str]:
    """Builds a structured Word (.docx) handbook for a completed course and returns (bytes, filename)."""
    progress = progress or {}
    reg = progress.get('registration') if isinstance(progress.get('registration'), dict) else {}
    cert = progress.get('certificate') if isinstance(progress.get('certificate'), dict) else {}

    resolved_name = str(
        learner_name
        or reg.get('full_name')
        or progress.get('learner_name')
        or 'Course Graduate'
    ).strip() or 'Course Graduate'
    resolved_email = str(reg.get('email') or '').strip()
    resolved_org = str(reg.get('organization') or '').strip()

    course_id = str(course_obj.get('course_id') or 'siraugga_course').strip()
    course_title = str(course_obj.get('title') or 'Siraugga Practical Course').strip()
    course_subtitle = str(course_obj.get('subtitle') or '').strip()
    badge_label = str(course_obj.get('badge_label') or 'Siraugga Practical Academy').strip()
    year_str = time.strftime('%Y', time.gmtime())
    issued_date = time.strftime('%Y-%m-%d', time.gmtime())

    doc = Document()
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(10.5)
    normal_style.font.color.rgb = _BRAND_DARK

    _configure_page_chrome(doc, course_title, resolved_name, year_str)

    # --- Cover Page ---
    badge_p = doc.add_paragraph()
    badge_p.paragraph_format.space_before = Pt(36)
    badge_p.paragraph_format.space_after = Pt(8)
    badge_r = badge_p.add_run(badge_label.upper())
    badge_r.bold = True
    badge_r.font.size = Pt(10)
    badge_r.font.color.rgb = _BRAND_PRIMARY

    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_after = Pt(8)
    title_r = title_p.add_run(course_title)
    title_r.bold = True
    title_r.font.size = Pt(26)
    title_r.font.color.rgb = _BRAND_DARK

    if course_subtitle:
        sub_p = doc.add_paragraph()
        sub_p.paragraph_format.space_after = Pt(18)
        sub_r = sub_p.add_run(course_subtitle)
        sub_r.font.size = Pt(13)
        sub_r.font.color.rgb = _BRAND_MUTED

    doc_type_p = doc.add_paragraph()
    doc_type_p.paragraph_format.space_after = Pt(24)
    doc_type_r = doc_type_p.add_run('Complete Learner Reference Handbook & Study Guide')
    doc_type_r.bold = True
    doc_type_r.font.size = Pt(12)
    doc_type_r.font.color.rgb = _BRAND_ACCENT

    modules = course_obj.get('modules') or []
    total_sections = sum(len(m.get('sections') or []) for m in modules)
    completed_count = len(progress.get('completed_steps') or [])

    meta_rows = [
        ('Prepared For', resolved_name),
        ('Course ID', course_id),
        ('Completion Date (UTC)', issued_date),
        ('Sections Verified', f'{min(completed_count, total_sections) or total_sections} / {total_sections}'),
    ]
    if resolved_email:
        meta_rows.insert(1, ('Learner Email', resolved_email))
    if resolved_org:
        meta_rows.insert(2, ('Organization', resolved_org))
    if cert.get('certificate_id'):
        meta_rows.append(('Certificate ID', str(cert.get('certificate_id'))))

    _add_kv_table(doc, meta_rows, col1_header='Handbook Record', col2_header='Details')

    cov_copy = doc.add_paragraph()
    cov_copy.paragraph_format.space_before = Pt(24)
    cov_copy_r = cov_copy.add_run(
        f'© {year_str} Siraugga / DevCore Academy. Licensed to {resolved_name} for personal, '
        'non-commercial study and reference. See Copyright & Distribution Policy on the next page.'
    )
    cov_copy_r.italic = True
    cov_copy_r.font.size = Pt(9.5)
    cov_copy_r.font.color.rgb = _BRAND_MUTED

    doc.add_page_break()

    # --- Copyright & Distribution Policy ---
    _add_copyright_and_distribution_section(doc, course_title, resolved_name, year_str)
    doc.add_page_break()

    # --- Course Overview & Curriculum Map ---
    _add_heading_styled(doc, 'Course Overview', level=1, color=_BRAND_PRIMARY)
    if course_obj.get('course_summary'):
        p = doc.add_paragraph(str(course_obj['course_summary']).strip())
        p.paragraph_format.space_after = Pt(8)

    course_objectives = _as_list(course_obj.get('objectives'))
    if course_objectives:
        _add_heading_styled(doc, 'Course Learning Objectives', level=2, color=_BRAND_DARK)
        _add_bullet_list(doc, course_objectives)

    if modules:
        _add_heading_styled(doc, 'Curriculum Map', level=2, color=_BRAND_DARK)
        map_rows = []
        for idx, mod in enumerate(modules, start=1):
            m_num = mod.get('module_number', idx - 1)
            m_title = str(mod.get('title') or f'Module {m_num}').strip()
            sec_count = len(mod.get('sections') or [])
            map_rows.append((f'Module {m_num}', f'{m_title} ({sec_count} sections)'))
        _add_kv_table(doc, map_rows, col1_header='Module', col2_header='Topic & Scope')

    # --- Modules & Sections ---
    step_outputs = progress.get('step_outputs') if isinstance(progress.get('step_outputs'), dict) else {}
    reflections = progress.get('reflections') if isinstance(progress.get('reflections'), dict) else {}

    for m_idx, mod in enumerate(modules, start=1):
        doc.add_page_break()
        m_num = mod.get('module_number', m_idx - 1)
        m_title = str(mod.get('title') or f'Module {m_num}').strip()
        _add_heading_styled(doc, f'Module {m_num}: {m_title}', level=1, color=_BRAND_PRIMARY)

        if mod.get('summary'):
            p = doc.add_paragraph(str(mod['summary']).strip())
            p.paragraph_format.space_after = Pt(6)

        m_objs = _as_list(mod.get('objectives'))
        if m_objs:
            _add_heading_styled(doc, 'Module Objectives', level=3, color=_BRAND_MUTED)
            _add_bullet_list(doc, m_objs)

        for s_idx, sec in enumerate(mod.get('sections') or [], start=1):
            sec_id = str(sec.get('id') or f'm{m_num}_s{s_idx}')
            sec_code = str(sec.get('section_code') or f'{m_num}.{s_idx}').strip()
            sec_title = str(sec.get('title') or f'Section {s_idx}').strip()
            _add_heading_styled(doc, f'{sec_code} — {sec_title}', level=2, color=_BRAND_DARK)

            s_objs = _as_list(sec.get('objectives'))
            if s_objs:
                _add_bullet_list(doc, [f'Objective: {o}' for o in s_objs])

            if sec.get('concept_summary'):
                p = doc.add_paragraph(str(sec['concept_summary']).strip())
                p.paragraph_format.space_after = Pt(5)

            bullets = _as_list(sec.get('concept_bullets'))
            if bullets:
                _add_bullet_list(doc, bullets)

            if sec.get('code_snippet'):
                _add_code_block(doc, str(sec['code_snippet']), title=sec.get('code_title') or 'Example')

            breakdown_rows = _format_breakdown_rows(sec.get('word_breakdown'))
            if breakdown_rows:
                _add_heading_styled(doc, 'Key Terms & Breakdown', level=3, color=_BRAND_MUTED)
                _add_kv_table(doc, breakdown_rows, col1_header='Term / Token', col2_header='Meaning')

            if sec.get('task_prompt'):
                _add_heading_styled(doc, 'Practical Exercise', level=3, color=_BRAND_MUTED)
                tp = doc.add_paragraph(str(sec['task_prompt']).strip())
                tp.paragraph_format.space_after = Pt(4)

                options = sec.get('options') or []
                if isinstance(options, list) and options:
                    for opt_i, opt in enumerate(options):
                        letter = chr(65 + opt_i) if opt_i < 26 else str(opt_i + 1)
                        op = doc.add_paragraph(f'  {letter}. {str(opt).strip()}')
                        op.paragraph_format.space_after = Pt(2)
                    c_idx = sec.get('correct_index')
                    if isinstance(c_idx, int) and 0 <= c_idx < len(options):
                        c_letter = chr(65 + c_idx) if c_idx < 26 else str(c_idx + 1)
                        _add_callout(doc, 'Reference Answer', f'{c_letter}. {options[c_idx]}', fill_hex='ECFDF5', border_hex='059669')

                if sec.get('expected_command'):
                    _add_code_block(doc, str(sec['expected_command']), title='Reference Command')
                if sec.get('solution_code'):
                    _add_code_block(doc, str(sec['solution_code']), title='Reference Solution')
                if sec.get('correct_text'):
                    _add_callout(doc, 'Reference Answer', str(sec['correct_text']), fill_hex='ECFDF5', border_hex='059669')

            common_errs = _as_list(sec.get('common_errors'))
            if common_errs:
                _add_heading_styled(doc, 'Common Pitfalls to Watch For', level=3, color=_BRAND_MUTED)
                _add_bullet_list(doc, common_errs)

            # Personalized learner submissions & reflections
            user_out = step_outputs.get(sec_id)
            user_ref = reflections.get(sec_id)
            if isinstance(user_out, dict):
                user_out_text = str(user_out.get('code') or user_out.get('command') or user_out.get('answer') or user_out.get('output') or '').strip()
            else:
                user_out_text = str(user_out or '').strip()
            if user_out_text:
                _add_code_block(doc, user_out_text[:1500], title='Your Recorded Lab Submission')
            if isinstance(user_ref, str) and user_ref.strip():
                _add_callout(doc, 'Your Reflection Note', user_ref.strip(), fill_hex='EFF6FF', border_hex='2563EB')

            if sec.get('takeaway'):
                _add_callout(doc, 'Key Takeaway', str(sec['takeaway']), fill_hex='F0FDFA', border_hex='0F766E')

        if mod.get('closing_summary'):
            _add_heading_styled(doc, f'Module {m_num} Wrap-Up', level=2, color=_BRAND_ACCENT)
            p = doc.add_paragraph(str(mod['closing_summary']).strip())
            p.paragraph_format.space_after = Pt(5)
        summary_bullets = _as_list(mod.get('summary_bullets'))
        if summary_bullets:
            _add_bullet_list(doc, summary_bullets)

    buf = io.BytesIO()
    doc.save(buf)
    filename = f"{_safe_filename(course_title)}_Handbook.docx"
    return buf.getvalue(), filename
