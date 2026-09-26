"""Deterministic discovery contracts, policies and lifecycle regressions."""
import asyncio
import hashlib
import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from testq_browser.policies import Frontier, normalize_url, redact, safe_url, selectors
from testq_browser.schemas import ApplicationMap, Artifact, DiscoveryLimits, DiscoveryRequest
from testq_browser.runner import DiscoveryEngine
from app.services.evidence_manager import EvidenceError, verify_artifact
from app.worker.pipeline import Pipeline, InvalidTransition
from app.models.test_run import TestRunStatus as S
from tests.test_hardening import new_run

BASE = 'http://127.0.0.1:4321'

@pytest.mark.parametrize('href,expected', [
    ('/a/../b?token=secret#x', BASE+'/b'), ('/%7euser', BASE+'/~user'),
    ('//example.com/a', None), ('javascript:alert(1)', None),
    ('http://user:secret@127.0.0.1:4321/', None),
    ('http://127.0.0.1:4322/', None), ('/a\\b', None),
])
def test_url_normalization(href, expected):
    assert normalize_url(href, BASE) == expected


def test_frontier_dedup_depth_and_page_limits():
    frontier = Frontier(BASE, 2, 1)
    assert not frontier.add('/?q=1', 1, BASE)
    assert not frontier.add('/deep', 2, BASE)
    assert frontier.add('/second', 1, BASE)
    assert not frontier.add('/third', 1, BASE)
    assert len(frontier.queue) == 2 and frontier.limited


def test_selector_priority():
    candidates = selectors(dict(test_id='save', role='button', accessible_name='Save',
        element_id='save-id', name='submit', placeholder='Save changes', css='button'))
    assert [c.strategy for c in candidates] == ['test_id','role','id','name','attribute','css']


def test_privacy():
    value = redact('password=hunter2 token=abc Bearer abcdef https://example.com/a?api_key=xyz')
    assert all(secret not in value for secret in ('hunter2','abcdef','xyz','abc '))
    assert safe_url(BASE+'/a?secret=123#456') == BASE+'/a'

@pytest.mark.parametrize('limits', [{'max_pages':0}, {'max_depth':9}, {'discovery_timeout':301}])
def test_invalid_limits(limits):
    with pytest.raises(ValidationError):
        DiscoveryLimits(**limits)

@pytest.mark.parametrize('url', ['https://example.com', 'http://localhost:4321', BASE+'/secret', BASE+'?token=x'])
def test_runner_accepts_only_target_loopback(url):
    with pytest.raises(ValidationError):
        DiscoveryRequest(run_id='run', session_id='session', base_url=url)


def test_evidence_integrity():
    data = b'[]'
    item = Artifact(kind='console', filename='console.json', size_bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(), media_type='application/json')
    verify_artifact(data, item)
    with pytest.raises(EvidenceError):
        verify_artifact(b'{}', item)
    with pytest.raises(ValidationError):
        Artifact(**{**item.model_dump(), 'filename':'../console.json'})

@pytest.mark.parametrize('mode', ['crash','timeout'])
async def test_browser_failure_retains_partial_result_and_closes(tmp_path, mode):
    class BrokenBrowser:
        closed = False
        def __init__(self, *args): pass
        async def open(self):
            if mode == 'timeout':
                await asyncio.sleep(10)
            raise RuntimeError('intentional browser failure')
        async def close(self): self.closed = True
    request = DiscoveryRequest(run_id='run',session_id='session',base_url=BASE,
        limits=DiscoveryLimits(discovery_timeout=0.05))
    engine = DiscoveryEngine(request, tmp_path, browser_factory=BrokenBrowser)
    result = await engine.run()
    assert result.status == ('failed' if mode=='crash' else 'timed_out')
    assert engine.browser.closed
    assert ApplicationMap.model_validate_json((tmp_path/'result.json').read_text()).status == result.status
    assert (tmp_path/'browser-errors.json').exists()


