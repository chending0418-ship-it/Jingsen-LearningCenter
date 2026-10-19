"""Preparation migration, fixed scope, private drafts and atomic grading."""
import asyncio
import copy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import api.reading as reading_api
from main import app
from services.reading_curriculum import CURRICULUM_PATH, lessons_for
from services.reading_service import ReadingService


class PrepAI:
    def __init__(self):
        self.calls = 0
        self.mode = 'ok'

    async def generate_json(self, prompt, **kwargs):
        self.calls += 1
        if self.mode == 'fail':
            raise RuntimeError('model unavailable')
        data = json.loads(prompt.split('DATA:\n', 1)[1])
        assert 'READING_ONLY_MARKER' in data['reading']
        assert 'BACK_MATTER_ONLY_MARKER' not in data['reading']
        rows = [{'id': w['id'], 'feedback': 'You connected the event to a reason. Explain how that changes the team.',
                 'understanding_level': 'clear', 'parent_note': 'Explains cause and effect.'} for w in data['work']]
        if self.mode == 'partial':
            rows.pop()
        return {'questions': rows, 'student_summary': 'You explained how the decision changed the team.',
                'parent_summary': 'Explained a decision with a story event.',
                'strengths': ['Explains cause and effect'], 'review_next': [],
                'next_steps': ['Compare two characters’ responses.']}


def make_preparation_service(tmp_path):
    service = ReadingService(data_root=tmp_path, ai_generator=PrepAI())
    curriculum = json.loads(CURRICULUM_PATH.read_text())
    titles = [t for l in curriculum['lessons'] for t in l['chapter_titles']]
    chapters = []
    for i, title in enumerate(titles):
        text = f'[PDF page {i+1}]\n{title}\nREADING_ONLY_MARKER The team made a decision under pressure.'
        if title == 'Night':
            text += f'\n[PDF page {i+2}]\nA C K N O W L E D G M E N T S\nBACK_MATTER_ONLY_MARKER'
        chapters.append({'id':f'ch-{i}', 'title':title, 'start_page':i+1, 'end_page':i+1,
                         'content_text':text})
    book = service.repository.create_book({'id':'shoe-book','title':'Shoe Dog', 'pdf_asset':'unused.pdf',
        'pdf_sha256':'fake-digest','page_count':24,'status':'published',
        'created_at':'2026-10-19T00:00:00Z','updated_at':'2026-10-19T00:00:00Z'},chapters)
    return service, book


def test_fixed_curriculum_and_snapshot_preserve_history(tmp_path):
    service, book = make_preparation_service(tmp_path)
    original = copy.deepcopy(book['chapters'])
    lessons = lessons_for(book)
    assert len(lessons) == 12
    assert [l['number'] for l in lessons] == list(range(1,13))
    assert lessons[7]['chapter_titles'] == ['1974','1975','1975']
    assert len(set(lessons[7]['chapter_ids'])) == 3
    assert 'BACK_MATTER_ONLY_MARKER' not in lessons[11]['_reading_text']
    assert lessons[11]['end_page'] == 22
    assert all(len(l['notes']) == 5 for l in lessons)
    assert all(5 <= len(l['questions']) <= 6 for l in lessons)
    old = service.repository.create_session({'id':'old','access_token_hash':'oldhash','book_id':book['id'],
        'chapter_ids':['ch-0'],'created_at':'old','updated_at':'old'},[{'question_text':'An old question'}])
    first = service.start_preparation(book['id'],'shoedog-08')
    second = service.start_preparation(book['id'],'shoedog-08')
    assert service.ai_generator.calls == 0
    assert [q['question_text'] for q in first['questions']] == [q['question_text'] for q in second['questions']]
    assert first['preparation']['lesson']['notes'] == lessons[7]['notes']
    assert '_reading_text' not in first['preparation']
    assert 'reference_answer' not in first['questions'][0]
    assert service.repository.get_book(book['id'])['chapters'] == original
    assert service.repository.get_session('old',True) == old
    assert not lessons_for(dict(book,title='Another Book'))
    assert not lessons_for(dict(book,chapters=book['chapters'][:-1]))


