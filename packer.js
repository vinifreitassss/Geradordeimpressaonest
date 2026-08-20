(function(g){
  class Packer{
    constructor(W,H,padding=0,options={}){this.W=W;this.H=H;this.padding=padding;this.options={allowRotation:true,...options};this.bins=[]}
    addArray(arr){this.items=arr.slice();this._pack()}
    _pack(){
      const source=(this.items||[]).filter(i=>Number.isFinite(i.width)&&Number.isFinite(i.height)&&i.width>0&&i.height>0);
      const strategies=[
        (a,b)=>b.width*b.height-a.width*a.height,
        (a,b)=>Math.max(b.width,b.height)-Math.max(a.width,a.height),
        (a,b)=>b.height-a.height || b.width-a.width,
        (a,b)=>b.width-a.width || b.height-a.height
      ];
      let best=null;
      for(const sort of strategies){
        const items=source.slice().sort(sort);const bins=[];
        for(const item of items){
          let placed=null,binIndex=-1;
          for(let bi=0;bi<bins.length;bi++){
            const r=place(bins[bi],item,this.options);
            if(r&&(!placed||r.score<placed.score)){placed=r;binIndex=bi}
          }
          if(!placed){
            const bin={width:this.W,height:this.H,rects:[],free:[{x:0,y:0,width:this.W,height:this.H}],height:0};
            placed=place(bin,item,this.options);
            if(!placed){bin.rects.push({x:0,y:0,width:item.width,height:item.height,rot:false,data:item.data,oversized:true});bins.push(bin);continue}
            binIndex=bins.length;bins.push(bin);
          }
          const b=bins[binIndex];b.rects.push(placed);b.free=prune(splitFree(b.free,placed));b.height=Math.max(b.height,placed.y+placed.height);
        }
        const score=bins.length*1000000+bins.reduce((s,b)=>s+(this.W*b.height-b.rects.reduce((a,r)=>a+r.width*r.height,0)),0);
        if(!best||score<best.score)best={score,bins};
      }
      this.bins=best?best.bins:[];
    }
  }
  function place(bin,item,options){
    let best=null;
    const candidates=[{w:item.width,h:item.height,rot:false},{w:item.height,h:item.width,rot:true}];
    for(const c of candidates){
      if(c.rot&&!options.allowRotation)continue;
      if(c.w<=0||c.h<=0)continue;
      for(const f of bin.free){
        if(c.w<=f.width&&c.h<=f.height){
          const leftoverW=f.width-c.w,leftoverH=f.height-c.h;
          const score=Math.min(leftoverW,leftoverH)*100000+Math.max(leftoverW,leftoverH);
          if(!best||score<best.score)best={x:f.x,y:f.y,width:c.w,height:c.h,rot:c.rot,data:item.data,score};
        }
      }
    }
    return best;
  }
  function splitFree(free,r){
    const out=[];
    for(const f of free){
      if(r.x>=f.x+f.width||r.x+r.width<=f.x||r.y>=f.y+f.height||r.y+r.height<=f.y){out.push(f);continue}
      if(r.x>f.x)out.push({x:f.x,y:f.y,width:r.x-f.x,height:f.height});
      if(r.x+r.width<f.x+f.width)out.push({x:r.x+r.width,y:f.y,width:f.x+f.width-r.x-r.width,height:f.height});
      if(r.y>f.y)out.push({x:f.x,y:f.y,width:f.width,height:r.y-f.y});
      if(r.y+r.height<f.y+f.height)out.push({x:f.x,y:r.y+r.height,width:f.width,height:f.y+f.height-r.y-r.height});
    }
    return out;
  }
  function prune(rs){
    for(let i=rs.length-1;i>=0;i--){if(rs[i].width<=0||rs[i].height<=0){rs.splice(i,1);continue}for(let j=rs.length-1;j>=0;j--)if(i!==j&&contains(rs[j],rs[i])){rs.splice(i,1);break}}
    return rs;
  }
  function contains(a,b){return b.x>=a.x&&b.y>=a.y&&b.x+b.width<=a.x+a.width&&b.y+b.height<=a.y+a.height}
  g.MaxRectsPacker={MaxRectsPacker:Packer};
})(window);