async def test_discovery_state_progress_persistence(db):
    run = await new_run(db)
    pipeline = Pipeline(db)
    for state in [S.CLONING,S.ANALYZING,S.BUILDING,S.STARTING,S.READY,S.DISCOVERING,S.DISCOVERY_COMPLETE]:
        await pipeline._update_status(run,state)
    await db.refresh(run)
    assert run.progress['discovering'] == 'completed'
    assert run.progress['discovery_complete'] == 'completed'
    assert run.progress.get('testing') != 'completed'
    with pytest.raises(InvalidTransition):
        await pipeline._update_status(run,S.TESTING)


@pytest.mark.parametrize('url', ['http://[broken', 'http://127.0.0.1:bad/', '/\\escape'])
def test_malformed_link_is_ignored(url):
    assert normalize_url(url, BASE) is None


def test_nondefault_scheme_port_preserved():
    assert safe_url('https://example.com:80/path?secret=x')=='https://example.com:80/path'


async def test_evidence_api_context_integrity_and_persistence(db,tmp_path,monkeypatch):
    from httpx import ASGITransport,AsyncClient
    from app.main import app
    from app.database import get_db
    from app.config import settings
    from app.models.discovery import DiscoverySession
    from app.services.evidence_manager import EvidenceManager
    run=await new_run(db)
    result=ApplicationMap(run_id=run.id,session_id='session',base_url=BASE,status='completed')
    db.add(DiscoverySession(id='session',run_id=run.id,status='completed',application_map=result.model_dump(mode='json')))
    await db.commit()
    monkeypatch.setattr(settings,'evidence_dir',str(tmp_path))
    row=await EvidenceManager(db).store_json(run.id,'session','console.json','console',[])
    async def override_db(): yield db
    app.dependency_overrides[get_db]=override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as api:
            response=await api.get(f'/api/test-runs/{run.id}/discovery')
            assert response.status_code==200 and response.json()['session_id']=='session'
            response=await api.get(f'/api/test-runs/{run.id}/evidence')
            assert response.status_code==200 and response.json()['evidence'][0]['sha256']==row.sha256
            url=response.json()['evidence'][0]['url']
            response=await api.get(url)
            assert response.status_code==200 and response.json()==[]
            assert (await api.get(f'/api/test-runs/another-run/evidence/{row.id}')).status_code==404
            (tmp_path/row.path).write_text('{}')
            assert (await api.get(url)).status_code==410
    finally:
        app.dependency_overrides.clear()


def test_sanitized_trace_omits_secrets_and_resources(tmp_path):
    import zipfile
    from testq_browser.artifacts import sanitize_trace
    raw=tmp_path/'raw.zip';safe=tmp_path/'trace.zip'
    events=[{'type':'context-options','version':8,'browserName':'chromium'},
            {'type':'before','callId':'call@1','method':'goto','params':{'url':BASE+'/?token=hidden','headers':{'Authorization':'hidden'}}},
            {'type':'console','text':'hidden'}]
    with zipfile.ZipFile(raw,'w') as archive:
        archive.writestr('trace.trace','\n'.join(json.dumps(e) for e in events))
        archive.writestr('trace.network','hidden')
        archive.writestr('resources/body','hidden')
    sanitize_trace(raw,safe,1024*1024)
    data=safe.read_bytes()
    item=Artifact(kind='trace',filename='trace.zip',size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),media_type='application/zip')
    verify_artifact(data,item)
    with zipfile.ZipFile(safe) as archive:
        assert set(archive.namelist())=={'trace.trace','trace.network'}
        assert b'hidden' not in archive.read('trace.trace')
        assert archive.read('trace.network')==b''

async def test_evidence_export_budget(db,tmp_path):
    from app.services.evidence_manager import EvidenceManager
    manager=EvidenceManager(db,tmp_path)
    manager.max_artifact_bytes=1
    with pytest.raises(EvidenceError,match='export budget'):
        await manager.store_json('run','session','console.json','console',[])
    assert not list(tmp_path.rglob('*.json'))
