import asyncio
import json
import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings, ROOT
from .store import Store
from .knowledge import Knowledge
from .agent import Agent
from .devices import dispatch
from .video import analyze_video

class AnalysisRequest(BaseModel):
    mode: Literal['demo','local']='demo'

class ApprovalRequest(BaseModel):
    approve: bool
    reviewer: str=Field(min_length=1,max_length=60)

class SearchRequest(BaseModel):
    query: str=Field(min_length=1,max_length=300)

class SearchFilter(BaseModel):
    event_type: Literal['ALL','INTRUSION','NO_HELMET']=Field(default='ALL',description='闯入/禁区=INTRUSION；未戴安全帽=NO_HELMET；没指定=ALL')
    status: Literal['ALL','new','awaiting_approval','needs_review','device_acknowledged','mock_executed','rejected','error']=Field(default='ALL',description='待审批=awaiting_approval；待研判=new；证据不足=needs_review；已拒绝=rejected；失败=error；未指定=ALL')
    min_duration: float=Field(default=0,ge=0,le=120)

def create_app(settings=None):
    settings=settings or Settings()
    store=Store(settings.data_dir)
    knowledge=Knowledge(ROOT/'knowledge'/'sop.json')
    agent=Agent(settings,knowledge,store)
    model_lock=asyncio.Lock()
    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        print('VisionGuard local approval token: '+settings.approval_token, flush=True)
        yield
    app=FastAPI(title='VisionGuard',version='1.0.0',lifespan=lifespan)
    app.state.store=store; app.state.agent=agent; app.state.settings=settings

    def event_or_404(eid):
        event=store.get(eid)
        if not event: raise HTTPException(404,'Event not found')
        return event

    @app.get('/api/health')
    async def health():
        models=[]; available=False
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                r=await client.get(settings.ollama_url+'/api/tags'); r.raise_for_status()
                models=[m['name'] for m in r.json().get('models',[])]; available=True
        except (httpx.HTTPError,ValueError): pass
        return {'status':'ok','ollama':available,'models':models,'agent_model':settings.model,
                'vision_model':settings.vision_model,'device_mode':settings.device_mode,
                'retrieval':'Local: BGE-M3/FAISS/BM25 with explicit BM25 fallback; demo: BM25',
                'storage':'SQLite','demo_only_rules':True}

    @app.get('/api/events')
    def events(): return store.list()

    @app.post('/api/search')
    async def search_events(request:SearchRequest):
        try:
            async with model_lock, httpx.AsyncClient(timeout=120) as client:
                r=await client.post(settings.ollama_url+'/api/chat',json={
                    'model':settings.model,'stream':False,'think':False,'keep_alive':0,
                    'format':SearchFilter.model_json_schema(),
                    'options':{'num_ctx':2048,'num_predict':200,'temperature':0},
                    'messages':[{'role':'system','content':'Translate the user query into event_type, status and min_duration filters. '
                      'Chinese mappings: 闯入/禁区=INTRUSION, 未戴安全帽=NO_HELMET, 待审批/待批准=awaiting_approval, '
                      '待研判=new, 证据不足/待复核=needs_review, 已拒绝=rejected, 已执行=device_acknowledged. '
                      'Example: 待审批的闯入事件 -> {"event_type":"INTRUSION","status":"awaiting_approval","min_duration":0}. '
                      'Use ALL only if that field is not mentioned. Extract seconds as min_duration. Return JSON only. /no_think'},
                      {'role':'user','content':request.query}]})
                r.raise_for_status(); filters=SearchFilter.model_validate_json(r.json()['message']['content'])
        except (httpx.HTTPError,ValueError,KeyError) as exc:
            raise HTTPException(503,'自然语言检索需要可用的本地语言模型') from exc
        found=[e for e in store.list() if (filters.event_type=='ALL' or e['event_type']==filters.event_type)
               and (filters.status=='ALL' or e['status']==filters.status) and e['duration']>=filters.min_duration]
        return {'filters':filters.model_dump(),'events':found,
                'scope':'最近200条事件，仅支持事件类型、状态和最短持续时间；日期/跨镜头身份查询尚未实现'}

    @app.post('/api/demo-events')
    def samples():
        definitions=[('INTRUSION','仓库限制区',0.92,6.0,'合成演示：人员在限制区连续停留6秒。'),
                     ('NO_HELMET','施工区域A',0.90,5.0,'合成演示：专用检测器报告人员未戴安全帽。'),
                     ('INTRUSION','仓库限制区',0.43,1.0,'合成演示：图像模糊且仅出现1秒，证据不足。')]
        return [store.add({'event_type':typ,'zone':zone,'confidence':confidence,'duration':duration,
                           'description':desc,'source':'demo','camera_id':'demo-camera','track_id':i+1,
                           'observations':[{'simulated':True,'duration':duration}]})
                for i,(typ,zone,confidence,duration,desc) in enumerate(definitions)]

    @app.get('/api/events/{eid}')
    def event(eid):
        return event_or_404(eid) | {'audit':store.audits(eid),'command':store.command(eid)}

    @app.post('/api/events/{eid}/analyze')
    async def analyze(eid, request:AnalysisRequest):
        e=event_or_404(eid)
        if not store.claim_analysis(eid): raise HTTPException(409,'Event already analyzed or running')
        try:
            async with model_lock:
                report=await agent.run(e,request.mode)
            store.save_report(eid,report)
        except Exception as exc:
            store.fail(eid,str(exc)[:300])
            logging.exception('Agent failed for event %s',eid)
            raise HTTPException(503,'分析失败，请检查模型服务/模型名称。不会静默切换为演示模式。') from exc
        return event(eid)

    @app.post('/api/events/{eid}/approve')
    async def approve(eid, request:ApprovalRequest, authorization:str=Header(default='')):
        if not secrets.compare_digest(authorization,'Bearer '+settings.approval_token):
            raise HTTPException(403,'Approval token required; find it in the server terminal')
        event_or_404(eid)
        existing=store.command(eid)
        if existing: return {'event':store.get(eid),'command':existing,'idempotent':True}
        if not store.approve(eid,request.reviewer.strip() or 'reviewer',request.approve):
            existing=store.command(eid)
            if existing: return {'event':store.get(eid),'command':existing,'idempotent':True}
            raise HTTPException(409,'Event is not awaiting approval')
        if request.approve:
            cmd=store.command(eid)['payload']
            try: result=await asyncio.to_thread(dispatch,settings,cmd)
            except Exception as exc:
                result={'status':'delivery_unknown','command_id':cmd['command_id'],'detail':str(exc)[:300]}
            store.complete_command(eid,result)
        return {'event':store.get(eid),'command':store.command(eid),'idempotent':False}

    @app.get('/api/events/{eid}/report')
    def report(eid):
        e=event(eid)
        if not e['report']: raise HTTPException(409,'Analyze the event first')
        return e

    @app.get('/api/events/{eid}/snapshot')
    def snapshot(eid):
        e=event_or_404(eid)
        if not e.get('snapshot'): raise HTTPException(404,'No snapshot')
        return FileResponse(settings.data_dir/'snapshots'/e['snapshot'])

    @app.post('/api/videos')
    async def video(file:UploadFile=File(...), polygon:str=Form('[[0.2,0.2],[0.8,0.2],[0.8,0.95],[0.2,0.95]]')):
        try:
            points=json.loads(polygon)
            if not isinstance(points,list) or not 3<=len(points)<=12: raise ValueError()
            for p in points:
                if len(p)!=2 or any(not isinstance(v,(int,float)) or not 0<=v<=1 for v in p): raise ValueError()
        except (ValueError,TypeError): raise HTTPException(422,'Polygon requires 3-12 normalized [x,y] points')
        directory=settings.data_dir/'uploads'; directory.mkdir(exist_ok=True)
        path=directory/(uuid.uuid4().hex+'.mp4'); size=0
        try:
            with path.open('wb') as output:
                while chunk:=await file.read(1024*1024):
                    size+=len(chunk)
                    if size>100*1024*1024: raise HTTPException(413,'Video limit is 100 MiB')
                    output.write(chunk)
            async with model_lock:
                return await asyncio.to_thread(analyze_video,path,settings,store,points)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        finally:
            await file.close()
            path.unlink(missing_ok=True)

    @app.get('/api/knowledge')
    def docs(): return knowledge.docs

    dist=ROOT/'frontend'/'dist'
    if (dist/'assets').exists(): app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/')
    def home():
        if not (dist/'index.html').exists(): raise HTTPException(503,'Build frontend first: npm run build')
        return FileResponse(dist/'index.html')
    return app

app=create_app()

