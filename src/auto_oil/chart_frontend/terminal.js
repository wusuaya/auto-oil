/* Persistent canvas chart. All gestures stay in this iframe, not Python reruns. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id), canvas=$('chart'), ctx=canvas.getContext('2d');
  const RED='#e7474e', GREEN='#159b75', COLORS=['#7c8291','#cd9d28','#d661b7','#428edf'];
  const clone=x=>JSON.parse(JSON.stringify(x));
  let prefs={main:'MA',sub:'MACD',vol:true,levels:true,hollow:true,params:clone(OilIndicators.defaults)};
  try{prefs={...prefs,...JSON.parse(localStorage.getItem('oil-chart-prefs-v1')||'{}')};}catch{}
  let rows=[], indicators={}, markers=[], levels=[], n=0, count=55, right=0, follow=true;
  let touchTimer=null, inspecting=false;
  let key='',period='',hover=null,W=0,H=0,panes=[],drag=null,pointers=new Map(),pinch=null;
  const fmt=(v,d=2)=>Number.isFinite(v)?v.toFixed(d):'—';
  const short=v=>Math.abs(v)>=10000?(v/10000).toFixed(1)+'万':fmt(v,0);
  const savePrefs=()=>{try{localStorage.setItem('oil-chart-prefs-v1',JSON.stringify(prefs));}catch{}};
  function saveView(){try{sessionStorage.setItem(key,JSON.stringify({count,follow,time:rows[Math.max(0,Math.ceil(right)-1)]?.t}));}catch{}}
  function locate(t){let lo=0,hi=n;while(lo<hi){const mid=(lo+hi)>>1;if(rows[mid].t<=t)lo=mid+1;else hi=mid;}return Math.max(0,lo-1);}
  function constrain(){count=Math.max(15,Math.min(Math.max(n,15),Math.round(count)));right=Math.max(Math.min(count,n),Math.min(n,right));}
  function syncButtons(){document.querySelectorAll('[data-main]').forEach(b=>b.classList.toggle('active',b.dataset.main===prefs.main));document.querySelectorAll('[data-sub]').forEach(b=>b.classList.toggle('active',b.dataset.sub===prefs.sub));$('vol').checked=prefs.vol;$('levels').checked=prefs.levels;$('style').textContent=prefs.hollow?'空心阳线':'实心阳线';}
  function mainKeys(){return prefs.main==='MA'?prefs.params.ma.map(x=>'MA'+x):prefs.main==='BOLL'?['MID','UPPER','LOWER']:prefs.main==='EXPMA'?prefs.params.ema.map(x=>'EMA'+x):[];}
  function subKeys(){return prefs.sub==='MACD'?['DIF','DEA']:prefs.sub==='KDJ'?['K','D','J']:prefs.sub==='RSI'?prefs.params.rsi.map(x=>'RSI'+x):prefs.sub==='WR'?['WR']:prefs.sub==='CCI'?['CCI']:['VMA5','VMA10'];}
  function resize(){const ratio=window.devicePixelRatio||1;W=canvas.clientWidth;H=canvas.clientHeight;canvas.width=Math.round(W*ratio);canvas.height=Math.round(H*ratio);ctx.setTransform(ratio,0,0,ratio,0,0);draw();height();}
  function height(){parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height:document.body.scrollHeight},'*');}
  const text=(s,x,y,c='#999fae',align='left')=>{ctx.fillStyle=c;ctx.textAlign=align;ctx.fillText(s,x,y);};
  function draw(){
    if(!n||!W)return;
    constrain(); ctx.clearRect(0,0,W,H);ctx.fillStyle='#ffffff';ctx.fillRect(0,0,W,H);ctx.font='11px Arial,"Microsoft YaHei"';ctx.lineWidth=1;
    const width=Math.max(60,W-72), start=Math.max(0,right-count), end=Math.min(n,Math.ceil(right)), first=Math.floor(start),dx=width/count;
    const X=i=>8+(i-start+.5)*dx, current=hover?Math.max(first,Math.min(end-1,Math.floor(start+(hover.x-8)/dx))):end-1;
    const r=rows[current]; if(!r)return;
    const showVol=prefs.vol && prefs.sub!=='VOL', subH=Math.max(56,H*.19), volH=showVol?Math.max(44,H*.15):0, mainH=H-subH-volH-25;
    panes=[{top:0,bottom:mainH,kind:'price',keys:mainKeys()},...(showVol?[{top:mainH,bottom:mainH+volH,kind:'vol',keys:['VMA5','VMA10']}]:[]),{top:mainH+volH,bottom:H-25,kind:prefs.sub==='VOL'?'vol':'sub',keys:subKeys()}];
    for(const p of panes){
      let vals=[];
      if(p.kind==='price')for(let i=first;i<end;i++)vals.push(rows[i].h,rows[i].l);
      if(p.kind==='vol')for(let i=first;i<end;i++)vals.push(rows[i].v,0);
      if(p.kind==='sub'&&prefs.sub==='MACD')vals.push(0,...indicators.MACD.slice(first,end));
      for(const k of p.keys)vals.push(...indicators[k].slice(first,end).filter(v=>v!==null&&Number.isFinite(v)));
      if(p.kind==='sub'&&['RSI','WR','KDJ'].includes(prefs.sub))vals.push(0,100);
      let lo=vals.length?Math.min(...vals):0,hi=vals.length?Math.max(...vals):1;
      const pad=(hi-lo||Math.max(1,Math.abs(hi)*.01))*.08;
      if(p.kind!=='vol')lo-=pad;hi+=pad;
      p.y0=p.top+24;p.y1=p.bottom-9;p.lo=lo;p.hi=hi;p.Y=v=>p.y1-(v-lo)/(hi-lo||1)*(p.y1-p.y0);
      ctx.strokeStyle='#e7e9ee';ctx.beginPath();ctx.moveTo(0,p.bottom);ctx.lineTo(W,p.bottom);ctx.stroke();
      const ticks=p.y1-p.y0<70?1:4;for(let j=0;j<=ticks;j++){let y=p.y0+(p.y1-p.y0)*j/ticks;ctx.strokeStyle='#f0f1f4';ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(width+8,y);ctx.stroke();text(p.kind==='vol'?short(hi-(hi-lo)*j/ticks):fmt(hi-(hi-lo)*j/ticks,p.kind==='price'?1:2),W-4,y+4,'#9298a5','right');}
      ctx.save();ctx.beginPath();ctx.rect(0,p.y0,width+9,p.y1-p.y0+1);ctx.clip();
      if(p.kind==='price'){
        for(let i=first;i<end;i++){const b=rows[i],x=X(i),up=b.c>=b.o,col=up?RED:GREEN;ctx.strokeStyle=col;ctx.fillStyle=col;ctx.beginPath();ctx.moveTo(x,p.Y(b.h));ctx.lineTo(x,p.Y(b.l));ctx.stroke();const y=Math.min(p.Y(b.o),p.Y(b.c)),bh=Math.max(1,Math.abs(p.Y(b.o)-p.Y(b.c))),bw=Math.max(1,dx*.68);if(up&&prefs.hollow){ctx.fillStyle='#ffffff';ctx.fillRect(x-bw/2,y,bw,bh);ctx.strokeRect(x-bw/2,y,bw,bh);}else ctx.fillRect(x-bw/2,y,bw,bh);}
      }
      if(p.kind==='vol'||(p.kind==='sub'&&prefs.sub==='MACD')){
        for(let i=first;i<end;i++){const value=p.kind==='vol'?rows[i].v:indicators.MACD[i],up=p.kind==='vol'?rows[i].c>=rows[i].o:value>=0;ctx.fillStyle=up?RED:GREEN;const y=p.Y(value),zero=p.Y(0);ctx.fillRect(X(i)-Math.max(1,dx*.65)/2,Math.min(y,zero),Math.max(1,dx*.65),Math.max(1,Math.abs(y-zero)));}
      }
      p.keys.forEach((k,kidx)=>{ctx.strokeStyle=COLORS[kidx%COLORS.length];ctx.lineWidth=1;ctx.beginPath();let on=false;for(let i=first;i<end;i++){const value=indicators[k][i];if(value===null||!Number.isFinite(value)){on=false;continue;}if(on)ctx.lineTo(X(i),p.Y(value));else ctx.moveTo(X(i),p.Y(value));on=true;}ctx.stroke();});
      if(p.kind==='price'){
        if(prefs.levels){const seen=new Set();for(const level of levels){const id=level.label+level.price;if(seen.has(id))continue;seen.add(id);if(level.price<p.lo||level.price>p.hi)continue;ctx.strokeStyle=level.side==='buy'?RED:GREEN;ctx.setLineDash([5,4]);ctx.beginPath();ctx.moveTo(0,p.Y(level.price));ctx.lineTo(width,p.Y(level.price));ctx.stroke();ctx.setLineDash([]);text(level.label+' '+fmt(level.price,1),12,p.Y(level.price)-3,ctx.strokeStyle);}}
        for(const marker of markers){const i=locate(marker.t);if(i<first||i>=end||marker.t<rows[0].t)continue;const x=X(i),y=p.Y(marker.price),buy=marker.side==='buy';ctx.fillStyle=buy?RED:GREEN;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x-5,y+(buy?10:-10));ctx.lineTo(x+5,y+(buy?10:-10));ctx.closePath();ctx.fill();text(buy?'B':'S',x,y+(buy?21:-13),ctx.fillStyle,'center');}
      }
      ctx.restore();
      const name=p.kind==='price'?(prefs.main==='NONE'?'K线':prefs.main):p.kind==='vol'?'VOL':prefs.sub;
      text(name,8,p.top+15,'#747b88');let tx=8+ctx.measureText(name).width+14;
      const infoKeys=p.kind==='sub'&&prefs.sub==='MACD'?[...p.keys,'MACD']:p.kind==='vol'?['VOL',...p.keys]:p.keys;
      infoKeys.forEach((k,i)=>{const s=k+':'+fmt(indicators[k][current],k==='VOL'?0:2);if(tx+ctx.measureText(s).width<width){text(s,tx,p.top+15,COLORS[i%COLORS.length]);tx+=ctx.measureText(s).width+14;}});
    }
    for(let j=0;j<=2;j++){const i=Math.max(first,Math.min(end-1,Math.round(start+count*j/2)));const x=Math.max(40,Math.min(width-40,X(i)));text(rows[i].t.slice(5),x,H-8,'#8f96a5','center');}
    if(hover){const p=panes.find(p=>hover.y>=p.top&&hover.y<=p.bottom);ctx.setLineDash([3,3]);ctx.strokeStyle='#9298a6';ctx.beginPath();ctx.moveTo(X(current),0);ctx.lineTo(X(current),H-25);if(p){ctx.moveTo(0,hover.y);ctx.lineTo(width,hover.y);}ctx.stroke();ctx.setLineDash([]);if(p){const val=p.lo+(p.y1-hover.y)/(p.y1-p.y0)*(p.hi-p.lo);ctx.fillStyle='#424854';ctx.fillRect(width+8,hover.y-9,64,18);text(fmt(val,p.kind==='vol'?0:2),W-3,hover.y+4,'white','right');}ctx.fillStyle='#424854';const timeX=Math.max(60,Math.min(width-60,X(current)));ctx.fillRect(timeX-59,H-24,118,23);text(r.t.slice(5),timeX,H-8,'white','center');}
    for(const [id,value] of [['qo',r.o],['qh',r.h],['qc',r.c],['ql',r.l]]){document.getElementById(id).textContent=fmt(value,1);document.getElementById(id).className=value>=r.o?'up':'down';}
    $('quote').textContent=`${r.t}　成交量 ${short(r.v)}　${period}分钟`;
    $('quote').style.color=r.c>=r.o?RED:GREEN;
    $('view').textContent=`${Math.min(count,n)} 根 / ${follow?'跟随最新':'查看历史'}`;
    $('history').textContent=`已载入 ${n.toLocaleString()} 根 · 仅已揭示行情`;
    canvas.dataset.visibleCount=count;canvas.dataset.rightTime=rows[end-1].t;canvas.dataset.follow=String(follow);
  }
  function changed(){constrain();saveView();draw();}
  function zoom(factor,anchor=.5){const old=count,next=Math.max(15,Math.min(Math.max(n,15),Math.round(old*factor)));const point=right-old+anchor*old;count=next;right=follow?n:point+(1-anchor)*next;changed();}
  function pan(amount){right+=amount;follow=right>=n;hover=null;changed();}
  function latest(){follow=true;right=n;hover=null;changed();}
  function reset(){count=55;latest();}
  $('zin').onclick=()=>zoom(.8);$('zout').onclick=()=>zoom(1.25);$('older').onclick=()=>pan(-Math.max(5,count/4));$('newer').onclick=()=>pan(Math.max(5,count/4));$('latest').onclick=latest;$('reset').onclick=reset;
  document.querySelectorAll('[data-main]').forEach(b=>b.onclick=()=>{prefs.main=b.dataset.main;savePrefs();syncButtons();draw();});
  document.querySelectorAll('[data-sub]').forEach(b=>b.onclick=()=>{prefs.sub=b.dataset.sub;savePrefs();syncButtons();draw();});
  $('vol').onchange=e=>{prefs.vol=e.target.checked;savePrefs();draw();};$('levels').onchange=e=>{prefs.levels=e.target.checked;savePrefs();draw();};$('style').onclick=()=>{prefs.hollow=!prefs.hollow;savePrefs();syncButtons();draw();};
  $('full').onclick=()=>{$('wrap').classList.toggle('large');$('full').textContent=$('wrap').classList.contains('large')?'还原图表':'放大图表';resize();};
  function openParams(){for(const k of Object.keys(prefs.params))$('form').elements[k].value=prefs.params[k].join(',');$('error').textContent='';$('dialog').showModal();}
  $('params').onclick=openParams;$('cancel').onclick=()=>$('dialog').close();$('defaultparams').onclick=()=>{for(const [k,v]of Object.entries(OilIndicators.defaults))$('form').elements[k].value=v.join(',');};
  $('form').onsubmit=e=>{e.preventDefault();const p={};for(const k of Object.keys(OilIndicators.defaults)){p[k]=$('form').elements[k].value.split(/[,，\s]+/).filter(Boolean).map(Number);const size=OilIndicators.defaults[k].length;if(p[k].length!==size||p[k].some((v,i)=>!Number.isFinite(v)||v<1||v>250||(!(k==='boll'&&i===1)&&!Number.isInteger(v)))){$('error').textContent=k.toUpperCase()+' 参数无效，请按默认个数填写 1–250 的周期。';return;}}if(p.macd[0]>=p.macd[1]){$('error').textContent='MACD 短周期必须小于长周期。';return;}prefs.params=p;indicators=OilIndicators.calculate(rows,p);savePrefs();$('dialog').close();draw();};
  function point(e){const r=canvas.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top};}
  canvas.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?.85:1/.85,Math.max(0,Math.min(1,point(e).x/(W-72))));},{passive:false});
  canvas.addEventListener('pointerdown',e=>{if(e.button&&e.button!==0)return;canvas.focus();canvas.setPointerCapture(e.pointerId);const pos=point(e);pointers.set(e.pointerId,pos);drag={x:pos.x,right};if(pointers.size===2){const pts=[...pointers.values()];pinch={distance:Math.hypot(pts[0].x-pts[1].x,pts[0].y-pts[1].y),count};}hover=e.pointerType==='touch'?null:pos;inspecting=false;clearTimeout(touchTimer);if(e.pointerType==='touch'&&pointers.size===1)touchTimer=setTimeout(()=>{inspecting=true;hover=pos;draw();},450);draw();});
  canvas.addEventListener('pointermove',e=>{const pos=point(e);if(pointers.has(e.pointerId))pointers.set(e.pointerId,pos);if(pointers.size===2&&pinch){clearTimeout(touchTimer);inspecting=false;const pts=[...pointers.values()],dist=Math.hypot(pts[0].x-pts[1].x,pts[0].y-pts[1].y);zoom(pinch.count*Math.max(1,pinch.distance)/Math.max(1,dist)/count);return;}if(inspecting){hover=pos;draw();return;}if(drag&&pointers.size===1&&Math.abs(pos.x-drag.x)>5){clearTimeout(touchTimer);right=drag.right-(pos.x-drag.x)/(Math.max(60,W-72)/count);follow=right>=n;hover=null;changed();}else{hover=pos;draw();}});
  function release(e){clearTimeout(touchTimer);inspecting=false;pointers.delete(e.pointerId);drag=null;pinch=null;saveView();}
  canvas.addEventListener('pointerup',release);canvas.addEventListener('pointercancel',release);canvas.addEventListener('pointerleave',()=>{if(!drag){hover=null;draw();}});canvas.ondblclick=reset;
  canvas.onkeydown=e=>{if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','+','-','=','End','Home','Escape'].includes(e.key))e.preventDefault();if(e.key==='ArrowUp'||e.key==='+'||e.key==='=')zoom(.8);if(e.key==='ArrowDown'||e.key==='-')zoom(1.25);if(e.key==='End')latest();if(e.key==='Home'){right=Math.min(n,count);follow=false;changed();}if(e.key==='Escape'){hover=null;draw();}if(e.key==='ArrowLeft'||e.key==='ArrowRight'){const direction=e.key==='ArrowLeft'?-1:1;if(e.ctrlKey){pan(direction*count/4);return;}const dx=Math.max(60,W-72)/count;hover={x:hover?hover.x+direction*dx:Math.max(8,(W-72)-dx),y:hover?.y??100};if(hover.x<8){pan(-1);hover={x:8,y:100};}if(hover.x>W-72){pan(1);hover={x:W-72,y:100};}draw();}};
  canvas.oncontextmenu=e=>{e.preventDefault();$('context').style.display='block';$('context').style.left=Math.min(e.clientX,W-150)+'px';$('context').style.top=Math.min(e.clientY,H-80)+'px';};
  document.addEventListener('click',e=>{if(!e.target.closest('#context'))$('context').style.display='none';});document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>{$('context').style.display='none';({latest,reset,params:openParams})[b.dataset.action]();});
  window.addEventListener('message',event=>{
    if(event.source!==parent||event.data?.type!=='streamlit:render')return;
    const args=event.data.args, nextKey='oil-view-'+args.session_id+'-'+args.period, oldTime=rows[Math.max(0,Math.ceil(right)-1)]?.t;
    rows=args.rows||[];n=rows.length;markers=args.markers||[];levels=args.levels||[];period=args.period;
    if(key!==nextKey){key=nextKey;let saved=null;try{saved=JSON.parse(sessionStorage.getItem(key)||'null');}catch{}count=saved?.count||55;follow=saved?.follow??true;right=follow?n:saved?.time?locate(saved.time)+1:n;hover=null;}
    else right=follow?n:oldTime?locate(oldTime)+1:right;
    indicators=OilIndicators.calculate(rows,prefs.params);syncButtons();constrain();resize();saveView();
  });
  new ResizeObserver(resize).observe(canvas);syncButtons();
  parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');height();
})();
