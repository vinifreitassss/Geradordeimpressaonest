(function(g){
  class Packer{
    constructor(W,H,padding=0,options={}){this.W=W;this.H=H;this.padding=padding;this.options=options;this.bins=[]}
    addArray(arr){this.items=arr.slice();this._pack()}
    _pack(){
      const items=(this.items||[]).slice().sort((a,b)=>b.width*b.height-a.width*a.height);
      this.bins=[];
      for(const item of items){
        let placed=false;
        for(const bin of this.bins){const r=place(bin,item,this.options);if(r){bin.rects.push(r);bin.free=prune(splitFree(bin.free,r));bin.height=Math.max(bin.height,r.y+r.height);placed=true;break}}
        if(!placed){
          const bin={width:this.W,height:this.H,rects:[],free:[{x:0,y:0,width:this.W,height:this.H}],height:0};
          const r=place(bin,item,this.options);
          if(!r) bin.rects.push({x:0,y:0,width:item.width,height:item.height,rot:false,data:item.data,oversized:true});
          else{bin.rects.push(r);bin.free=prune(splitFree(bin.free,r));bin.height=r.y+r.height}
          this.bins.push(bin);
        }
      }
    }
  }
  function place(bin,item,options){
    let best=null;
    for(const f of bin.free){
      if(item.width<=f.width&&item.height<=f.height){const score=Math.min(f.width-item.width,f.height-item.height);if(!best||score<best.score)best={x:f.x,y:f.y,width:item.width,height:item.height,rot:false,data:item.data,score}}
      if(options.allowRotation&&item.height<=f.width&&item.width<=f.height){const score=Math.min(f.width-item.height,f.height-item.width);if(!best||score<best.score)best={x:f.x,y:f.y,width:item.height,height:item.width,rot:true,data:item.data,score}}
    }
    if(!best)return null;delete best.score;return best;
  }
  function splitFree(free,r){const out=[];for(const f of free){if(r.x>=f.x+f.width||r.x+r.width<=f.x||r.y>=f.y+f.height||r.y+r.height<=f.y){out.push(f);continue}if(r.x>f.x)out.push({x:f.x,y:f.y,width:r.x-f.x,height:f.height});if(r.x+r.width<f.x+f.width)out.push({x:r.x+r.width,y:f.y,width:f.x+f.width-r.x-r.width,height:f.height});if(r.y>f.y)out.push({x:f.x,y:f.y,width:f.width,height:r.y-f.y});if(r.y+r.height<f.y+f.height)out.push({x:f.x,y:r.y+r.height,width:f.width,height:f.y+f.height-r.y-r.height})}return out}
  function prune(rs){for(let i=rs.length-1;i>=0;i--)for(let j=rs.length-1;j>=0;j--)if(i!==j&&contains(rs[j],rs[i])){rs.splice(i,1);break}return rs}
  function contains(a,b){return b.x>=a.x&&b.y>=a.y&&b.x+b.width<=a.x+a.width&&b.y+b.height<=a.y+a.height}
  g.MaxRectsPacker={MaxRectsPacker:Packer};
})(window);
