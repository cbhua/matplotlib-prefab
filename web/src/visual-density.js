/** Print-space diagnostics, not a validated aesthetics or information score.
 * Raster ink is descriptive. Semantic mark overdraw and free space drive warnings.
 * References and threshold rationale: skills/scientific-figures/references/visual-density.md.
 */
import {measureFigureDensity} from './figure-density.js';
import {measureBarDistribution} from './bar-distribution.js';
export const VISUAL_DENSITY_RULES = {
  version: '1', dpi: 144, foregroundContrast: .08,
  minimumMarks: 20, minimumOverdraw: .25, minimumOverlappingMarks: .3,
};
const SCALE=VISUAL_DENSITY_RULES.dpi/72;

/** Foreground coverage and binary edge transitions on an opaque white canvas.
 * Contrast uses normalized sRGB luma (not linear-light luminance or CIELab).
 */
export function measurePixels(pixels,width,height) {
  const mask=new Uint8Array(width*height);let ink=0,contrast=0,edges=0,pairs=0;
  for(let i=0;i<mask.length;i++){
    const p=i*4,alpha=pixels[p+3]/255;
    const c=alpha*(1-(.2126*pixels[p]+.7152*pixels[p+1]+.0722*pixels[p+2])/255);
    contrast+=c;
    if(c>=VISUAL_DENSITY_RULES.foregroundContrast){mask[i]=1;ink++;}
  }
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const i=y*width+x;
    if(x){edges+=mask[i]!==mask[i-1];pairs++;}
    if(y){edges+=mask[i]!==mask[i-width];pairs++;}
  }
  return {ink_fraction:ink/mask.length,mean_contrast:contrast/mask.length,
    edge_transition_fraction:pairs?edges/pairs:0,width_px:width,height_px:height};
}

async function rasterInk(svg) {
  const vb=svg.viewBox.baseVal,width=Math.max(1,Math.ceil(vb.width*SCALE)),height=Math.max(1,Math.ceil(vb.height*SCALE));
  const clone=svg.cloneNode(true);clone.setAttribute('width',width);clone.setAttribute('height',height);
  // A colored canvas is not information. Normalize only the renderer's background.
  if(clone.firstElementChild?.tagName==='rect')clone.firstElementChild.setAttribute('fill','white');
  const image=new Image();let url;
  try {
    if(width*height>4000000)throw Error('Density raster exceeds the 4 megapixel limit.');
    url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:'image/svg+xml'}));
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(Error('Density rasterization timed out.')),3000);
      image.onload=()=>{clearTimeout(timer);resolve();};image.onerror=()=>{clearTimeout(timer);reject(Error('Density rasterization failed.'));};image.src=url;
    });
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.fillStyle='white';ctx.fillRect(0,0,width,height);ctx.drawImage(image,0,0,width,height);
    return {status:'measured',...measurePixels(ctx.getImageData(0,0,width,height).data,width,height)};
  } catch(error){return {status:'not_checked',reason:error.message};}
  finally{if(url)URL.revokeObjectURL(url);}
}

/** Exact filled marker footprints sampled at 144 dpi, clipped to the plot.
 * Count before compositing: identical opaque marks cannot hide their multiplicity.
 * Lines, bars, gridlines and legend handles cannot create marker-overdraw warnings.
 */
