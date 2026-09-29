/* One event in flight; Python acknowledges before controls unlock. */
(()=>{
'use strict';const $=id=>document.getElementById(id);let state={},session='',qty=1,limit=false,pending=null,lastNotice='';
function fit(){let h=window.innerHeight;try{h=parent.innerHeight;}catch{}document.documentElement.style.setProperty('--screen',Math.max(570,h-4)+'px');parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height:Math.max(570,h-4)},'*');}
window.addEventListener('resize',fit);fit();
function notice(message){$('notice').textContent=message;clearTimeout(lastNotice);lastNotice=setTimeout(()=>$('notice').textContent='',3000);}
function refresh(){
 document.querySelectorAll('[data-qty]').forEach(b=>b.classList.toggle('active',+b.dataset.qty===qty));
 for(const id of ['open_long','open_short','close_long','close_short'])$(id).disabled=!!pending||(id.startsWith('open')?state.finished:qty>(state[id]||0)||(state.finished&&limit));
 for(const id of ['next','forward','play'])$(id).disabled=!!pending||state.finished;
 for(const id of ['random','settings','records','flatten'])$(id).disabled=!!pending;
 $('order').textContent=limit?'限价 '+($('limitValue').value||'—')+' ▾':'市价 ▾';
 $('limitValue').disabled=!limit;$('marketMode').classList.toggle('active',!limit);$('limitMode').classList.toggle('active',limit);
}
function send(action,extra={}){if(pending)return;pending=crypto.randomUUID();refresh();parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:{id:pending,session,action,...extra}},'*');}
for(const action of ['random','settings','records','next','forward','play','flatten'])$(action).onclick=()=>{if(action==='flatten')$('orderSheet').close();send(action);};
for(const action of ['open_long','open_short','close_long','close_short'])$(action).onclick=()=>{const price=Number($('limitValue').value);if(limit&&(!Number.isFinite(price)||price<=0)){notice('请设置有效的限价');$('orderSheet').showModal();return;}send(action,{quantity:qty,limit:limit?price:null});};
document.querySelectorAll('[data-qty]').forEach(b=>b.onclick=()=>{qty=+b.dataset.qty;refresh();});
document.querySelectorAll('[data-period]').forEach(b=>b.onclick=()=>send('period',{value:+b.dataset.period}));
$('speed').onchange=e=>send('speed',{value:+e.target.value});
$('more').onclick=()=>$('options').showModal();$('order').onclick=()=>$('orderSheet').showModal();
$('marketMode').onclick=()=>{limit=false;refresh();};$('limitMode').onclick=()=>{limit=true;refresh();};$('limitValue').oninput=refresh;
window.addEventListener('message',event=>{if(event.source!==parent||event.data?.type!=='streamlit:render')return;const args=event.data.args;state=args.state||{};if(session!==args.session_id){session=args.session_id;pending=null;limit=false;$('limitValue').value=args.rows.at(-1)?.c||'';}if(state.ack===pending)pending=null;
$('returns').textContent=(state.returns||0).toFixed(2)+'%';$('returns').className=state.returns>=0?'up':'down';
$('holdings').textContent=`多 ${state.long||0}手 · 空 ${state.short||0}手`;$('pnl').textContent=`浮盈 ${(state.pnl||0).toFixed(0)}`;$('pnl').className=state.pnl>=0?'up':'down';$('play').textContent=state.playing?'Ⅱ 暂停':'▶ 播放';$('speed').value=state.speed||1;
$('time').textContent=state.time||'';$('time').title=state.range||'';$('status').textContent=state.finished?'本局结束 · 可平仓结算':pending?'处理中…':'双指缩放 · 长按看价';$('progress').style.width=(state.progress*100)+'%';document.querySelectorAll('[data-period]').forEach(b=>b.classList.toggle('active',+b.dataset.period===args.period));if(state.notice)notice(state.notice);refresh();fit();});
})();
