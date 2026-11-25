import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {createRenderer, ref, nextTick} from 'vue';
import {contentStyle} from '../frontend/model.js';
test('text fitting finds the largest fitting size and can grow again after content shrinks',async()=>{
  const server=await createServer({server:{middlewareMode:true,watch:null,ws:false},optimizeDeps:{noDiscovery:true,entries:[]},appType:'custom'});
  try{
    const {fitTextSize}=await server.ssrLoadModule('/frontend/textFit.ts');
    let calls=0;
    const small=fitTextSize(96,size=>{calls++;return size<=13.5;});
    assert.ok(small<=13.5 && small>13.35);assert.ok(calls<=11);
    assert.equal(fitTextSize(96,size=>size<=100),96);
    assert.equal(fitTextSize(24,size=>size<=100),24);
    const {dataPaths,systemPaths}=await server.ssrLoadModule('/frontend/dataPaths.ts');
    assert.ok(systemPaths.includes('temperatureC'));
    assert.deepEqual(dataPaths({queue:[{count:3}]}),['queue','queue[0]','queue[0].count']);
    assert.deepEqual(dataPaths(JSON.parse('{"__proto__":{"token":1},"safe":2}')),['safe']);
    const cyclic={};cyclic.self=cyclic;assert.ok(dataPaths(cyclic).length<=8);
    assert.ok(dataPaths(Array.from({length:1000},(_,n)=>n)).length<=200);
    for(const [verticalAlign,expected] of [['top','flex-start'],['middle','center'],['bottom','flex-end']]){
      const style=contentStyle({rules:[],verticalAlign,fontWeight:700,italic:true},{});
      assert.equal(style['--widget-vertical-align'],expected);
      assert.equal(style['--widget-font-weight'],700);assert.equal(style['--widget-font-style'],'italic');
    }
  }finally{await server.close();}
});

test('mounted text fits without animation frames and retired callbacks cannot change it',async()=>{
  const server=await createServer({server:{middlewareMode:true,watch:null,ws:false},optimizeDeps:{noDiscovery:true,entries:[]},appType:'custom'});
  const original={ResizeObserver:globalThis.ResizeObserver,MutationObserver:globalThis.MutationObserver,document:globalThis.document,requestAnimationFrame:globalThis.requestAnimationFrame};
  const observers=[],listeners=new Map();let resolveFonts,writes=0,size=16;
  const fontsReady=new Promise(resolve=>{resolveFonts=resolve;});
  const box={clientWidth:100,clientHeight:20};
  const content={style:{setProperty:(name,value)=>{size=parseFloat(value);writes++;}},get scrollHeight(){return size*2;},scrollWidth:80};
  const Observer=class{constructor(callback){this.callback=callback;observers.push(this);}observe(){}disconnect(){this.disconnected=true;}};
  Object.assign(globalThis,{ResizeObserver:Observer,MutationObserver:Observer,requestAnimationFrame:()=>{throw new Error('Off-screen animation frame must not be required');},document:{fonts:{ready:fontsReady,addEventListener:(name,callback)=>listeners.set(name,callback),removeEventListener:name=>listeners.delete(name)}}});
  let app;
  try{
    const {useTextFit}=await server.ssrLoadModule('/frontend/textFit.ts');
    const renderer=createRenderer({createComment:()=>({}),createText:()=>({}),createElement:()=>({}),insert(){},remove(){},setText(){},setElementText(){},parentNode:()=>null,nextSibling:()=>null,patchProp(){}});
    app=renderer.createApp({setup(){useTextFit(ref(box),ref(content),()=>32,()=>true);return()=>null;}});
    app.mount({});await nextTick();await Promise.resolve();
    assert.ok(size<=10&&size>9.9);
    box.clientHeight=64;observers[0].callback();await Promise.resolve();assert.equal(size,32);
    observers[1].callback();app.unmount();app=null;
    const before=writes;resolveFonts();await Promise.resolve();await Promise.resolve();
    for(const observer of observers){assert.ok(observer.disconnected);observer.callback();}
    await Promise.resolve();assert.equal(writes,before);assert.equal(listeners.size,0);
  }finally{app?.unmount();Object.assign(globalThis,original);await server.close();}
});
