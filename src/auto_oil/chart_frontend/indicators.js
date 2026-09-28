/* Standard public indicator formulas. No future prices or external services. */
(function (root) {
  const defaults = {ma:[5,10,20,60], boll:[20,2], ema:[12,50], macd:[12,26,9], kdj:[9,3,3], rsi:[6,12,24], wr:[14], cci:[14]};
  function sma(a,n) { let sum=0; return a.map((v,i)=>{sum+=v; if(i>=n)sum-=a[i-n];return i>=n-1?sum/n:null;}); }
  function ema(a,n) {let last=a[0]??0;return a.map((v,i)=>last=i?last+(v-last)*2/(n+1):v);}
  function cnSma(a,n,seed) {let last=seed??a[0]??0;return a.map(v=>last=(v+(n-1)*last)/n);}
  function calculate(rows,p=defaults) {
    const c=rows.map(r=>r.c), v=rows.map(r=>r.v), out={};
    p.ma.forEach(n=>out['MA'+n]=sma(c,n)); p.ema.forEach(n=>out['EMA'+n]=ema(c,n));
    const [bn,bk]=p.boll, mid=sma(c,bn);
    const sd=c.map((_,i)=>i<bn-1?null:Math.sqrt(c.slice(i-bn+1,i+1).reduce((s,x)=>s+(x-mid[i])**2,0)/bn));
    out.MID=mid;out.UPPER=mid.map((m,i)=>m===null?null:m+bk*sd[i]);out.LOWER=mid.map((m,i)=>m===null?null:m-bk*sd[i]);
    const fast=ema(c,p.macd[0]),slow=ema(c,p.macd[1]);out.DIF=c.map((_,i)=>fast[i]-slow[i]);out.DEA=ema(out.DIF,p.macd[2]);out.MACD=c.map((_,i)=>2*(out.DIF[i]-out.DEA[i]));
    const rsv=rows.map((r,i)=>{const chunk=rows.slice(Math.max(0,i-p.kdj[0]+1),i+1),hi=Math.max(...chunk.map(x=>x.h)),lo=Math.min(...chunk.map(x=>x.l));return hi===lo?50:100*(r.c-lo)/(hi-lo);});
    out.K=cnSma(rsv,p.kdj[1],50);out.D=cnSma(out.K,p.kdj[2],50);out.J=out.K.map((k,i)=>3*k-2*out.D[i]);
    const delta=c.map((x,i)=>i?x-c[i-1]:0);
    p.rsi.forEach(n=>{const up=cnSma(delta.map(x=>Math.max(x,0)),n,0),total=cnSma(delta.map(Math.abs),n,0);out['RSI'+n]=up.map((x,i)=>total[i]?100*x/total[i]:50);});
    out.WR=rows.map((r,i)=>{if(i<p.wr[0]-1)return null;const ch=rows.slice(i-p.wr[0]+1,i+1),hi=Math.max(...ch.map(x=>x.h)),lo=Math.min(...ch.map(x=>x.l));return hi===lo?50:100*(hi-r.c)/(hi-lo);});
    const tp=rows.map(r=>(r.h+r.l+r.c)/3),avg=sma(tp,p.cci[0]);
    out.CCI=tp.map((x,i)=>{if(avg[i]===null)return null;const md=tp.slice(i-p.cci[0]+1,i+1).reduce((s,y)=>s+Math.abs(y-avg[i]),0)/p.cci[0];return md?(x-avg[i])/(.015*md):0;});
    out.VOL=v;out.VMA5=sma(v,5);out.VMA10=sma(v,10);return out;
  }
  const api={defaults,sma,ema,cnSma,calculate};
  if(typeof module!=='undefined')module.exports=api;else root.OilIndicators=api;
})(typeof window==='undefined'?this:window);
