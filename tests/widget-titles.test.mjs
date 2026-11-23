import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { createSSRApp } from 'vue';
import { renderToString } from 'vue/server-renderer';

test('widget titles require nonblank text and enabled visibility for every content type', async () => {
  const server = await createServer({server:{middlewareMode:true,watch:null,ws:false},optimizeDeps:{noDiscovery:true,entries:[]},appType:'custom'});
  try {
    const {default:Content} = await server.ssrLoadModule('/frontend/WidgetContent.vue');
    const base = {id:'widget',kind:'text',title:'',text:'Content stays visible',source:'system',path:'load1',itemPath:'',unit:'',icon:'user',rules:[],columns:[1],rows:[1],gap:0,items:[]};
    const render = widget => renderToString(createSSRApp(Content,{widget,data:{system:{value:{load1:0}}},now:new Date('2026-11-23T12:00:00Z')}));
    for (const kind of ['text','value','list','clock','icon','layout']) {
      for (const [title,showTitle,visible] of [['',undefined,false],['   ',true,false],['Custom title',false,false],['Custom title',true,true],['Custom title',undefined,true]]) {
        const html = await render({...base,kind,title,showTitle});
        assert.equal(html.includes('<h2'),visible,`${kind}: title=${JSON.stringify(title)}, showTitle=${showTitle}`);
        if (visible) assert.ok(html.includes('Custom title'));
        if (kind==='text') assert.ok(html.includes(base.text));
      }
    }
    const layout = {...base,kind:'layout',title:'Hidden parent',showTitle:false,items:[{...base,id:'child',title:'Visible child',showTitle:true,row:0,column:0,rowSpan:1,columnSpan:1}]};
    assert.match(await render(layout), /Visible child/);
    assert.ok(!(await render(layout)).includes('Hidden parent'));
    layout.items[0].showTitle=false;
    assert.ok(!(await render(layout)).includes('<h2'));
    layout.items[0].showTitle=true;
    assert.match(await render(layout), /Visible child/);
    const hostile = await render({...base,title:'<script>alert(1)</script>'});
    assert.ok(hostile.includes('&lt;script&gt;'));
    assert.ok(!hostile.includes('<script>'));
  } finally { await server.close(); }
});
