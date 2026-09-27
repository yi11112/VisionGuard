import React, {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

type RecordData = Record<string,any>;
const labels: Record<string,string>={new:'待研判',analyzing:'研判中',awaiting_approval:'待人工批准',needs_review:'证据不足',dismissed:'排除告警',mock_executed:'模拟设备已执行',device_acknowledged:'收到设备确认',delivery_unknown:'执行结果未知',rejected:'审批已拒绝',error:'分析失败',dispatching:'指令发送中'};
const types:Record<string,string>={INTRUSION:'限制区域闯入',NO_HELMET:'未佩戴安全帽'};
async function api(path:string,options:RequestInit={}) {
 const response=await fetch('/api'+path,options);
 const data=await response.json();
 if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
 return data;
}
const post=(data:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});

function App(){
 const [health,setHealth]=useState<RecordData>({}); const [events,setEvents]=useState<RecordData[]>([]);
 const [selected,setSelected]=useState<string>(''); const [detail,setDetail]=useState<RecordData|null>(null);
 const [mode,setMode]=useState('demo'); const [busy,setBusy]=useState(''); const [error,setError]=useState('');
 const [tab,setTab]=useState('evidence'); const [token,setToken]=useState(''); const [reviewer,setReviewer]=useState('值班员');
 const [polygon,setPolygon]=useState('[[0.2,0.2],[0.8,0.2],[0.8,0.95],[0.2,0.95]]');
 const [searchQuery,setSearchQuery]=useState(''); const [searchInfo,setSearchInfo]=useState('');
 const refresh=async()=>{const list=await api('/events');setEvents(list);return list;};
 useEffect(()=>{Promise.all([refresh(),api('/health').then(setHealth)]).catch(e=>setError(e.message));},[]);
 useEffect(()=>{if(!selected){setDetail(null);return;} let active=true;
  const load=()=>api('/events/'+selected).then(d=>{if(active)setDetail(d);}).catch(e=>{if(active)setError(e.message);});
  load();const timer=setInterval(load,2500);return()=>{active=false;clearInterval(timer);};
 },[selected]);
 const action=async(name:string,fn:()=>Promise<void>)=>{setBusy(name);setError('');try{await fn();await refresh();if(selected)setDetail(await api('/events/'+selected));}catch(e){setError((e as Error).message);}finally{setBusy('');}};
 const seed=()=>action('生成演示事件',async()=>{const list=await api('/demo-events',{method:'POST'});setSelected(list[0].id);});
 const analyze=()=>action('Agent 正在收集证据',async()=>{if(detail)setDetail(await api('/events/'+detail.id+'/analyze',post({mode})));});
 const approve=(allow:boolean)=>action('提交审批',async()=>{await api('/events/'+selected+'/approve',{...post({approve:allow,reviewer}),headers:{'Content-Type':'application/json','Authorization':'Bearer '+token}});setToken('');});
 const upload=(file:File)=>action('检测视频，最长处理前120秒',async()=>{const data=new FormData();data.append('file',file);data.append('polygon',polygon);const r=await api('/videos',{method:'POST',body:data});if(r.events.length)setSelected(r.events[0].id);else setError('视频处理完成，未发现持续3秒的禁区闯入。可以调整区域或更换视频。');});
 const exportReport=async()=>{const r=await api('/events/'+selected+'/report');const url=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='visionguard-'+selected.slice(0,8)+'.json';a.click();URL.revokeObjectURL(url);};
 const report=detail?.report;
 const search=async()=>{setBusy('解析查询条件');setError('');try{const r=await api('/search',post({query:searchQuery}));setEvents(r.events);setSearchInfo(JSON.stringify(r.filters));if(r.events.length)setSelected(r.events[0].id);}catch(e){setError((e as Error).message);}finally{setBusy('');}};
 return <div className="layout">
  <aside><div className="brand"><span className="brand-icon">V</span><div>VisionGuard<small>园区事件研判工作台</small></div></div><div className="nav-label">WORKSPACE</div><div className="nav active">◈　事件中心</div><a className="nav" href="/docs" target="_blank" rel="noreferrer">⌘　API 文档 ↗</a><div className="aside-note"><span className="live-dot"/> 本地演示环境<p>感知 → 取证 → 研判 → 审批</p><small>所有制度为项目自拟示例。<br/>设备默认模拟，不操作真实门禁。</small></div></aside>
  <main><header><div><p className="eyebrow">VISION + AGENT / INCIDENT OPERATIONS</p><h1>让每一次处置，都有据可查。</h1><p className="subtitle">从视频告警到人工批准，查看智能体实际调用的工具与证据。</p></div><div className="health"><span className={health.ollama?'live-dot':'off-dot'}/>{health.ollama?'模型服务在线':'模型服务未连接'}<small>{health.models?.length?health.models.join(' · '):'演示模式可离线运行'}</small></div></header>
  <section className="stats">{[['事件总数',events.length],['待审批',events.filter(e=>e.status==='awaiting_approval').length],['待复核',events.filter(e=>e.status==='needs_review').length],['设备模式',health.device_mode==='mqtt'?'MQTT':'模拟设备']].map(([label,value])=><div className="stat" key={String(label)}><span>{label}</span><strong>{value}</strong></div>)}</section>
  <section className="toolbar"><div><strong>事件收件箱</strong><span>　视频事件与合成演示分开标记</span></div><button className="primary" disabled={!!busy} onClick={seed}>＋ 生成演示事件</button></section>
  <section className="search"><input aria-label="自然语言检索" placeholder="例如：找出待审批、持续3秒以上的闯入事件" value={searchQuery} onChange={e=>setSearchQuery(e.target.value)}/><button disabled={!!busy||!searchQuery.trim()} onClick={search}>语义检索</button><button onClick={()=>{setSearchInfo('');refresh().catch(e=>setError(e.message));}}>重置</button><small>支持类型、状态、持续时间；最近200条。{searchInfo&&' 已解析：'+searchInfo}</small></section>
  {error&&<div role="alert" className="error">{error}<button onClick={()=>setError('')}>关闭</button></div>}
  {busy&&<div role="status" className="progress"><span className="spinner"/>{busy}…</div>}
  <div className="workspace"><section className="inbox">{!events.length?<div className="empty"><div>◈</div><h3>等待第一个事件</h3><p>生成三个演示事件，或上传一段<br/>包含人员走动的视频开始。</p><button onClick={seed} disabled={!!busy}>开始演示</button></div>:events.map(e=><button className={'event-card '+(selected===e.id?'selected':'')} key={e.id} onClick={()=>{setSelected(e.id);setTab('evidence');}}><div className="row"><span className={'status '+e.status}>{labels[e.status]||e.status}</span><small>{e.source==='demo'?'合成演示':'真实视频输入'}</small></div><h3>{types[e.event_type]||e.event_type}</h3><p>{e.zone} · {e.duration}s</p><small>{new Date(e.created).toLocaleString('zh-CN')}</small></button>)}</section>
  <section className="detail">{!detail?<div className="empty"><div>↖</div><h3>选择一个事件</h3><p>查看证据、工具执行记录与审批结果。</p></div>:<><div className="detail-head"><div><p className="eyebrow">EVENT / {detail.id.slice(0,8)}</p><h2>{types[detail.event_type]}</h2></div><span className={'status '+detail.status}>{labels[detail.status]||detail.status}</span></div>
   <div className="facts"><div>区域<strong>{detail.zone}</strong></div><div>持续时间<strong>{detail.duration} 秒</strong></div><div>检测器置信度<strong>{(detail.confidence*100).toFixed(0)}%</strong></div></div>
   <p className="description">{detail.description}</p>
   {detail.snapshot&&<img className="snapshot" src={'/api/events/'+detail.id+'/snapshot'} alt="事件关键帧：绿色为目标，红色为限制区域"/>}
   {['new','error'].includes(detail.status)&&<div className="analyze"><select aria-label="研判模式" value={mode} onChange={e=>setMode(e.target.value)}><option value="demo">演示模式 · 固定规则流程</option><option value="local">真实 Agent · 本地 Qwen 工具调用</option></select><button className="primary" onClick={analyze} disabled={!!busy}>开始研判 →</button><small>演示模式不调用大模型；真实模式失败会直接报错。</small></div>}
   {report&&<><div className="summary"><div className="row"><strong>研判结论</strong><small>{report.mode==='local'?'本地模型 '+report.model:'规则演示 · 无LLM参与'}</small></div><p>{report.summary}</p><small>风险由规则约束，模型不持有设备执行权限。</small></div><div className="tabs">{[['evidence','制度与证据'],['trace','工具调用'],['audit','审计记录']].map(([id,label])=><button className={tab===id?'on':''} key={id} onClick={()=>setTab(id)}>{label}</button>)}</div>
    {tab==='evidence'&&<div>{report.citations.length?report.citations.map((c:RecordData)=><article className="citation" key={c.id}><small>{c.id} · v{c.version}</small><h4>{c.title}</h4><p>{c.text}</p><small>{c.source}</small></article>):<p>未检索到适用条款，需人工复核。</p>}</div>}
    {tab==='trace'&&<div className="timeline">{report.trace.map((t:RecordData,i:number)=><article key={i}><div className="row"><strong>{i+1}. {t.tool}</strong><span>{t.elapsed_ms} ms · {t.status}</span></div><small>选择者：{t.selected_by==='local_llm'?'语言模型':'演示规则'}</small><details><summary>参数和工具结果</summary><pre>{JSON.stringify({arguments:t.arguments,result:t.result},null,2)}</pre></details></article>)}</div>}
    {tab==='audit'&&<div className="timeline">{detail.audit?.map((a:RecordData)=><article key={a.id}><strong>{a.action}</strong><small>　{new Date(a.created).toLocaleTimeString()}</small><details><summary>记录详情</summary><pre>{JSON.stringify(a.payload,null,2)}</pre></details></article>)}</div>}
    {detail.status==='awaiting_approval'&&<section className="approval"><h3>等待人工批准</h3><p>建议：开启 alarm-light-01 警灯30秒。当前设备模式：{health.device_mode}。</p><div className="approval-inputs"><input aria-label="审批人" placeholder="审批人" value={reviewer} onChange={e=>setReviewer(e.target.value)}/><input aria-label="审批令牌" placeholder="输入服务端终端显示的审批令牌" type="password" value={token} onChange={e=>setToken(e.target.value)}/></div><button className="primary" disabled={!!busy||!token} onClick={()=>approve(true)}>批准并执行</button><button disabled={!!busy||!token} onClick={()=>approve(false)}>拒绝</button></section>}
    {detail.command&&<div className="command"><strong>设备结果：{detail.command.status}</strong><p>{typeof detail.command.result?.detail==='string'?detail.command.result.detail:JSON.stringify(detail.command.result?.detail)}</p><small>指令ID：{detail.command.id} · 同一事件重复审批不会重复发送。</small></div>}
    <button className="export" onClick={()=>exportReport().catch(e=>setError(e.message))}>↓ 导出完整证据报告 JSON</button>
   </>}
  </>}</section></div>
  <section className="upload"><div><p className="eyebrow">VIDEO INGEST</p><h2>用自己的视频验证感知链路</h2><p>本地 YOLO11n + ByteTrack，检测人员在指定区域持续停留3秒。处理视频前120秒，文件最大100MiB。</p><small>仅人员禁区检测。默认权重不识别安全帽。区域坐标使用0～1归一化值。</small></div><div><label>限制区域多边形<input aria-label="限制区域多边形" value={polygon} onChange={e=>setPolygon(e.target.value)}/></label><label className="file-button">选择视频并检测<input type="file" accept="video/*" disabled={!!busy} onChange={e=>{const f=e.target.files?.[0];if(f)upload(f);e.target.value='';}}/></label></div></section>
  <footer>VisionGuard · 个人工程项目　/　可审计工具调用 · 人工审批 · 本地优先</footer>
 </main></div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
