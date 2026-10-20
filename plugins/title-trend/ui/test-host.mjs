import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium} from 'playwright';
const proc=spawn(process.execPath,[new URL('./host.mjs',import.meta.url).pathname],{env:{...process.env,TITLE_TREND_HOST_PORT:'4178'},stdio:['ignore','pipe','pipe']});
let browser;
try{
  await new Promise((resolve,reject)=>{proc.stdout.on('data',b=>{if(b.toString().includes('http://'))resolve();});proc.on('exit',c=>reject(new Error(`Host exited ${c}`)));setTimeout(()=>reject(new Error('Host startup timeout')),30000).unref();});
  browser=await chromium.launch({headless:true,executablePath:process.env.TITLE_TREND_CHROME || (existsSync('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')?'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome':undefined)});
  const page=await browser.newPage({viewport:{width:1000,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:4178/');
  await page.waitForFunction(()=>window.titleTrendHostReady===true);
  const frame=page.frameLocator('#app');
  async function capture(filename){
    // Paint the whole opaque iframe, including report content below the original viewport.
    await frame.locator('#footer').waitFor({state:'visible'});
    const cardHeight=await frame.locator('body').evaluate(el=>el.scrollHeight);
    await page.locator('#app').evaluate((el,h)=>{el.style.height=`${h+2}px`;},cardHeight);
    await page.setViewportSize({width:page.viewportSize().width,height:Math.ceil(cardHeight+180)});
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    await page.screenshot({path:new URL(filename,out).pathname,fullPage:true});
  }
  await frame.locator('#report').waitFor({state:'visible'});
  assert.match(await frame.locator('#demo').textContent(),/模拟/);
  assert.equal(await frame.locator('.keyword').count(),3);
  assert.equal(await frame.locator('.recommendation').count(),2);
  assert.ok(Number((await frame.locator('#score').textContent()).split('/')[0].trim())>0);
  const out=new URL('../artifacts/',import.meta.url);await mkdir(out,{recursive:true});
  await capture('host-light.png');
  await page.click('#theme');
  await page.waitForFunction(()=>document.querySelector('#app') && true);
  assert.equal(await frame.locator('html').getAttribute('data-theme'),'dark');
  await page.setViewportSize({width:375,height:900});
  await capture('host-dark-narrow.png');
  const overflow=await frame.locator('body').evaluate(el=>el.scrollWidth>el.clientWidth);
  assert.equal(overflow,false,'Narrow card must not overflow horizontally');
  await page.evaluate(()=>window.bridge.sendToolResult(window.session.analysis));
  await frame.locator('#advice-status').waitFor({state:'visible'});
  assert.equal(await frame.locator('#titles-section').isVisible(),false);
  assert.ok(Number((await frame.locator('#score').textContent()).split('/')[0].trim())>0);
  await page.click('#restore');
  await frame.locator('#titles-section').waitFor({state:'visible'});
  await page.click('#missing');
  await frame.locator('#score').filter({hasText:'数据不足，暂不评分'}).waitFor();
  await capture('host-missing.png');
  // Untrusted text cannot create DOM elements/scripts.
  await page.evaluate(async()=>{const data=structuredClone(window.session.result);data.structuredContent.advice.analysis='<img src=x onerror="window.pwned=1">';await window.bridge.sendToolResult(data);});
  await frame.locator('#analysis').filter({hasText:'<img'}).waitFor();
  assert.equal(await frame.locator('#analysis img').count(),0);
  await page.evaluate(()=>window.bridge.sendToolResult({isError:true,content:[{type:'text',text:'模拟请求失败'}]}));
  await frame.locator('#state').filter({hasText:'模拟请求失败'}).waitFor({state:'visible'});
  assert.equal(await frame.locator('#report').isVisible(),false,'Errors must hide any previous score');
  assert.deepEqual(errors,[]);
  await writeFile(new URL('host-validation.json',out),JSON.stringify({verified:true,simulated:true,host:'Official ext-apps AppBridge SDK local test host',transport:'Python stdio MCP + iframe postMessage',checks:['prepare → query → complete','awaiting Agent advice','ui/initialize','tool input/result','resource MIME/metadata','light','dark','375px no overflow','null score','untrusted text escaping','failed result hides previous score'],pageErrors:errors},null,2));
  console.log('MCP Apps SDK宿主联调通过（模拟数据）；明暗/375px/缺失状态/文本注入通过。');
}finally{if(browser)await browser.close();proc.kill('SIGTERM');}
