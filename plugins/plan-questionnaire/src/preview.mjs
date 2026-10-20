import { createServer } from "node:http";
import { randomBytes } from "node:crypto";
import { publicRecord, answerSummary } from "./store.mjs";

export async function startPreview(store, current, widgetHtml) {
  const csrf = randomBytes(24).toString("hex");
  const result = record => ({
    content: [], structuredContent: { questionnaire: publicRecord(record), answer_summary: answerSummary(record) },
    _meta: { submission_token: record.submission_token },
  });
  const server = createServer(async (req, res) => {
    const origin = `http://127.0.0.1:${server.address().port}`;
    const headers = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
    const send = (code, type, body) => res.writeHead(code, { ...headers, "Content-Type": type }).end(body);
    if (req.headers.host !== new URL(origin).host) return send(403, "text/plain", "Invalid host");
    if (req.method === "GET" && req.url === "/widget") return send(200, "text/html; charset=utf-8", widgetHtml);
    if (req.method === "GET" && req.url === "/") {
      return send(200, "text/html; charset=utf-8", `<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>方案讨论问卷 · 本地预览</title>
<style>body{font:14px system-ui;background:#eef1eb;margin:0;padding:24px;color:#374134}main{max-width:800px;margin:auto}p{font-size:13px;color:#64705d}iframe{border:1px solid #dfe5d8;border-radius:18px;width:100%;min-height:800px;background:white}pre{white-space:pre-wrap;background:white;padding:20px;border-radius:12px}</style>
<main><p>本地预览 · 答案保存在本机；此预览页不会自动发送聊天消息。</p><iframe title="讨论问卷" src="/widget"></iframe><pre id="reply" hidden></pre></main>
<script>
const frame=document.querySelector('iframe');
const current=${JSON.stringify(result(store.get(current.id))).replaceAll("<", "\\u003c")};
addEventListener('message',async e=>{
 if(e.source!==frame.contentWindow||e.origin!==location.origin)return;
 const m=e.data;if(!m||m.jsonrpc!=='2.0')return;
 const reply=r=>frame.contentWindow.postMessage({jsonrpc:'2.0',id:m.id,result:r},location.origin);
 if(m.method==='ui/initialize')return reply({protocolVersion:'2026-01-26',hostInfo:{name:'local-preview',version:'1.0.0'},hostCapabilities:{serverTools:{},message:{text:{}}},hostContext:{theme:'light',displayMode:'inline',availableDisplayModes:['inline'],platform:'web'}});
 if(m.method==='ui/notifications/initialized')return frame.contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:current},location.origin);
 if(m.method==='ui/notifications/size-changed'){if(m.params?.height)frame.style.height=m.params.height+'px';return;}
 if(m.method==='tools/call'){
   try{const r=await fetch('/api/tool',{method:'POST',headers:{'Content-Type':'application/json','X-Questionnaire-CSRF':${JSON.stringify(csrf)}},body:JSON.stringify(m.params)});return reply(await r.json());}
   catch{return reply({isError:true,content:[{type:'text',text:'本地服务连接失败'}]});}
 }
 if(m.method==='ui/message'){const p=document.querySelector('#reply');p.hidden=false;p.textContent=m.params.content.map(x=>x.text||'').join('\\n');return reply({isError:true});}
 if(m.method==='ui/update-model-context')return reply({});
 if(m.id!==undefined)frame.contentWindow.postMessage({jsonrpc:'2.0',id:m.id,error:{code:-32601,message:'Unsupported method'}},location.origin);
});
</script></html>`);
    }
    if (req.method === "POST" && req.url === "/api/tool") {
      if (req.headers.origin !== origin || req.headers["x-questionnaire-csrf"] !== csrf)
        return send(403, "application/json", JSON.stringify({ isError: true, content: [{ type: "text", text: "Invalid origin" }] }));
      try {
        let body = "";
        for await (const chunk of req) {
          body += chunk;
          if (body.length > 262144) throw new Error("请求过大");
        }
        const { name, arguments: args } = JSON.parse(body);
        let record;
        if (name === "get_questionnaire" && args.questionnaire_id === current.id) record = store.get(current.id);
        else if (name === "submit_questionnaire" && args.questionnaire_id === current.id) record = store.submit(args);
        else throw new Error("预览只允许读取或提交当前问卷");
        return send(200, "application/json", JSON.stringify(result(record)));
      } catch (e) {
        return send(400, "application/json", JSON.stringify({ isError: true, content: [{ type: "text", text: e.message }] }));
      }
    }
    send(404, "text/plain", "Not found");
  });
  await new Promise(resolve => server.listen(Number(process.env.PLAN_QUESTIONNAIRE_PORT ?? 0), "127.0.0.1", resolve));
  console.error(`Questionnaire preview: http://127.0.0.1:${server.address().port}/`);
  return server;
}
