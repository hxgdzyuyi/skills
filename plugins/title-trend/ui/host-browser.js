import {AppBridge,PostMessageTransport} from '@modelcontextprotocol/ext-apps/app-bridge';
(async()=>{
const session=await fetch('/session').then(r=>r.json());
const iframe=document.getElementById('app');
const bridge=new AppBridge(null,{name:'Title Trend Local Apps Host',version:'0.2.0'},{});
let theme='light';
bridge.onsizechange=({height})=>{if(height)iframe.style.height=`${height}px`;};
bridge.oninitialized=async()=>{
  document.getElementById('status').textContent='标准 ui/initialize 完成 · prepare_title → analyze_title → complete_report 经 Python stdio MCP 完成（模拟 Agent 建议）';
  await bridge.sendToolInput({arguments:session.toolArgs});
  await bridge.sendToolResult(session.result);
  window.titleTrendHostReady=true;
};
window.bridge=bridge;window.session=session;
await bridge.connect(new PostMessageTransport(iframe.contentWindow,iframe.contentWindow));
bridge.setHostContext({theme,displayMode:'inline',availableDisplayModes:['inline'],locale:'zh-CN',platform:'web'});
// An opaque-origin sandbox, no network or private application APIs.
const csp="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src data:; base-uri 'none'; form-action 'none'";
iframe.srcdoc=session.resource.text.replace('<head>',`<head><meta http-equiv="Content-Security-Policy" content="${csp}">`);
document.getElementById('theme').onclick=()=>{theme=theme==='light'?'dark':'light';bridge.setHostContext({theme,displayMode:'inline'});};
document.getElementById('restore').onclick=()=>bridge.sendToolResult(session.result);
document.getElementById('missing').onclick=()=>{
  const missing=structuredClone(session.result);const report=missing.structuredContent;
  report.metrics={score:null,demand:null,trend:null,growth:null};
  report.coverage.scorable=0;
  report.advice.analysis='模拟缺失样例：API未返回足够数据，无法判断搜索需求或趋势。编辑建议仅围绕原标题表达。';
  for(const r of report.keywords){r.data.status='no_data';r.data.reason='UI边界模拟：API未返回数据';r.metrics={score:null,demand:null,trend:null,growth:null,recent_monthly_volume:null,growth_pct:null};}
  report.warnings=['模拟缺失状态，仅验证 UI；并非真实 API 查询结果'];bridge.sendToolResult(missing);
};

})().catch(()=>{document.getElementById("status").textContent="宿主联调失败"});