def test_draft_restore_conflicts_and_atomic_submission(tmp_path):
    service, book = make_preparation_service(tmp_path)
    s = service.start_preparation(book['id'],'shoedog-12')
    sid, token = s['id'],s['access_token']
    answers = {q['id']: 'The team made a difficult decision. This matters because they had little time.' for q in s['questions']}
    with pytest.raises(ValueError):
        service.save_preparation_draft(sid,'wrong-token',answers,0)
    with pytest.raises(ValueError):
        service.save_preparation_draft(sid,token,{'unknown':'answer'},0)
    saved = service.save_preparation_draft(sid,token,answers,0)
    assert saved['preparation']['revision'] == 1
    assert not any(q['child_answer'] or q['answered_at'] for q in saved['questions'])
    reloaded = ReadingService(data_root=tmp_path, ai_generator=service.ai_generator)
    assert reloaded.get_public_session(sid,token)['preparation']['drafts'] == answers
    with pytest.raises(ValueError,match='其他窗口'):
        reloaded.save_preparation_draft(sid,token,{},0)
    for mode in ('fail','partial'):
        service.ai_generator.mode=mode
        with pytest.raises((RuntimeError,ValueError)):
            asyncio.run(service.submit_preparation(sid,token,1))
        state=service.repository.get_session(sid,True)
        assert state['status']=='active'
        assert not any(q['answered_at'] for q in state['questions'])
        assert state['preparation']['drafts']==answers
    service.ai_generator.mode='ok'
    result=asyncio.run(service.submit_preparation(sid,token,1))
    assert result['status']=='completed'
    assert all(q['answered_at'] and q['feedback'] for q in result['questions'])
    assert result['preparation']['lesson']['version']=='shoedog-2026-10-19-v3'
    calls=service.ai_generator.calls
    assert asyncio.run(service.submit_preparation(sid,token,1))['status']=='completed'
    assert service.ai_generator.calls==calls
    with pytest.raises(ValueError):
        service.save_preparation_draft(sid,token,answers,2)
    assert any(x['id']==sid for x in service.list_admin_sessions())
    assert service.get_admin_session(sid)['questions'][0]['child_answer']


def test_preparation_routes_and_legacy_route_guard(tmp_path,monkeypatch):
    service,book=make_preparation_service(tmp_path)
    monkeypatch.setattr(reading_api,'get_reading_service',lambda:service)
    with TestClient(app) as client:
        public=client.get('/api/reading/books').json()['books'][0]
        assert len(public['lessons'])==12
        assert '_reading_text' not in json.dumps(public)
        s=client.post('/api/reading/preparations',json={'book_id':book['id'],'lesson_id':'shoedog-01'}).json()
        sid,token=s['id'],s['access_token']
        assert client.put(f'/api/reading/preparations/{sid}/draft',json={'access_token':token,'revision':0,'answers':{s['questions'][0]['id']:'a'*1501}}).status_code==422
        assert client.post(f'/api/reading/sessions/{sid}/finish',json={'access_token':token}).status_code==400
        assert client.post(f'/api/reading/sessions/{sid}/answers',json={'access_token':token,'question_id':s['questions'][0]['id'],'answer':'test'}).status_code==400
        assert client.post(f'/api/reading/preparations/{sid}/submit',json={'access_token':token,'revision':0}).status_code==400
        answers={q['id']:'test' for q in s['questions']}
        saved=client.put(f'/api/reading/preparations/{sid}/draft',json={'access_token':token,'revision':0,'answers':answers})
        assert saved.status_code==200
        result=client.post(f'/api/reading/preparations/{sid}/submit',json={'access_token':token,'revision':1})
        assert result.status_code==200
        assert result.json()['overall_level']=='needs_support'
        assert result.json()['evaluation']['strengths']==[]
        assert service.ai_generator.calls==0
        restored=client.get(f'/api/reading/sessions/{sid}',params={'access_token':token}).json()
        assert restored['status']=='completed'
        assert '_reading_text' not in restored['preparation']
        assert 'parent_summary' not in restored
        assert 'parent_note' not in restored['questions'][0]
        assert restored['evaluation']['next_steps']


