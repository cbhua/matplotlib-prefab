/** Descriptive bar-space interface. Geometry cannot measure scientific information.
 * Keep category count separate from filled area and physical spacing. No new
 * sparse/low-information verdict is derived from these values by default.
 */
const PT_PER_MM=72/25.4;
export function measureBarDistribution(svg,g,{columns=8,rows=6}={}){
  const nodes=[...svg.querySelectorAll('.data > .data-bar')];
  if(!nodes.length)return null;
  const width=g.right-g.left,height=g.bottom-g.top;
  if(!(width>0&&height>0))return {status:'not_checked',reason:'No plot area.'};
  const rects=nodes.map(n=>{
    const x=Math.max(g.left,+n.getAttribute('x')),y=Math.max(g.top,+n.getAttribute('y'));
    const right=Math.min(g.right,+n.getAttribute('x')+(+n.getAttribute('width')));
    const bottom=Math.min(g.bottom,+n.getAttribute('y')+(+n.getAttribute('height')));
    return {x,y,width:Math.max(0,right-x),height:Math.max(0,bottom-y)};
  });
  const visible=rects.filter(r=>r.width>0&&r.height>0);
  const area=width*height,filled=visible.reduce((sum,r)=>sum+r.width*r.height,0);
  const bands=(count,horizontal)=>Array.from({length:count},(_,i)=>{
    const start=(horizontal?g.left:g.top)+i*(horizontal?width:height)/count;
    const end=start+(horizontal?width:height)/count;
    const ink=visible.reduce((sum,r)=>sum+Math.max(0,Math.min(end,(horizontal?r.x+r.width:r.y+r.height))-Math.max(start,horizontal?r.x:r.y))*(horizontal?r.height:r.width),0);
    return ink/(area/count);
  });
  let cursor=g.left,maxGap=0,occupied=0;
  for(const r of [...visible].sort((a,b)=>a.x-b.x)){
    maxGap=Math.max(maxGap,r.x-cursor);const end=r.x+r.width;
    occupied+=Math.max(0,end-Math.max(cursor,r.x));cursor=Math.max(cursor,end);
  }
  maxGap=Math.max(maxGap,g.right-cursor);
  return {status:'measured',method:'clipped-bar-rectangles',category_count:nodes.length,nonzero_bar_count:visible.length,
    plot_width_mm:width/PT_PER_MM,plot_height_mm:height/PT_PER_MM,plot_area_mm2:area/PT_PER_MM**2,
    area_per_category_mm2:area/PT_PER_MM**2/nodes.length,categories_per_1000mm2:nodes.length/(area/PT_PER_MM**2)*1000,
    width_per_category_mm:width/PT_PER_MM/nodes.length,categories_per_100mm:nodes.length/(width/PT_PER_MM)*100,
    bar_fill_fraction:filled/area,occupied_x_fraction:occupied/width,maximum_horizontal_gap_mm:maxGap/PT_PER_MM,
    top_empty_mm:(visible.length?Math.min(...visible.map(r=>r.y))-g.top:height)/PT_PER_MM,
    horizontal_load:bands(columns,true),vertical_load:bands(rows,false),
    interpretation:'Space distribution, not information content. Few categories and zero values can be scientifically meaningful; preserve values and the zero baseline.'};
}
