// Local, simulation-only MCP Apps test host. A real SDK stdio client reads the resource
// and invokes the Python tool. The browser AppBridge then negotiates ui/initialize.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {build} from 'esbuild';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
const root=fileURLToPath(new URL('../',import.meta.url));
const command=process.env.TITLE_TREND_PYTHON || resolve(root,'.venv/bin/python');
const client=new Client({name:'Title Trend Local Apps Host',version:'0.2.0'},{capabilities:{extensions:{'io.modelcontextprotocol/ui':{mimeTypes:['text/html;profile=mcp-app']}}}});
const transport=new StdioClientTransport({command,args:['-m','title_trend.cli','serve','--demo'],cwd:root,stderr:'pipe'});
await client.connect(transport);
const tools=await client.listTools();
const tool=tools.tools.find(t=>t.name==='complete_report');
const resourceUri=tool._meta.ui.resourceUri;
const resource=await client.readResource({uri:resourceUri});
const title='用 Python 自动化办公，如何减少重复工作？';
const prepared=await client.callTool({name:'prepare_title',arguments:{title}});
// Fixture stands in for host Agent output. No external model API is invoked.
const selection={topic:'Python自动化办公',candidates:[
  {keyword:'Python 自动化办公',anchors:['Python','自动化'],relevance:'原标题工具与用途'},
  {keyword:'Python 办公',anchors:['Python','办公'],relevance:'原词组合'},
  {keyword:'自动化办公',anchors:['自动化'],relevance:'原文场景'}
]};
const analysis=await client.callTool({name:'analyze_title',arguments:{title,selection,market:'CN'}});
const toolArgs={report_id:analysis.structuredContent.report_id,advice:{
  analysis:'模拟样本中，近期搜索水平高于历史基线。编辑判断：突出原标题工具和用途，便于读者理解。',
  keyword_suggestions:['保留 Python 与自动化办公主题，避免堆叠泛化热词。'],
  recommended_titles:[
    {title:'Python 自动化办公：如何减少重复工作？',direction:'明确工具与用途'},
    {title:'减少重复工作，如何用 Python 自动化办公？',direction:'问题前置，保留原标题事实'}
  ]
}};
const result=await client.callTool({name:tool.name,arguments:toolArgs});
if(prepared.isError || analysis.isError || result.isError)throw new Error('Simulation workflow failed');
const bundle=await build({entryPoints:[fileURLToPath(new URL('./host-browser.js',import.meta.url))],bundle:true,write:false,format:'iife',target:'es2022'});
const page=await readFile(new URL('./host.html',import.meta.url),'utf8');
const server=http.createServer((req,res)=>{
  if(req.headers.host!==`127.0.0.1:${server.address().port}`){res.writeHead(403);res.end();return;}
  if(req.url==='/session'){
    res.setHeader('Content-Type','application/json');
    res.end(JSON.stringify({tool,toolArgs,resource:resource.contents[0],result,analysis}));
  }else if(req.url==='/host.js'){
    res.setHeader('Content-Type','text/javascript');res.end(bundle.outputFiles[0].text);
  }else if(req.url==='/'){
    res.setHeader('Content-Type','text/html; charset=utf-8');res.end(page);
  }else {res.writeHead(404);res.end();}
});
server.listen(Number(process.env.TITLE_TREND_HOST_PORT||4177),'127.0.0.1',()=>console.log(`MCP Apps 模拟宿主 http://127.0.0.1:${server.address().port}`));
async function close(){server.close();await client.close();process.exit(0);}
process.on('SIGTERM',close);process.on('SIGINT',close);
