/** Legend exclusion-zone collisions in physical SVG coordinates.
 * Render data on its own: an opaque legend must not hide the evidence being tested.
 * The legend's layout rectangle is reserved even when its frame is disabled.
 */
export const LEGEND_OVERLAP_RULES = {dpi:288,minimumAlpha:16};
const SCALE=LEGEND_OVERLAP_RULES.dpi/72;

function rootBounds(node,inverse){
  const b=node.getBBox(),m=inverse.multiply(node.getCTM());
  const points=[[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]]
    .map(([x,y])=>new DOMPoint(x,y).matrixTransform(m));
  const x=Math.min(...points.map(p=>p.x)),y=Math.min(...points.map(p=>p.y));
  return {x,y,width:Math.max(...points.map(p=>p.x))-x,height:Math.max(...points.map(p=>p.y))-y};
}
function intersection(a,b){
  const x=Math.max(a.x,b.x),y=Math.max(a.y,b.y),right=Math.min(a.x+a.width,b.x+b.width),bottom=Math.min(a.y+a.height,b.y+b.height);
  return right>x&&bottom>y?{x,y,width:right-x,height:bottom-y}:null;
}
function shape(node){
  if(node.tagName==='path')return new Path2D(node.getAttribute('d'));
  const path=new Path2D();
  if(node.tagName==='rect')path.rect(+node.getAttribute('x'),+node.getAttribute('y'),+node.getAttribute('width'),+node.getAttribute('height'));
  else if(node.tagName==='circle')path.arc(+node.getAttribute('cx'),+node.getAttribute('cy'),+node.getAttribute('r'),0,Math.PI*2);
  else return null;
  return path;
}
export function measureLegendOverlap(svg,geometry){
  const legend=svg.querySelector('.legend');
  if(!legend || !geometry)return null;
  const inverse=svg.getCTM().inverse(),bounds=rootBounds(legend,inverse);
  const plot={x:geometry.left,y:geometry.top,width:geometry.right-geometry.left,height:geometry.bottom-geometry.top};
  const region=intersection(bounds,plot);
  if(!region)return null;
  const width=Math.ceil(region.width*SCALE),height=Math.ceil(region.height*SCALE);
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const ctx=canvas.getContext('2d',{willReadFrequently:true}),union=new Uint8Array(width*height);
  const hits={lines:0,markers:0,bars:0},series=new Set();let ink=0;
  let left=width,top=height,right=0,bottom=0;
  for(const node of svg.querySelectorAll('.data > .data-line,.data > .data-marker,.data > .data-bar')){
    const style=getComputedStyle(node);
    if(Number(style.opacity)===0 || style.display==='none')continue;
    const stroke=style.stroke!=='none'&&Number(style.strokeOpacity)>0?parseFloat(style.strokeWidth):0;
    const box=rootBounds(node,inverse);
    // A broad phase only; actual strokes/marker paths, not these boxes, decide hits.
    const expanded={x:box.x-stroke/2,y:box.y-stroke/2,width:box.width+stroke,height:box.height+stroke};
    if(!intersection(expanded,region))continue;
    const path=shape(node);if(!path)continue;
    ctx.resetTransform();ctx.clearRect(0,0,width,height);ctx.save();
    ctx.setTransform(SCALE,0,0,SCALE,-region.x*SCALE,-region.y*SCALE);
    ctx.beginPath();ctx.rect(region.x,region.y,region.width,region.height);ctx.clip();
    const m=inverse.multiply(node.getCTM());ctx.transform(m.a,m.b,m.c,m.d,m.e,m.f);
    if(style.fill!=='none'&&Number(style.fillOpacity)>0){
      ctx.globalAlpha=Number(style.opacity)*Number(style.fillOpacity);ctx.fillStyle=style.fill;
      ctx.fill(path,style.fillRule);
    }
    if(stroke>0){
      ctx.globalAlpha=Number(style.opacity)*Number(style.strokeOpacity);ctx.strokeStyle=style.stroke;ctx.lineWidth=stroke;
      ctx.lineCap=style.strokeLinecap;ctx.lineJoin=style.strokeLinejoin;
      ctx.setLineDash(style.strokeDasharray==='none'?[]:style.strokeDasharray.split(/[ ,]+/).map(parseFloat));
      ctx.lineDashOffset=parseFloat(style.strokeDashoffset)||0;ctx.stroke(path);
    }
    ctx.restore();
    const pixels=ctx.getImageData(0,0,width,height).data;let hit=false;
    for(let i=0;i<union.length;i++)if(pixels[i*4+3]>=LEGEND_OVERLAP_RULES.minimumAlpha){
      hit=true;
      if(!union[i]){union[i]=1;ink++;const x=i%width,y=Math.floor(i/width);left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x+1);bottom=Math.max(bottom,y+1);}
    }
    if(hit){hits[node.classList.contains('data-line')?'lines':node.classList.contains('data-marker')?'markers':'bars']++;if(node.hasAttribute('data-series'))series.add(Number(node.dataset.series));}
  }
  return {overlaps:ink>0,method:'isolated-data-in-legend-exclusion-zone',dpi:LEGEND_OVERLAP_RULES.dpi,
    legend_bounds:bounds,overlap_area_pt2:ink/SCALE**2,affected_primitives:hits,series_indices:[...series].sort((a,b)=>a-b),
    data_overlap_region:ink?{x:region.x+left/SCALE,y:region.y+top/SCALE,width:(right-left)/SCALE,height:(bottom-top)/SCALE}:null};
}
