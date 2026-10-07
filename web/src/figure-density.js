/** Spatial occupancy, not scientific information content. All geometry is in pt.
 * Ignore axes/grid ink; reserve breathing room around data and the legend.
 * Evaluate panels independently so adding panels does not create false sparsity.
 */
export const DENSITY_RULES = {
  columns: 48, rows: 36, breathingRoomMm: 3,
  minimumPlotAreaMm2: 5000, minimumEmptyFraction: .65,
  minimumEmptyRectangleFraction: .24, minimumEmptyRectangleMm2: 1800,
  minimumEmptySideMm: 20,
};
const PT_PER_MM=72/25.4;
export function measureFigureDensity(svg,g,rules=DENSITY_RULES){
  const {columns:cols,rows}=rules,w=g.right-g.left,h=g.bottom-g.top;
  if(!(w>0&&h>0))return null;
  const cells=new Uint8Array(cols*rows),dx=w/cols,dy=h/rows;
  const radius=rules.breathingRoomMm*PT_PER_MM;
  const occupy=(x0,y0,x1,y1)=>{
    const left=Math.max(0,Math.floor((x0-g.left)/dx)),right=Math.min(cols-1,Math.floor((x1-g.left)/dx));
    const top=Math.max(0,Math.floor((y0-g.top)/dy)),bottom=Math.min(rows-1,Math.floor((y1-g.top)/dy));
    for(let y=top;y<=bottom;y++)for(let x=left;x<=right;x++)cells[y*cols+x]=1;
  };
  // Native chart data paths contain straight segments. Dense sampling includes
  // the whole line, not just markers (which may be intentionally thinned).
  for(const path of svg.querySelectorAll('.data-line')){
    if(Number(path.getAttribute('stroke-width'))<=0)continue;
    const length=path.getTotalLength(),steps=Math.max(1,Math.ceil(length/Math.max(1,Math.min(dx,dy))));
    const pad=radius+Number(path.getAttribute('stroke-width'))/2;
    for(let i=0;i<=steps;i++){const p=path.getPointAtLength(length*i/steps);occupy(p.x-pad,p.y-pad,p.x+pad,p.y+pad);}
  }
  const inverse=svg.getCTM().inverse();
  for(const node of svg.querySelectorAll('.data-marker,.data-bar,.legend')){
    const b=node.getBBox(),matrix=inverse.multiply(node.getCTM());
    const points=[[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]].map(([x,y])=>new DOMPoint(x,y).matrixTransform(matrix));
    occupy(Math.min(...points.map(p=>p.x))-radius,Math.min(...points.map(p=>p.y))-radius,Math.max(...points.map(p=>p.x))+radius,Math.max(...points.map(p=>p.y))+radius);
  }
  // Largest all-empty rectangle in a binary grid, using histogram stacks.
  const heights=new Uint16Array(cols);let best={x:0,y:0,width:0,height:0},area=0;
  for(let y=0;y<rows;y++){
    for(let x=0;x<cols;x++)heights[x]=cells[y*cols+x]?0:heights[x]+1;
    const stack=[];
    for(let x=0;x<=cols;x++){
      const current=x===cols?0:heights[x];let start=x;
      while(stack.length&&stack.at(-1).height>current){const item=stack.pop();const a=item.height*(x-item.start);if(a>area){area=a;best={x:item.start,y:y-item.height+1,width:x-item.start,height:item.height};}start=item.start;}
      if(current && (!stack.length||stack.at(-1).height<current))stack.push({start,height:current});
    }
  }
  const plotAreaMm2=w*h/PT_PER_MM**2,occupied=cells.reduce((a,b)=>a+b,0);
  const emptyFraction=1-occupied/cells.length,rectangleFraction=area/cells.length;
  const region={x:g.left+best.x*dx,y:g.top+best.y*dy,width:best.width*dx,height:best.height*dy};
  const rectangleMm2=region.width*region.height/PT_PER_MM**2;
  const oversized=plotAreaMm2>=rules.minimumPlotAreaMm2 && emptyFraction>=rules.minimumEmptyFraction && rectangleFraction>=rules.minimumEmptyRectangleFraction && rectangleMm2>=rules.minimumEmptyRectangleMm2 && Math.min(region.width,region.height)/PT_PER_MM>=rules.minimumEmptySideMm;
  return {oversized,occupied_fraction:1-emptyFraction,empty_fraction:emptyFraction,plot_area_mm2:plotAreaMm2,largest_empty_rectangle_fraction:rectangleFraction,largest_empty_rectangle_mm2:rectangleMm2,region};
}