def test_v5_migration_preserves_existing_rows(tmp_path):
    service,book=make_preparation_service(tmp_path)
    old=service.repository.create_session({'id':'before-v6','access_token_hash':'hash','book_id':book['id'], 'chapter_ids':['ch-0'],'created_at':'old','updated_at':'old'},[{'question_text':'Historical question'}])
    path=service.repository.database.path
    with sqlite3.connect(path) as conn:
        conn.execute('ALTER TABLE reading_sessions DROP COLUMN preparation_json')
        conn.execute('DELETE FROM schema_migrations WHERE version=6')
    from database.sqlite import SQLiteDatabase
    database=SQLiteDatabase(path);database.initialize();database.initialize()
    with database.read() as conn:
        assert 'preparation_json' in {r['name'] for r in conn.execute('pragma table_info(reading_sessions)')}
        assert conn.execute('select count(*) from reading_chapters').fetchone()[0]==22
        assert conn.execute("select preparation_json from reading_sessions where id='before-v6'").fetchone()[0]=='{}'
        assert conn.execute("select question_text from reading_session_questions where session_id='before-v6'").fetchone()[0]=='Historical question'
        assert conn.execute('select count(*) from schema_migrations where version=6').fetchone()[0]==1


def test_edit_during_grading_rejects_stale_result_and_keeps_new_draft(tmp_path):
    service,book=make_preparation_service(tmp_path)
    s=service.start_preparation(book['id'],'shoedog-03')
    sid,token=s['id'],s['access_token']
    answers={q['id']:'The decision put pressure on the team because they needed more money.' for q in s['questions']}
    service.save_preparation_draft(sid,token,answers,0)
    original_generate=service.ai_generator.generate_json

    async def edit_during_grading(prompt,**kwargs):
        updated=dict(answers)
        updated[s['questions'][0]['id']]='A revised explanation with a different reason.'
        service.save_preparation_draft(sid,token,updated,1)
        return await original_generate(prompt,**kwargs)

    service.ai_generator.generate_json=edit_during_grading
    with pytest.raises(ValueError,match='其他窗口'):
        asyncio.run(service.submit_preparation(sid,token,1))
    state=service.repository.get_session(sid,True)
    assert state['status']=='active'
    assert state['preparation']['revision']==2
    assert state['preparation']['drafts'][s['questions'][0]['id']].startswith('A revised')
    assert all(not q['answered_at'] and not q['feedback'] for q in state['questions'])


def test_teacher_questions_bilingual_and_old_snapshots_unchanged(tmp_path):
    service,book=make_preparation_service(tmp_path)
    lessons=service.list_public_books()[0]['lessons']
    teachers=[q for lesson in lessons for q in lesson['questions'] if q['source']=='teacher']
    assert len(teachers)==38
    assert all(q['text'] and q['text_en'] and q['text']!=q['text_en'] for q in teachers)
    session=service.start_preparation(book['id'],'shoedog-01')
    stored=service.repository.get_session(session['id'],True)
    teacher_questions=[q for q in stored['questions'] if q['question_type']=='teacher_discussion']
    assert all(q['question_text_en'] for q in teacher_questions)
    assert teacher_questions[0]['question_text_en']==teachers[0]['text_en']
    # Simulate a pre-translation v1 session, with answers and snapshot intact.
    with service.repository.database.transaction() as conn:
        prep=dict(stored['preparation'])
        prep['lesson']['version']='shoedog-2026-10-19-v1'
        for q in prep['lesson']['questions']:
            q.pop('text_en',None)
        conn.execute('UPDATE reading_sessions SET preparation_json=? WHERE id=?',(json.dumps(prep),session['id']))
        conn.execute("UPDATE reading_session_questions SET extra_json='{}',child_answer='My existing answer' WHERE session_id=?",(session['id'],))
    original=service.repository.get_session(session['id'],True)
    public=service.get_public_session(session['id'],session['access_token'])
    admin=service.get_admin_session(session['id'])
    for returned in (public,admin):
        assert returned['questions'][0]['question_text_en']==teachers[0]['text_en']
        assert returned['questions'][0]['child_answer']=='My existing answer'
        assert returned['preparation']['lesson']['version']=='shoedog-2026-10-19-v1'
    assert service.repository.get_session(session['id'],True)==original