export function measureMarkOverlap(svg,g) {
  const markers=[...svg.querySelectorAll('.data > .data-marker')];
  const width=Math.max(1,Math.ceil((g.right-g.left)*SCALE)),height=Math.max(1,Math.ceil((g.bottom-g.top)*SCALE));
  if(!(g.right>g.left&&g.bottom>g.top))return {status:'not_checked',reason:'No plot area.'};
  const counts=new Uint32Array(width*height),owners=new Int32Array(width*height);owners.fill(-1);
  const overlaps=new Set();let area=0,union=0,multiple=0,visible=0;
  let left=width,top=height,right=0,bottom=0;
  const ctx=document.createElement('canvas').getContext('2d');
  const rootInverse=svg.getCTM().inverse();
  for(const [index,node] of markers.entries()){
    const matrix=rootInverse.multiply(node.getCTM()),box=node.getBBox();
    if(!box.width || !box.height || !Number.isFinite(matrix.a+matrix.d) || Math.abs(matrix.a*matrix.d-matrix.b*matrix.c)<1e-12)continue;
    const inverse=matrix.inverse();
    const corners=[[box.x,box.y],[box.x+box.width,box.y],[box.x,box.y+box.height],[box.x+box.width,box.y+box.height]].map(([x,y])=>new DOMPoint(x,y).matrixTransform(matrix));
    const x0=Math.max(0,Math.floor((Math.min(...corners.map(p=>p.x))-g.left)*SCALE));
    const x1=Math.min(width-1,Math.ceil((Math.max(...corners.map(p=>p.x))-g.left)*SCALE));
    const y0=Math.max(0,Math.floor((Math.min(...corners.map(p=>p.y))-g.top)*SCALE));
    const y1=Math.min(height-1,Math.ceil((Math.max(...corners.map(p=>p.y))-g.top)*SCALE));
    let path;
    if(node.tagName==='path')path=new Path2D(node.getAttribute('d'));
    else if(node.tagName==='circle'){path=new Path2D();path.arc(Number(node.getAttribute('cx')),Number(node.getAttribute('cy')),Number(node.getAttribute('r')),0,2*Math.PI);}
    else if(node.tagName==='rect'){path=new Path2D();path.rect(box.x,box.y,box.width,box.height);}
    else continue;
    let markArea=0;
    for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){
      const point=new DOMPoint(g.left+(x+.5)/SCALE,g.top+(y+.5)/SCALE).matrixTransform(inverse);
      if(!ctx.isPointInPath(path,point.x,point.y))continue;
      const i=y*width+x;markArea++;area++;
      if(!counts[i]){union++;owners[i]=index;}
      else {if(counts[i]===1)multiple++;overlaps.add(index);overlaps.add(owners[i]);left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x+1);bottom=Math.max(bottom,y+1);}
      counts[i]++;
    }
    if(markArea)visible++;
  }
  const overdraw=area?1-union/area:0,overlapping=visible?overlaps.size/visible:0;
  return {status:'measured',mark_count:markers.length,visible_mark_count:visible,
    overdraw_fraction:overdraw,overlapping_mark_fraction:overlapping,
    overlapped_ink_fraction:union?multiple/union:0,
    crowded:visible>=VISUAL_DENSITY_RULES.minimumMarks && overdraw>=VISUAL_DENSITY_RULES.minimumOverdraw && overlapping>=VISUAL_DENSITY_RULES.minimumOverlappingMarks,
    region:multiple?{x:g.left+left/SCALE,y:g.top+top/SCALE,width:(right-left)/SCALE,height:(bottom-top)/SCALE}:null};
}

export async function measureVisualDensity(svg,geometry) {
  return {ink:await rasterInk(svg),space:measureFigureDensity(svg,geometry),marks:measureMarkOverlap(svg,geometry),bar_distribution:measureBarDistribution(svg,geometry)};
}

const bodyCache=new Map();
/** A representative pure-prose strip, re-typeset at template column width.
 * This is deliberately not a screenshot/ink measurement of the whole article.
 * It excludes headings, captions, figures, page margins and UI backgrounds.
 */
export function measureBodyDensity(page,prose) {
  const size=page.preview_settings.body_size_pt,leading=page.preview_settings.body_leading_pt;
  const font=`${size*SCALE}px "${page.preset.font_family}"`;
  const width=Math.ceil(page.text_block.column_width_mm*72/25.4*SCALE),lines=16;
  const text=prose.split(/\n\s*\n/).filter(p=>!p.trim().startsWith('## ')).join(' ');
  const key=JSON.stringify([font,leading,width,text]);
  if(bodyCache.has(key))return bodyCache.get(key);
  if(!document.fonts.check(`${size}pt "${page.preset.font_family}"`))return {status:'not_checked',reason:'Template font is not loaded.'};
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=Math.ceil(lines*leading*SCALE);
  const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.font=font;ctx.fillStyle='black';
  const metrics=ctx.measureText('Ag');
  const baseline=(leading*SCALE+metrics.actualBoundingBoxAscent-metrics.actualBoundingBoxDescent)/2;
  const words=text.split(/\s+/).filter(Boolean);let word=0;
  if(!words.length)return {status:'not_checked',reason:'No body prose.'};
  for(let line=0;line<lines;line++){
    let value=words[word++%words.length];
    while(word<words.length*100){const next=words[word%words.length];if(ctx.measureText(value+' '+next).width>width)break;value+=' '+next;word++;}
    ctx.fillText(value,0,line*leading*SCALE+baseline);
  }
  const result={status:'measured',method:'representative-prose-strip',lines,dpi:VISUAL_DENSITY_RULES.dpi,
    font_family:page.preset.font_family,font_size_pt:size,leading_pt:leading,column_width_mm:page.text_block.column_width_mm,
    ...measurePixels(ctx.getImageData(0,0,canvas.width,canvas.height).data,canvas.width,canvas.height)};
  bodyCache.set(key,result);return result;
}

export function densityContext(report,page,prose) {
  const body=measureBodyDensity(page,prose);
  return {...report.visual_density,body_reference:body,
    limitations:['No universal aesthetics score','No full Feature Congestion or Subband Entropy model','No line-line occlusion analysis','Body reference is re-typeset prose, not a screenshot'],
    interpretation:'Descriptive print-space diagnostics; body ink is context, not an optimal target. Thresholds are uncalibrated project heuristics, not venue rules.',
    comparisons:(report.visual_density?.panels||[]).map(p=>({panel_index:p.panel_index,
      ink_to_body_ratio:p.ink.status==='measured'&&body.status==='measured'&&body.ink_fraction>0?p.ink.ink_fraction/body.ink_fraction:null}))};
}
