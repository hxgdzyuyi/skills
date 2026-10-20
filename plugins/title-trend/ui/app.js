import { App } from '@modelcontextprotocol/ext-apps';
const $ = id => document.getElementById(id);
const fmt = (v, suffix='') => typeof v === 'number' && Number.isFinite(v) ? `${new Intl.NumberFormat('zh-CN',{maximumFractionDigits:2}).format(v)}${suffix}` : '—';
const node = (tag, text='', cls='') => {const el=document.createElement(tag); el.textContent=text; if(cls)el.className=cls; return el;};
const at = value => value ? new Date(value).toLocaleString('zh-CN',{hour12:false}) : '未知';
const labels={ok:'有数据',zero:'真实零值',no_data:'无数据',unsupported:'不支持',request_failed:'请求失败',stale:'过期缓存'};
function render(r){
  if(!r || !Array.isArray(r.keywords) || !r.market){ $('state').hidden=false; $('report').hidden=true; $('state').textContent='分析结果缺失或无效。'; return; }
  $('state').hidden=true; $('report').hidden=false;
  $('title').textContent=r.title; $('demo').style.display=r.simulated?'block':'none';
  $('score').replaceChildren();
  if(r.metrics.score===null){$('score').className='score empty'; $('score').textContent='数据不足，暂不评分';}
  else {$('score').className='score'; $('score').append(node('span',fmt(r.metrics.score)),node('small',' / 100'));}
  $('coverage').textContent=`覆盖 ${r.coverage.scorable??0} / ${r.coverage.selected??0} 个关键词`;
  $('metrics').replaceChildren();
  for(const [key,label] of [['trend','趋势热度'],['growth','增长'],['demand','搜索需求']]){
    const m=node('div','', 'metric'); m.append(node('span',label,'muted'),node('b',fmt(r.metrics[key])));
    const bar=node('div','','meter'),fill=node('span'); fill.style.width=`${Math.max(0,Math.min(100,r.metrics[key]??0))}%`; bar.append(fill);m.append(bar);$('metrics').append(m);
  }
  $('source').replaceChildren(...[r.simulated?'模拟数据':'DataForSEO',r.market.engine,`${r.market.name} · ${r.market.language_code}`,'月度 · 四类设备'].map(t=>node('span',t,'pill')));
  $('keywords').replaceChildren();
  for(const row of r.keywords.slice(0,5)){
    const d=row.data,m=row.metrics,block=node('div','','keyword'),head=node('div','','keyword-head');
    head.append(node('strong',d.keyword),node('span',labels[d.status]??'未知','pill')); block.append(head);
    const values=node('div','','keyword-data');
    for(const [label,value] of [['搜索量（次/月）',fmt(m.recent_monthly_volume)],['趋势热度',fmt(m.trend)],['增长指标',fmt(m.growth)],['搜索量变化',fmt(m.growth_pct,'%')]]){
      const item=node('div');item.append(node('span',label),node('b',value));values.append(item);
    }block.append(values);
    block.append(node('p',`广告竞争：${fmt(d.ad_competition)}${d.ad_competition===null?'（此接口未提供）':''}`,'note'));
    if(d.reason||m.reason)block.append(node('p',d.reason||m.reason,'warning'));
    const detail=node('details');detail.append(node('summary','数据范围与获取时间'));
    detail.append(node('p',`统计 ${r.window_start??'未知'}—${r.window_end??'未知'}；获取 ${at(d.fetched_at)}；缓存${d.cache_hit?'命中':'未命中'}；过期 ${at(d.expires_at)}。`));
    if(d.status==='stale' && d.months?.length){detail.append(node('p',`过期历史末月 ${d.months.at(-1).month}：${fmt(d.months.at(-1).volume,' 次')}，只供查看。`));}
    block.append(detail);$('keywords').append(block);
  }
  if(!r.keywords.length)$('keywords').append(node('p','候选关键词尚未确定，未请求搜索数据。','muted'));
  $('advice-status').hidden=!!r.advice;
  $('advice-section').hidden=!r.advice;
  $('titles-section').hidden=!r.advice;
  if(r.advice){
  $('analysis').textContent=r.advice.analysis;
  $('advice-origin').textContent=`编辑判断 · ${r.advice.origin==='simulation'?'模拟建议':'当前 Agent 基于已校验数据生成'}`;
  $('suggestions').replaceChildren(...r.advice.keyword_suggestions.map(t=>node('li',t)));
  $('titles').replaceChildren(...r.advice.recommended_titles.map(t=>{const div=node('div','','recommendation');div.append(node('b',t.title),node('p',t.direction));return div;}));
  }
  $('warnings').replaceChildren(...r.warnings.map(t=>node('p',t,'warning')));
  $('footer').textContent=`统计范围：${r.window_start??'未知'} 至 ${r.window_end??'未知'}。来源更新：${r.data_updated_at??'未知'}；更新状态获取：${at(r.status_fetched_at)}；报告生成：${at(r.generated_at)}。公式 ${r.formula_version}。${r.disclaimer}`;
}
const preview=$('preview-data');
if(preview){render(JSON.parse(preview.textContent));}
else{
  const app=new App({name:'Title Trend',version:'0.2.0'});
  const theme=ctx=>{if(['light','dark'].includes(ctx?.theme))document.documentElement.dataset.theme=ctx.theme;};
  app.onhostcontextchanged=theme;
  app.ontoolresult=result=>{if(result.isError){$('state').hidden=false;$('report').hidden=true;$('state').textContent=result.content?.find(x=>x.type==='text')?.text??'分析失败';}else render(result.structuredContent);};
  app.ontoolcancelled=()=>{$('state').hidden=false;$('report').hidden=true;$('state').textContent='分析已取消';};
  app.connect().then(()=>theme(app.getHostContext())).catch(()=>{$('state').textContent='需要支持 MCP Apps 的宿主。普通浏览器请使用明确标注的模拟 preview。';});
}
