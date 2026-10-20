import {build} from 'esbuild';
import {readFile,writeFile} from 'node:fs/promises';
const output=await build({entryPoints:[new URL('./app.js',import.meta.url).pathname],bundle:true,write:false,format:'iife',minify:true,target:'es2022'});
const template=await readFile(new URL('./report.template.html',import.meta.url),'utf8');
const js=output.outputFiles[0].text.replaceAll('</script','<\\/script');
await writeFile(new URL('../src/title_trend/ui/report.html',import.meta.url),template.replace('/* APP_BUNDLE */',()=>js));
console.log('Built self-contained MCP Apps resource (no external script/network dependency).');
