/** UI-only translations. Paper prose, SVG labels and agent payloads stay English. */
const zh={
'Figure studio':'科研图表工作台','Figure setup':'图表配置','Loading templates…':'正在加载模板…','Set up your figure':'配置你的图表','Paper template':'论文模板','Panel layout':'子图排布','Column width':'栏宽','Single Column':'单栏','Double Column':'双栏','Preparing…':'正在准备…','Create figure':'创建图表',
'Starting…':'正在启动…','Connecting to the figure renderer…':'正在加载图表绘制器…','This configuration could not be drawn.':'无法绘制当前配置。','Could not load this example.':'无法加载此示例。','The outline renderer failed to start.':'图表绘制器启动失败。','Zoom':'缩放','Retry':'重试','Paper page preview':'论文预览','Figure warnings':'图表警告','Style controls':'样式设置','Hand off':'交接给 Agent','🤖 Copy for Agents':'🤖 复制给 Agent','Copied!':'已复制！','Figure instructions copied to clipboard.':'图表说明已复制到剪贴板。','Hand-off text':'交接说明','Figure content':'图表内容','Example data':'示例数据','Imported data':'导入的数据','Illustrative values for choosing scale and style.':'用于选择尺寸和样式的示例数据。','Panel':'子图','Example':'示例','Choose example…':'选择示例…','line — three series':'折线图 — 三组数据','line — one series':'折线图 — 单组数据','line — many series':'折线图 — 多组数据','bar — crossing zero':'柱状图 — 含正负值','bar — positive':'柱状图 — 正值','scatter — two groups':'散点图 — 两组数据','Import spec':'导入配置','Choose file…':'选择文件…','Figure size':'图表尺寸','Reset size':'重置尺寸','Figure width':'图表宽度','Figure height':'图表高度','Shared style':'统一样式','Undo':'撤销','Reset all':'全部重置','Applies to every panel. A dot marks a setting you have changed.':'应用于所有子图。圆点表示已修改的设置。',
'Type size':'字号','Type weight':'字重','Lines and markers':'线条与标记','Axes and grid':'坐标轴与网格','Bars':'柱形','X axis label':'X 轴标题','Y axis label':'Y 轴标题','X tick labels':'X 轴刻度文字','Y tick labels':'Y 轴刻度文字','Legend':'图例','Title':'标题','Data lines':'数据线','Axis spines':'坐标轴线','Tick marks':'刻度线','Tick length':'刻度长度','Tick label gap':'刻度文字间距','Marker size':'标记大小','Markers per series':'每组标记数量','X tick count':'X 轴刻度数量','Y tick count':'Y 轴刻度数量','Grid opacity':'网格不透明度','Grid line width':'网格线宽','X data margin':'X 轴数据留白','Y data margin':'Y 轴数据留白','Bar width':'柱形宽度','Bar edge':'柱形边线','Zero line':'零值线','Category label angle':'类别文字角度','normal':'常规','medium':'中等','semibold':'半粗','bold':'粗体','max':'上限','of slot':'占比','Reset':'重置','Changed from the profile default':'已修改默认设置',
'✅ Nice figure!':'✅ 图表状态良好！','Checking figure…':'正在检查图表…','⚠️ Fix figure settings.':'⚠️ 请修正图表设置。','No warnings from the current checks':'当前检查未发现警告','Current figure warnings':'当前图表警告','Adjust setting':'调整设置',
'Figure may be oversized':'图表可能过大，空间利用率偏低','Text overlap':'文字重叠','Text outside figure':'文字超出图表','Text too small':'文字过小','Lines may disappear in print':'线条打印后可能不清晰','Labels crowd the plot':'文字挤占绘图区','Markers are invisible':'数据标记不可见','Figure reaches the page margin':'图表延伸至页边距','Figure exceeds text width':'图表超出正文宽度','Body text is squeezed':'环绕正文过窄','Figure overlaps body text':'图表与正文重叠','Figure text is small beside prose':'图中文字相对正文过小','Figure text dominates the page':'图中文字相对正文过大',
'The figure and caption extend below the text area. Reduce figure height to keep them clear of the footer.':'图表和图注超出了正文底部。请减小图表高度，避免进入页脚。','The figure extends beyond the template text block. Reduce its width.':'图表超出了模板正文区域，请减小宽度。','The figure or caption intersects surrounding text. Reduce the figure width or height.':'图表或图注与正文重叠，请减小宽度或高度。','Less than 20% of this panel is available for data. Increase the figure size or reduce oversized labels.':'数据绘图区不足子图面积的 20%。请增大图表，或减小过大的文字。','Marker size is zero, so the scatter data cannot be seen.':'标记大小为零，散点数据不可见。',
};
const patterns=[
 [/^A contiguous empty region occupies about (\d+)% of the plotting area\. Consider reducing figure height or width while keeping labels readable\. This is a spacing heuristic, not a measure of scientific value\.$/,(_,n)=>`一块连续空白约占绘图区的 ${n}%。建议在保持文字清晰的前提下，适当减小图表高度或宽度。这只是空间利用率的启发式判断，不评价科研信息的价值。`],
 [/^(\d+(?:\.\d+)?)\s*(max|of slot)$/,(_,n,u)=>`${n} ${translate(u)}`],
 [/^⚠️ There (?:is|are) (\d+) warnings?\.$/,(_,n)=>`⚠️ 有 ${n} 项警告。`],
 [/^Panel (\d+) · (line|bar|scatter)$/,(_,n,k)=>`子图 ${n} · ${{line:'折线图',bar:'柱状图',scatter:'散点图'}[k]}`],
 [/^Panel (\d+): ([\s\S]+)$/,(_,n,s)=>`子图 ${n}：${translate(s)}`],
 [/^(\d+) label\(s\) are below ([\d.]+) pt at print size\.$/,(_,n,p)=>`${n} 处文字的打印字号小于 ${p} pt。`],
 [/^(\d+) label\(s\) extend beyond the canvas\. Increase the figure size\.$/,(_,n)=>`${n} 处文字超出画布，请增大图表尺寸。`],
 [/^Some data lines or axes are thinner than ([\d.]+) pt\. Review them at print size\.$/,(_,n)=>`部分数据线或坐标轴线小于 ${n} pt，请按打印尺寸检查。`],
 [/^Only ([\d.]+) mm remains beside the figure\. Aim for at least ([\d.]+) mm of readable body text\.$/,(_,a,b)=>`图表旁仅剩 ${a} mm 正文宽度，建议至少保留 ${b} mm。`],
 [/^The smallest figure text is ([\d.]+) pt beside ([\d.]+) pt body text\. Consider increasing the smaller labels\.$/,(_,a,b)=>`最小图中文字为 ${a} pt，正文为 ${b} pt。建议增大小号文字。`],
 [/^Figure labels reach ([\d.]+) pt beside ([\d.]+) pt body text\. Check the balance at the intended print size\.$/,(_,a,b)=>`图中文字达到 ${a} pt，正文为 ${b} pt。请检查打印尺寸下的视觉比例。`],
 [/^([\s\S]+)\. Widen the figure or reduce the label size\.$/,(_,s)=>`${s}。请加宽图表或减小文字。`],
 [/^(.+) slider$/,(_,s)=>`${translate(s)}滑块`], [/^(.+) weight$/,(_,s)=>`${translate(s)}字重`],
 [/^Reset (.+) to the profile value$/,(_,s)=>`将${translate(s)}恢复为默认值`],
 [/^Could not import (.+)\.$/,(_,s)=>`无法导入 ${s}。`],
 [/^The browser refused clipboard access \(([\s\S]+)\)\. Select the text below instead\.$/,(_,s)=>`浏览器未允许访问剪贴板（${s}），请手动选择并复制下方文本。`],
];
function translate(s){if(zh[s])return zh[s];for(const [re,fn] of patterns)if(re.test(s))return s.replace(re,fn);if(s.startsWith('⚠️ '))return '⚠️ '+translate(s.slice(3));return s;}
export function initLanguage(){
 let language='en';try{language=localStorage.getItem('figure-studio-language')||'en';}catch{}
 const picker=document.querySelector('#ui-language');language=language==='zh'?'zh':'en';
 const roots=[...document.querySelectorAll('#setup,.side,#warning-rail,.preview-tools,#status,#paper-overflow')];
 const originals=new WeakMap();
 const observe=()=>roots.forEach(root=>observer.observe(root,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['aria-label','aria-valuetext','title']}));
 function apply(){
  observer.disconnect();
  picker.dataset.language=language;
  picker.setAttribute('aria-label',language==='zh'?'Switch to English':'切换为中文');picker.title=picker.getAttribute('aria-label');
  document.documentElement.lang=language==='zh'?'zh-CN':'en';document.title=language==='zh'?zh['Figure studio']:'Figure studio';
  const localize=(node,key,value,set)=>{let record=originals.get(node);if(!record){record={};originals.set(node,record);}let item=record[key];if(!item||value!==item.output)item=record[key]={input:value};const input=item.input;const trimmed=input.trim();const output=language==='zh'?input.replace(trimmed,translate(trimmed)):input;item.output=output;if(value!==output)set(output);};
  for(const root of roots){const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;while(n=walker.nextNode()){if(n.parentElement.closest('textarea,svg'))continue;const text=n;localize(text,'text',text.nodeValue,v=>text.nodeValue=v);}
   for(const node of [root,...root.querySelectorAll('[aria-label],[aria-valuetext],[title]')])for(const key of ['aria-label','aria-valuetext','title'])if(node.hasAttribute(key))localize(node,key,node.getAttribute(key),v=>node.setAttribute(key,v));
  }observe();
 }
 const observer=new MutationObserver(apply);
 picker.addEventListener('click',()=>{language=language==='zh'?'en':'zh';try{localStorage.setItem('figure-studio-language',language);}catch{}apply();});apply();
}
