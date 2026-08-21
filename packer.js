(function(g){
  class Packer{
    constructor(W,H,padding=0,options={}){this.W=W;this.H=H;this.padding=padding;this.options={allowRotation:true,...options};this.bins=[]}
    addArray(arr){this.items=arr.slice();this._pack()}
    _pack(){
      const source=(this.items||[]).filter(i=>Number.isFinite(i.width)&&Number.isFinite(i.height)&&i.width>0&&i.height>0);
      const strategies=[
        (a,b)=>b.width*b.height-a.width*a.height,
        (a,b)=>Math.max(b.width,b.height)-Math.max(a.width,a.height),
        (a,b)=>b.height-a.height||b.width-a.width,
        (a,b)=>b.width-a.width||b.height-a.height
      ];
      let best=null;
      for(const sort of strategies){
        const items=source.slice().sort(sort),bins=[];
        for(const item of items){
          let placed=null,bi=-1;
          for(let i=0;i<bins.length;i++){const r=place(bins[i],item,this.options);if(r&&(!placed||r.score<placed.score)){placed=r;bi=i}}
          if(!placed){const bin={width:this.W,height:this.H,rects:[],free:[{x:0,y:0,width:this.W,height:this.H}],height:0};placed=place(bin,item,this.options);if(!placed){continue}bi=bins.length;bins.push(bin)}
          const b=bins[bi];b.rects.push(placed);b.free=prune(splitFree(b.free,placed));b.height=Math.max(b.height,placed.y+placed.height)
        }
        const used=bins.reduce((s,b)=>s+b.rects.reduce((a,r)=>a+r.width*r.height,0),0),height=bins.reduce((s,b)=>s+Math.max(0,b.height),0);
        const score=bins.length*1000000+(bins.length?height:0)*10-used*.001;
        if(!best||score<best.score)best={score,bins}
      }
      this.bins=best?best.bins:[]
    }
  }
  function place(bin,item,options){
    let best=null;const candidates=[{w:item.width,h:item.height,rot:false},{w:item.height,h:item.width,rot:true}];
    for(const c of candidates){if(c.rot&&!options.allowRotation)continue;for(const f of bin.free){if(c.w<=f.width+1e-6&&c.h<=f.height+1e-6){const lw=f.width-c.w,lh=f.height-c.h,score=Math.min(lw,lh)*100000+Math.max(lw,lh);if(!best||score<best.score)best={x:f.x,y:f.y,width:c.w,height:c.h,rot:c.rot,data:item.data,score}}}}
    return best
  }
  function splitFree(free,r){const out=[];for(const f of free){if(r.x>=f.x+f.width||r.x+r.width<=f.x||r.y>=f.y+f.height||r.y+r.height<=f.y){out.push(f);continue}if(r.x>f.x)out.push({x:f.x,y:f.y,width:r.x-f.x,height:f.height});if(r.x+r.width<f.x+f.width)out.push({x:r.x+r.width,y:f.y,width:f.x+f.width-r.x-r.width,height:f.height});if(r.y>f.y)out.push({x:f.x,y:f.y,width:f.width,height:r.y-f.y});if(r.y+r.height<f.y+f.height)out.push({x:f.x,y:r.y+r.height,width:f.width,height:f.y+f.height-r.y-r.height})}return out}
  function prune(rs){for(let i=rs.length-1;i>=0;i--){if(rs[i].width<=0||rs[i].height<=0){rs.splice(i,1);continue}for(let j=rs.length-1;j>=0;j--)if(i!==j&&contains(rs[j],rs[i])){rs.splice(i,1);break}}return rs}
  function contains(a,b){return b.x>=a.x&&b.y>=a.y&&b.x+b.width<=a.x+a.width&&b.y+b.height<=a.y+a.height}
  g.MaxRectsPacker={MaxRectsPacker:Packer};

  const BAR_PAT='212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 114131 311141 411131 211412 211214 211232 2331112'.split(' ');
  function code128B(text){text=String(text??'').replace(/[^\x20-\x7E]/g,'?');let vals=[104];for(const ch of text)vals.push(ch.charCodeAt(0)-32);let sum=104;for(let i=1;i<vals.length;i++)sum+=vals[i]*i;vals.push(sum%103);vals.push(106);return vals.map(v=>BAR_PAT[v]).join('')}
  function drawBarcode(page,text,x,y,w,h){const bits=code128B(text),quiet=Math.max(.6,w*.035),usable=Math.max(1,w-2*quiet),module=usable/bits.length;let xx=x+quiet;for(const ch of bits){const n=Number(ch);if(ch%2==='1')page.drawRectangle({x:xx,y,width:module*n,height:h,borderWidth:0});xx+=module*n}}

  function finite(n,f=0){return Number.isFinite(Number(n))?Number(n):f}
  function packIndividualPieces(){
    const items=[];const SP=2,PAD=2,LABEL=10,SHEET_W=450,SHEET_H=600;
    for(const o of state.orders){
      for(let i=0;i<o.quantity;i++){
        const pw=finite(o.w),ph=finite(o.h);if(!(pw>0&&ph>0))continue;
        const candidates=[[pw,ph],[ph,pw]];let best=null;
        for(const [rw,rh] of candidates){
          const bw=rw+2*PAD,bh=rh+LABEL+2*PAD;if(bw>SHEET_W||bh>SHEET_H)continue;
          const score=bh*1000+bw;if(!best||score<best.score)best={pw:rw,ph:rh,bw,bh,score,rot:rw!==pw};
        }
        if(!best)throw Error(`A peça do pedido ${o.code} não cabe em 450 × 600 mm.`);
        items.push({width:best.bw,height:best.bh,data:{orderId:o.id,code:o.code,modelName:o.modelName,quantity:1,index:i+1,total:o.quantity,pw:best.pw,ph:best.ph,rot:best.rot}})
      }
    }
    const p=new g.MaxRectsPacker.MaxRectsPacker(SHEET_W,SHEET_H,0,{allowRotation:false});p.addArray(items);
    return p.bins.map(b=>({width:SHEET_W,height:Math.min(SHEET_H,Math.max(1,finite(b.height,SHEET_H))),rects:b.rects.filter(r=>[r.x,r.y,r.width,r.height].every(Number.isFinite)).map(r=>({...r,data:r.data}))}));
  }

  async function buildIndividualPdf(sheets){
    const {PDFDocument,StandardFonts,rgb}=PDFLib,PT=72/25.4,SHEET_W=450,SHEET_H=600,SP=2,PAD=2,LABEL=10;
    const out=await PDFDocument.create(),font=await out.embedFont(StandardFonts.Helvetica),embedded=new Map(),pngCache=new Map(),pdfImgCache=new Map();
    for(const o of state.orders)embedded.set(o.id,(await out.embedPdf(o.modelBytes,[0]))[0]);
    for(const sh of sheets){
      const page=out.addPage([SHEET_W*PT,finite(sh.height,SHEET_H)*PT]);
      for(const r of sh.rects){
        const d=r.data,o=state.orders.find(x=>x.id===d.orderId);if(!o)continue;
        const x=finite(r.x)*PT,y=page.getHeight()-(finite(r.y)+finite(r.height))*PT,w=r.width*PT,h=r.height*PT;
        page.drawRectangle({x,y,width:w,height:h,borderWidth:.25,borderColor:rgb(.35,.35,.35)});
        page.drawText(`PED ${o.code} · ${d.index}/${d.total}`,{x:x+1.5,y:y+h-5.8,size:4.2,font,color:rgb(.1,.1,.1),maxWidth:Math.max(10,w-3)});
        drawBarcode(page,o.code,x+1.5,y+h-LABEL*PT+1,w-3,Math.max(3,3.8*PT));
        const px=x+PAD*PT,py=y+PAD*PT,iw=d.pw*PT,ih=d.ph*PT;
        if(o.mode==='own')page.drawPage(embedded.get(o.id),{x:px,y:py,width:iw,height:ih});
        else{
          const wPx=Math.max(1,Math.round(d.pw*300/25.4)),hPx=Math.max(1,Math.round(d.ph*300/25.4)),key=o.id+'-'+wPx+'-'+hPx;
          if(!pngCache.has(key))pngCache.set(key,makePiecePng(o,wPx,hPx));
          const png=await pngCache.get(key);if(!pdfImgCache.has(key))pdfImgCache.set(key,await out.embedPng(png));
          page.drawImage(pdfImgCache.get(key),{x:px,y:py,width:iw,height:ih});page.drawPage(embedded.get(o.id),{x:px,y:py,width:iw,height:ih});
        }
      }
    }
    return out.save();
  }

  function renderIndividualSheets(sheets){
    const box=document.getElementById('sheetPreview');if(!box)return;box.style.display='block';box.innerHTML='<b>Prévia das folhas — peça individual com identificação</b>';
    for(let si=0;si<sheets.length;si++){const s=sheets[si];box.appendChild(document.createTextNode(`Folha ${si+1} · 450 × ${finite(s.height,600).toFixed(1)} mm`));const d=document.createElement('div');d.className='sheet';d.style.aspectRatio=`450/${Math.max(1,finite(s.height,600))}`;for(const r of s.rects){const e=document.createElement('div');e.className='sheetBlock';e.style.left=(finite(r.x)/450*100)+'%';e.style.top=(finite(r.y)/Math.max(1,s.height)*100)+'%';e.style.width=(finite(r.width)/450*100)+'%';e.style.height=(finite(r.height)/Math.max(1,s.height)*100)+'%';e.innerHTML=`<div class="label">${esc(r.data.code)} · ${r.data.index}/${r.data.total}</div><div class="dots">||||||||</div>`;d.appendChild(e)}box.appendChild(d)}
  }

  document.addEventListener('DOMContentLoaded',()=>{
    const btn=document.getElementById('generate');if(!btn)return;
    btn.onclick=async()=>{
      if(!state.orders.length){show('nestMsg','Adicione pelo menos um pedido.',true);return}
      btn.disabled=true;document.getElementById('progress').style.display='block';
      try{
        const sheets=packIndividualPieces();renderIndividualSheets(sheets);const bytes=await buildIndividualPdf(sheets);const url=URL.createObjectURL(new Blob([bytes],{type:'application/pdf'})),a=document.createElement('a');a.href=url;a.download='impressao_nest_'+new Date().toISOString().replace(/[-:T]/g,'').slice(0,14)+'.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);show('nestMsg',`PDF gerado localmente com ${sheets.length} folha(s), ${sheets.reduce((n,s)=>n+s.rects.length,0)} peças.`)
      }catch(e){console.error(e);show('nestMsg',e.message||String(e),true)}finally{btn.disabled=false;document.getElementById('progress').style.display='none'}
    }
  });
})(window);
