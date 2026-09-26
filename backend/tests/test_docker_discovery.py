"""Real same-container discovery, gated by TESTQ_DOCKER_TESTS=1."""
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.discovery import DiscoverySession, Evidence
from app.models.test_run import TestRunStatus as S
from app.worker.pipeline import Pipeline
from app.worker.control import RunControl
from tests.test_docker_hardening import git_fixture, LocalGit
from tests.test_hardening import new_run
from testq_browser.schemas import ApplicationMap

pytestmark = [pytest.mark.docker, pytest.mark.skipif(
    os.environ.get('TESTQ_DOCKER_TESTS') != '1', reason='Requires real Docker')]


async def test_real_discovery_pipeline(db, tmp_path, monkeypatch):
    source = git_fixture(tmp_path, 'success')
    (source/'server.js').write_text(r'''
const http = require('http');
const port = process.env.PORT || 4321;
const html = `<!doctype html><title>TestQ fixture</title><h1>Discovery fixture</h1>
<a href="/second">Second page</a><a href="/login">Login</a><a href="/broken">Broken</a>
<a href="https://example.com/">External</a><button data-testid="hello">Hello</button>
<form id="login" action="/api/login" method="post"><label for="email">Email</label>
<input id="email" name="email" type="email" required><input type="password" name="password">
<input type="checkbox" name="remember"><input type="radio" name="choice">
<select name="country"><option>India</option></select><textarea name="notes"></textarea>
<button type="submit">Sign in</button></form>
<script>console.error('intentional console observation');fetch('/api/products');
fetch('https://example.com/blocked').catch(()=>{});
setTimeout(()=>{throw new Error('intentional browser observation')},10);</script>`;
console.log('DISCOVERY-APP-STDOUT');
http.createServer((req,res)=>{
 if(req.url==='/api/products'){res.setHeader('Content-Type','application/json');return res.end('[]');}
 if(req.url==='/broken'){res.statusCode=404;return res.end('Missing');}
 res.setHeader('Content-Type','text/html'); res.end(html);
}).listen(port,'127.0.0.1');
''')
    subprocess.run(['git','-C',str(source),'add','.'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(source),'-c','user.name=TestQ','-c','user.email=testq@example.invalid',
                    'commit','-m','browser fixture'],check=True,capture_output=True)
    evidence_root = Path(os.environ.get('TESTQ_FIXTURE_EVIDENCE_DIR', str(tmp_path/'evidence'))).resolve()
    monkeypatch.setattr(settings,'evidence_dir',evidence_root)
    run = await new_run(db)
    run.discovery_enabled = True
    await db.commit()
    pipeline = Pipeline(db,RunControl(180),github=LocalGit(tmp_path/'clones',source))
    await pipeline.run(run)
    assert run.status == S.DISCOVERY_COMPLETE, run.failure_reason
    session = (await db.execute(select(DiscoverySession).where(DiscoverySession.run_id==run.id))).scalar_one()
    result = ApplicationMap.model_validate(session.application_map)
    assert len(result.pages)==4
    assert any(p.status==404 and p.navigation=='http_error' for p in result.pages)
    home = result.pages[0]
    assert home.title=='TestQ fixture' and home.forms and home.buttons and home.inputs
    assert {'email','password','checkbox','radio'} <= {i.input_type for i in home.inputs}
    assert any(e.path=='/api/products' for e in result.api_endpoints)
    assert {'console_error','browser_error','external_blocked'} <= {o.kind for o in result.observations}
    artifacts = (await db.execute(select(Evidence).where(Evidence.run_id==run.id))).scalars().all()
    assert {'screenshot','trace','application_map','application_log','console','network'} <= {a.kind for a in artifacts}
    assert all((Path(settings.evidence_dir)/a.path).is_file() for a in artifacts)
    assert not pipeline.sandbox.client.containers.list(all=True,filters={'label':f'testq.run_id={run.id}'})
    import json
    (evidence_root/'fixture-verification.json').write_text(json.dumps({
        'run_id':run.id,'status':run.status,'pages':len(result.pages),
        'artifacts':[a.path for a in artifacts]},indent=2))


