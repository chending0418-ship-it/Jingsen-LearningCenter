"""Versioned, fixed preparation lessons; original chapters remain unchanged."""
import copy
import json
import re
from pathlib import Path

CURRICULUM_PATH = Path(__file__).resolve().parent / 'curricula/shoedog-v1.json'


def lessons_for(book):
    if not re.search(r'\bshoe\s*dog\b', book['title'], re.I):
        return []
    curriculum = json.loads(CURRICULUM_PATH.read_text(encoding='utf-8'))
    # Resolve by narrative order, never hard-coded database IDs or PDF page offsets.
    chapters = [c for c in book['chapters'] if c['title'].strip().lower() not in {'part one', 'part two'}]
    expected = [title for lesson in curriculum['lessons'] for title in lesson['chapter_titles']]
    if [c['title'].strip().lower() for c in chapters] != [t.lower() for t in expected]:
        return []  # An unrecognized edition needs explicit chapter review.
    result, offset = [], 0
    for template in curriculum['lessons']:
        lesson = copy.deepcopy(template)
        count = len(lesson['chapter_titles'])
        selected = chapters[offset:offset + count]
        offset += count
        lesson.update(version=curriculum['version'], source=curriculum['source'],
                      chapter_ids=[c['id'] for c in selected],
                      start_page=selected[0]['start_page'], end_page=selected[-1]['end_page'])
        # Night may include back matter in the original detected chapter. Keep that
        # chapter intact for historical records; trim only the new lesson context.
        text = '\n\n'.join(c['content_text'] for c in selected)
        if lesson['number'] == 12:
            match = re.search(r'(?im)^\s*A\s*C\s*K\s*N\s*O\s*W\s*L\s*E\s*D\s*G\s*M\s*E\s*N\s*T\s*S\s*$', text)
            if match:
                text = text[:match.start()]
                markers = list(re.finditer(r'\[PDF page (\d+)\]', text))
                if markers:
                    # The last marker immediately precedes the back-matter heading.
                    last = markers[-1]
                    if not text[last.end():].strip():
                        text = text[:last.start()]
                        markers = markers[:-1]
                    if markers:
                        lesson['end_page'] = int(markers[-1].group(1))
        lesson['_reading_text'] = text
        result.append(lesson)
    return result


def public_lesson(lesson):
    public = copy.deepcopy({k: v for k, v in lesson.items() if not k.startswith('_')})
    public['questions'] = [{k: v for k, v in q.items() if k != 'reference_answer'}
                           for q in public['questions']]
    return public


def add_teacher_translations(session):
    """Enrich old snapshots for display without rewriting questions or answers."""
    if not session.get('preparation'):
        return session
    curriculum = json.loads(CURRICULUM_PATH.read_text(encoding='utf-8'))
    translations = {q['text']: q['text_en'] for lesson in curriculum['lessons']
                    for q in lesson['questions'] if q['source'] == 'teacher' and q.get('text_en')}
    for question in session.get('questions', []):
        if question.get('question_type') == 'teacher_discussion' and not question.get('question_text_en'):
            translation = translations.get(question['question_text'])
            if translation:
                question['question_text_en'] = translation
    return session


def reference_answers_for(session):
    """Exact-text matching for additive backfill of pre-answer-bank sessions."""
    curriculum = json.loads(CURRICULUM_PATH.read_text(encoding='utf-8'))
    answers = {q['text']: q['reference_answer'] for lesson in curriculum['lessons']
               for q in lesson['questions'] if q.get('reference_answer')}
    return {q['id']: answers[q['question_text']] for q in session['questions']
            if q['question_text'] in answers}
