import test from 'node:test';
import assert from 'node:assert/strict';
import { appearance, widgetTitle } from '../frontend/model.js';
import { createServer } from 'vite';
import { createSSRApp } from 'vue';
import { renderToString } from 'vue/server-renderer';
const data={system:{value:{ready:true,count:42},error:null}};
const match={source:'system',path:'ready',operator:'eq',value:true,target:'visible',visible:false};

test('one condition applies multiple actions in order and recovers base values',()=>{
  const widget={kind:'text',title:'Original',text:'Original content',textColor:'#ffffff',rules:[
    {...match,actions:[{target:'text',text:'Ready'},{target:'title',text:'Status'},{target:'textColor',color:'#00ff00'},{target:'visible',visible:false}]},
    {...match,actions:[{target:'visible',visible:true},{target:'text',text:''}]},
  ]};
  const original=structuredClone(widget);
  assert.deepEqual(appearance(widget,data),{textColor:'#00ff00',backgroundColor:undefined,iconColor:undefined,visible:true,text:'',title:'Status'});
  assert.equal(widgetTitle(widget,data),'Status');
  assert.equal(widgetTitle({...widget,showTitle:false},data),'');
  for(const values of [{},{system:{value:{ready:false},error:null}},{system:{value:{ready:true},error:'offline'}}]){
    assert.equal(appearance(widget,values).text,undefined);
    assert.equal(appearance(widget,values).textColor,'#ffffff');
    assert.equal(widgetTitle(widget,values),'Original');
  }
  assert.deepEqual(widget,original);
  assert.equal(appearance({rules:[{...match,actions:[{target:'title',text:''}]}]},data).visible,true,'explicit actions replace legacy target');
  assert.equal(appearance({rules:[match]},data).visible,false,'legacy action remains supported');
});

test('text and title actions render safely on widgets and items and preserve title visibility',async()=>{
  const server=await createServer({server:{middlewareMode:true,watch:null,ws:false},optimizeDeps:{noDiscovery:true,entries:[]},appType:'custom'});
  try{
    const {default:Content}=await server.ssrLoadModule('/frontend/WidgetContent.vue');
    const {default:Editor}=await server.ssrLoadModule('/frontend/RuleActionsEditor.vue');
    const {ruleActions}=await server.ssrLoadModule('/frontend/conditions.ts');
    const legacy={...match,target:'textColor',color:'#123456'};
    assert.deepEqual(ruleActions(legacy),[{target:'textColor',color:'#123456'}]); assert.equal(legacy.actions,undefined);
    const base={id:'sample',kind:'value',title:'Original',text:'Base text',source:'system',path:'count',unit:'%',itemPath:'',rules:[{...match,actions:[{target:'text',text:'<script>ready</script>'},{target:'title',text:'Changed'}]}]};
    const render=(widget,values=data)=>renderToString(createSSRApp(Content,{widget,data:values,now:new Date()}));
    for(const kind of ['text','value']){
      const html=await render({...base,kind});
      assert.ok(html.includes('&lt;script&gt;ready&lt;/script&gt;')); assert.ok(!html.includes('<script>'));
      assert.ok(html.includes('Changed')); assert.ok(!html.includes('<small>'));
    }
    const restored=await render(base,{system:{value:{ready:false,count:42}}});
    assert.ok(restored.includes('<span>42</span><small>%</small>'));
    const empty=await render({...base,rules:[{...match,actions:[{target:'text',text:''},{target:'title',text:''}]}]});
    assert.ok(empty.includes('<span></span>')); assert.ok(!empty.includes('<h2'));
    const hidden=await render({...base,showTitle:false}); assert.ok(!hidden.includes('<h2'));
    const layout={kind:'layout',title:'Parent',columns:[1],rows:[1],gap:0,rules:[{...match,actions:[{target:'title',text:'New parent'}]}],items:[{...base,row:0,column:0,rowSpan:1,columnSpan:1}]};
    const nested=await render(layout); assert.ok(nested.includes('New parent')); assert.ok(nested.includes('Changed'));
    const markup=await renderToString(createSSRApp(Editor,{rule:legacy,kind:'text'}));
    assert.ok(markup.includes('Replacement text')); assert.match(markup, /disabled[^>]*aria-label="Remove action"/);
    assert.equal(legacy.actions,undefined);
  }finally{await server.close();}
});