@pytest.mark.parametrize('mode', ['navigation_timeout','discovery_timeout','cancel','page_limit','depth_limit','browser_failure'])
async def test_real_discovery_limits_and_failures(db, tmp_path, monkeypatch, mode):
    import asyncio
    import time
    from app.services.sandbox_manager import SandboxManager
    from testq_browser.schemas import DiscoveryLimits
    source = git_fixture(tmp_path,'success')
    (source/'server.js').write_text("""
const http=require('http');const port=process.env.PORT||4321;
http.createServer((req,res)=>{
 if(req.url==='/slow'){console.log('SLOW-PAGE-REQUESTED');return;}
 res.setHeader('Content-Type','text/html');
 res.end('<title>Limits</title><a href="/slow">Slow</a><a href="/last">Last</a>');
}).listen(port,'127.0.0.1');
""")
    subprocess.run(['git','-C',str(source),'add','.'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(source),'-c','user.name=TestQ','-c','user.email=testq@example.invalid',
                    'commit','-m','limits fixture'],check=True,capture_output=True)
    limits=DiscoveryLimits(navigation_timeout=2,discovery_timeout=20)
    if mode=='discovery_timeout': limits.discovery_timeout=2; limits.navigation_timeout=10
    if mode=='cancel': limits.navigation_timeout=30; limits.discovery_timeout=60
    if mode=='page_limit': limits.max_pages=1
    if mode=='depth_limit': limits.max_depth=0
    monkeypatch.setattr(type(settings),'discovery_limits',lambda self:limits)
    monkeypatch.setattr(settings,'evidence_dir',tmp_path/'evidence')
    class BrokenBrowserSandbox(SandboxManager):
        def execute(self,container_id,command,**kwargs):
            if kwargs.get('source')=='discovery':
                # Deliberately invalid controlled browser executable location.
                kwargs['environment']['PLAYWRIGHT_BROWSERS_PATH']='/nonexistent'
            return super().execute(container_id,command,**kwargs)
    run=await new_run(db);run.discovery_enabled=True;await db.commit()
    pipeline=Pipeline(db,RunControl(120),github=LocalGit(tmp_path/'clones',source),
                      sandbox_factory=BrokenBrowserSandbox if mode=='browser_failure' else SandboxManager)
    task=asyncio.create_task(pipeline.run(run))
    if mode=='cancel':
        for _ in range(300):
            await asyncio.sleep(.1)
            if task.done(): break
            if run.container_id and pipeline.sandbox:
                logs=await asyncio.to_thread(pipeline.sandbox.collect_logs,run.container_id)
                if any('SLOW-PAGE-REQUESTED' in value for _,_,value in logs):
                    from httpx import ASGITransport, AsyncClient
                    from sqlalchemy.ext.asyncio import async_sessionmaker
                    from app.database import get_db
                    from app.main import app
                    sessions = async_sessionmaker(db.bind, expire_on_commit=False)
                    async def override_db():
                        async with sessions() as session:
                            yield session
                    app.dependency_overrides[get_db] = override_db
                    try:
                        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as api:
                            response = await api.post(f'/api/test-runs/{run.id}/cancel')
                            assert response.status_code in (200,202), response.text
                    finally:
                        app.dependency_overrides.clear()
                    break
        assert pipeline.control.cancel_event.is_set()
    await asyncio.wait_for(task,120)
    expected=S.CANCELLED if mode=='cancel' else S.FAILED if mode in ('discovery_timeout','browser_failure') else S.DISCOVERY_COMPLETE
    assert run.status==expected,run.failure_reason
    session=(await db.execute(select(DiscoverySession).where(DiscoverySession.run_id==run.id))).scalar_one()
    result=ApplicationMap.model_validate(session.application_map)
    assert not pipeline.sandbox.client.containers.list(all=True,filters={'label':f'testq.run_id={run.id}'})
    if mode=='navigation_timeout':
        assert any(p.navigation=='timeout' for p in result.pages)
        assert any(p.url.endswith('/last') and p.navigation=='ok' for p in result.pages)
    if mode in ('page_limit','depth_limit'): assert len(result.pages)==1 and result.truncated
    if mode=='cancel': assert result.status=='cancelled' and result.pages
    if mode=='discovery_timeout': assert result.status=='timed_out'
    artifacts=(await db.execute(select(Evidence).where(Evidence.run_id==run.id))).scalars().all()
    assert artifacts and all((Path(settings.evidence_dir)/a.path).exists() for a in artifacts)


