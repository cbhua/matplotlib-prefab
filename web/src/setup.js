/** Single-page setup. All styling hooks live under #setup in design-overrides.css. */
export function createSetup(root,index,onGenerate,onCancel) {
  const venues=[...new Map(index.pages.map(p=>[p.venue,{id:p.venue,name:p.name.replace(/\s*20\d\d/g,'')}])).values()];
  let draft={venue:null,rows:1,columns:1,layout:'narrow',kinds:['line']},busy=false,error='';
  const node=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls;if(text)n.textContent=text;return n;};
  function render(){
    const focused=document.activeElement?.dataset;const focusKey=focused&&['venue','grid','layout'].find(k=>focused[k]);const focusValue=focused?.[focusKey];
    root.replaceChildren();const card=node('section','setup-card');
    card.append(node('h1','','Set up your figure'));
    const section=(title,cls)=>{const s=node('section','setup-section');s.append(node('h2','',title));const choices=node('div',`setup-choices ${cls}`);s.append(choices);card.append(s);return choices;};
    const choice=(host,label,detail,key,value,selected,action)=>{const b=node('button','setup-choice');b.type='button';b.dataset[key]=value;b.setAttribute('aria-pressed',String(selected));b.disabled=busy;b.append(node('strong','',label));if(detail)b.append(node('span','',detail));b.onclick=()=>{action();render();};host.append(b);return b;};
    const templates=section('Paper template','template-choices');
    for(const v of venues)choice(templates,v.name,'','venue',v.id,draft.venue===v.id,()=>draft.venue=v.id);
    const grids=section('Panel layout','grid-choices');
    for(let rows=1;rows<=4;rows++)for(let columns=1;columns<=4;columns++){
      const b=choice(grids,`${rows} × ${columns}`,'','grid',`${rows}x${columns}`,draft.rows===rows&&draft.columns===columns,()=>{draft.rows=rows;draft.columns=columns;draft.kinds=Array(rows*columns).fill('line');});
      const icon=node('span','grid-icon');icon.style.gridTemplateColumns=`repeat(${columns},1fr)`;for(let i=0;i<rows*columns;i++)icon.append(node('i',''));b.prepend(icon);
    }
    const widths=section('Column width','width-choices');
    for(const layout of ['narrow','wide']){
      choice(widths,layout==='narrow'?'Single Column':'Double Column','','layout',layout,draft.layout===layout,()=>draft.layout=layout);
    }
    const message=node('p','setup-error',error);message.setAttribute('role','alert');card.append(message);
    const actions=node('div','setup-actions');const generate=node('button','primary-button',busy?'Preparing…':'Create figure');generate.id='setup-next';generate.disabled=busy||!draft.venue;
    generate.onclick=async()=>{busy=true;error='';render();try{await onGenerate(structuredClone(draft));}catch(e){error=e.message;}finally{busy=false;render();}};
    actions.append(generate);card.append(actions);root.append(card);
    if(focusKey)root.querySelector(`[data-${focusKey}="${focusValue}"]`)?.focus();
  }
  render();return {open(config){draft=structuredClone(config);render();}};
}