def test_single_answer_reveals_only_its_reference_and_finishes_same_session(tmp_path):
    service,book=make_preparation_service(tmp_path)
    s=service.start_preparation(book['id'],'shoedog-03')
    sid,token=s['id'],s['access_token']
    assert 'reference_answer' not in json.dumps(service.list_public_books())
    assert all('reference_answer' not in q for q in s['questions'])
    answer='Johnson needs feedback because his letters ask for recognition and guidance.'
    first_id=s['questions'][2]['id']  # Submission order is unrestricted.
    after=asyncio.run(service.submit_preparation_answer(sid,token,0,first_id,answer))
    assert after['id']==sid and after['status']=='active'
    assert after['preparation']['revision']==1
    answered=next(q for q in after['questions'] if q['id']==first_id)
    assert answered['child_answer']==answer
    assert answered['reference_answer'] and answered['feedback'] and answered['understanding_level']=='clear'
    assert all('reference_answer' not in q for q in after['questions'] if not q['answered_at'])
    assert 'parent_note' not in answered
    calls=service.ai_generator.calls
    assert asyncio.run(service.submit_preparation_answer(sid,token,0,first_id,answer))['id']==sid
    assert service.ai_generator.calls==calls
    with pytest.raises(ValueError,match='不能修改'):
        asyncio.run(service.submit_preparation_answer(sid,token,1,first_id,'A changed answer.'))
    with pytest.raises(ValueError,match='不能修改'):
        service.save_preparation_draft(sid,token,{first_id:'A changed draft.'},1)
    with pytest.raises(ValueError,match='其他窗口'):
        asyncio.run(service.submit_preparation_answer(sid,token,0,s['questions'][0]['id'],answer))
    revision=1
    for question in s['questions']:
        if question['id']==first_id:
            continue
        after=asyncio.run(service.submit_preparation_answer(sid,token,revision,question['id'],answer))
        revision+=1
    assert after['status']=='completed'
    assert after['id']==sid
    assert after['completed_at'] and after['student_summary'] and after['evaluation']['next_steps']
    reloaded=ReadingService(data_root=tmp_path,ai_generator=service.ai_generator)
    for _ in range(3):
        restored=reloaded.get_public_session(sid,token)
        assert restored['status']=='completed'
        assert [(q['child_answer'],q['reference_answer'],q['feedback'],q['understanding_level']) for q in restored['questions']]==[(q['child_answer'],q['reference_answer'],q['feedback'],q['understanding_level']) for q in after['questions']]
    assert len(reloaded.repository.list_sessions())==1