@pytest.mark.parametrize('image',['testq-sandbox-node:latest','testq-sandbox-python:latest'])
def test_real_chromium_launch_and_security(image):
    from app.services.sandbox_manager import SandboxManager
    from app.schemas.common import SandboxConfig
    sandbox=SandboxManager(RunControl(40))
    try:
        cid=sandbox.create(SandboxConfig(image=image,browser_enabled=True,timeout=40))['container_id']
        sandbox.restrict_network(cid)
        container=sandbox.client.containers.get(cid);container.reload()
        host=container.attrs['HostConfig']
        assert not container.attrs['Mounts'] and not container.attrs['NetworkSettings']['Networks']
        assert not host['Privileged'] and host['CapDrop']==['ALL']
        assert host['PidsLimit']==256 and host['NanoCpus']==2_000_000_000
        assert host['Memory']==2*1024**3 and host['ShmSize']==256*1024**2
        assert host['IpcMode']!='host' and not host['PortBindings']
        result=sandbox.execute(cid,"/opt/testq/venv/bin/python -I -c 'from playwright.sync_api import sync_playwright; import os; p=sync_playwright().start(); b=p.chromium.launch(chromium_sandbox=True); print(os.getuid(), b.version); b.close(); p.stop()'",
                               user='10002:10002',environment={'HOME':'/home/browser'},timeout=20)
        assert result.exit_code==0,result.stderr
        assert result.stdout.startswith('10002 ')
    finally:
        sandbox.cleanup()

@pytest.mark.skipif(os.environ.get('TESTQ_PUBLIC_APP_TEST')!='1',reason='Explicit public repository verification')
async def test_public_supported_application(db,tmp_path,monkeypatch):
    import json
    from app.services.github_service import GitHubService
    root=Path(os.environ.get('TESTQ_VERIFICATION_DIR',str(tmp_path/'public-evidence'))).resolve()
    monkeypatch.setattr(settings,'evidence_dir',root)
    run=await new_run(db)
    run.project.repository_url='https://github.com/heroku/node-js-getting-started'
    run.discovery_enabled=True
    await db.commit()
    pipeline=Pipeline(db,RunControl(300),github=GitHubService(tmp_path/'clones'))
    await pipeline.run(run)
    assert run.status==S.DISCOVERY_COMPLETE,run.failure_reason
    session=(await db.execute(select(DiscoverySession).where(DiscoverySession.run_id==run.id))).scalar_one()
    result=ApplicationMap.model_validate(session.application_map)
    assert result.pages[0].navigation=='ok' and result.pages[0].status==200
    artifacts=(await db.execute(select(Evidence).where(Evidence.run_id==run.id))).scalars().all()
    assert any(a.kind=='trace' for a in artifacts) and any(a.kind=='screenshot' for a in artifacts)
    assert all((root/a.path).exists() for a in artifacts)
    assert not pipeline.sandbox.client.containers.list(all=True,filters={'label':f'testq.run_id={run.id}'})
    (root/'public-verification.json').write_text(json.dumps({'repository':run.project.repository_url,
        'commit_sha':run.commit_sha,'run_id':run.id,'status':run.status,'pages':len(result.pages),
        'artifacts':[a.path for a in artifacts]},indent=2))
