/** Browser counterpart of the public figure spec contract; never edits data. */
const common=['schema_version','kind','x_label','y_label','title'];
const object=value=>value!==null && typeof value==='object' && !Array.isArray(value);
const fail=message=>{throw new Error(message);};
const keys=(value,allowed,where)=>{const unknown=Object.keys(value).filter(k=>!allowed.includes(k));if(unknown.length)fail(`${where}: unknown field ${unknown[0]}.`);};
const numbers=(value,where)=>{if(!Array.isArray(value)||!value.length||value.some(v=>typeof v!=='number'||!Number.isFinite(v)))fail(`${where} must be a non-empty array of finite numbers.`);};
export function validateFigureSpec(spec,{grid=true}={}){
  if(!object(spec))fail('The figure spec must be a JSON object.');
  if(spec.schema_version!=='1')fail('spec.schema_version must be "1".');
  if(spec.kind==='grid' && grid){
    keys(spec,['schema_version','kind','rows','columns','panels'],'spec');
    if(![spec.rows,spec.columns].every(v=>Number.isInteger(v)&&v>=1&&v<=4))fail('Grid rows and columns must be integers from 1 to 4.');
    if(!Array.isArray(spec.panels)||spec.panels.length!==spec.rows*spec.columns)fail('Grid panel count must equal rows × columns.');
    spec.panels.forEach((panel,i)=>{try{validateFigureSpec(panel,{grid:false});}catch(error){fail(`Panel ${i+1}: ${error.message}`);}});
    return spec;
  }
  if(!['line','bar','scatter'].includes(spec.kind))fail('Supported single-panel kinds: line, bar, scatter.');
  keys(spec,[...common,...(spec.kind==='bar'?['categories','values']:['x','series'])],'spec');
  for(const field of ['x_label','y_label'])if(typeof spec[field]!=='string')fail(`spec.${field} must be a string.`);
  if(spec.title!==undefined && spec.title!==null && typeof spec.title!=='string')fail('spec.title must be a string or null.');
  if(spec.kind==='bar'){
    if(!Array.isArray(spec.categories)||!spec.categories.length||spec.categories.some(s=>typeof s!=='string'||!s.trim()))fail('spec.categories must contain non-empty names.');
    if(new Set(spec.categories).size!==spec.categories.length)fail('Category names must be unique.');
    numbers(spec.values,'spec.values');
    if(spec.values.length!==spec.categories.length)fail('Bar values must have the same length as categories.');
  }else{
    numbers(spec.x,'spec.x');
    if(!Array.isArray(spec.series)||!spec.series.length)fail('spec.series must be a non-empty array.');
    const names=new Set();
    for(const [i,series] of spec.series.entries()){
      if(!object(series))fail(`spec.series[${i}] must be an object.`);
      keys(series,['name','y'],`spec.series[${i}]`);
      if(typeof series.name!=='string'||!series.name.trim())fail(`spec.series[${i}].name must be a non-empty string.`);
      if(names.has(series.name))fail('Series names must be unique.');names.add(series.name);
      numbers(series.y,`spec.series[${i}].y`);
      if(series.y.length!==spec.x.length)fail(`spec.series[${i}].y must have the same length as x.`);
    }
  }
  return spec;
}