def test_legacy_completed_references_backfilled_once_without_regrading(tmp_path,monkeypatch):
    service,book=make_preparation_service(tmp_path)
    s=service.start_preparation(book['id'],'shoedog-01')
    sid,token=s['id'],s['access_token']
    with service.repository.database.transaction() as conn:
        conn.execute("UPDATE reading_sessions SET status='completed',overall_level='mostly_clear',student_summary='Original summary',completed_at='original-time' WHERE id=?",(sid,))
        conn.execute("UPDATE reading_session_questions SET reference_answer='Use the lesson text and teacher notes as context; accept supported alternative interpretations.',child_answer='Original answer',feedback='Original feedback',understanding_level='mostly_clear',answered_at='original-time' WHERE session_id=?",(sid,))
    after=service.get_public_session(sid,token)
    assert after['questions'][0]['reference_answer'].startswith('A bold idea')
    assert after['questions'][0]['child_answer']=='Original answer'
    assert after['questions'][0]['feedback']=='Original feedback'
    assert after['student_summary']=='Original summary'
    assert after['completed_at']=='original-time'
    assert service.ai_generator.calls==0
    stored=service.repository.get_session(sid,True)
    assert stored['questions'][0]['reference_answer']==after['questions'][0]['reference_answer']
    import services.reading_curriculum as module
    changed=json.loads(CURRICULUM_PATH.read_text())
    changed['lessons'][0]['questions'][0]['reference_answer']='A future replacement answer.'
    path=tmp_path/'future-curriculum.json';path.write_text(json.dumps(changed))
    monkeypatch.setattr(module,'CURRICULUM_PATH',path)
    again=service.get_public_session(sid,token)
    assert again['questions'][0]['reference_answer']==after['questions'][0]['reference_answer']
    assert again['questions'][0]['understanding_level']=='mostly_clear'


def test_single_question_api_failures_leave_drafts_and_other_grades_unchanged(tmp_path,monkeypatch):
    service,book=make_preparation_service(tmp_path)
    monkeypatch.setattr(reading_api,'get_reading_service',lambda:service)
    with TestClient(app) as client:
        s=client.post('/api/reading/preparations',json={'book_id':book['id'],'lesson_id':'shoedog-01'}).json()
        sid,token=s['id'],s['access_token']
        payload={'access_token':token,'revision':0,'question_id':s['questions'][0]['id'],'answer':'The idea needs financial support and a practical first step.'}
        assert client.post(f'/api/reading/preparations/{sid}/answers',json=dict(payload,access_token='wrong-token-with-enough-length')).status_code==404
        assert client.post(f'/api/reading/preparations/{sid}/answers',json=dict(payload,question_id='other-session-question')).status_code==404
        assert client.post(f'/api/reading/preparations/{sid}/answers',json=dict(payload,answer=' ')).status_code==400
        assert client.post(f'/api/reading/preparations/{sid}/answers',json=dict(payload,answer='a'*1501)).status_code==422
        drafts={s['questions'][0]['id']:payload['answer'],s['questions'][1]['id']:'My unfinished draft.'}
        client.put(f'/api/reading/preparations/{sid}/draft',json={'access_token':token,'revision':0,'answers':drafts})
        payload['revision']=1
        service.ai_generator.mode='fail'
        assert client.post(f'/api/reading/preparations/{sid}/answers',json=payload).status_code==502
        state=service.repository.get_session(sid,True)
        assert state['preparation']['drafts']==drafts
        assert not any(q['answered_at'] for q in state['questions'])
        service.ai_generator.mode='ok'
        response=client.post(f'/api/reading/preparations/{sid}/answers',json=payload)
        assert response.status_code==200
        assert response.json()['status']=='active'
        assert response.json()['questions'][0]['reference_answer']
        assert 'reference_answer' not in response.json()['questions'][1]
        state=client.get(f'/api/reading/sessions/{sid}',params={'access_token':token}).json()
        assert state['questions'][0]['feedback']
        assert state['preparation']['drafts'][s['questions'][1]['id']]=='My unfinished draft.'
        first_grade=dict(state['questions'][0])
        remaining={q['id']:q.get('child_answer') or 'The idea needs support and an action that tests it.' for q in state['questions']}
        saved=client.put(f'/api/reading/preparations/{sid}/draft',json={'access_token':token,'revision':state['preparation']['revision'],'answers':remaining}).json()
        completed=client.post(f'/api/reading/preparations/{sid}/submit',json={'access_token':token,'revision':saved['preparation']['revision']}).json()
        assert completed['status']=='completed'
        assert completed['questions'][0]==first_grade
        assert all(q['reference_answer'] and q['feedback'] for q in completed['questions'])

