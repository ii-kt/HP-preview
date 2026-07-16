const PAL_ICON_BASE="https://raw.githubusercontent.com/tylercamp/palcalc/8b7e2f779e47fddae16ddcb973e828ba20c02b80/PalCalc.UI/Resources/Pals/";
function initials(p){return (p.jp||p.en).replace(/[（）()・\s]/g,"").slice(0,2)}
function iconUrl(p){return PAL_ICON_BASE+encodeURIComponent(p.en)+".png"}
function mark(p,sm=false){
 if(!p)return `<span class="palmark ${sm?"sm":""} placeholder"><span class="palmark-fallback">?</span></span>`;
 return `<span class="palmark ${sm?"sm":""}"><img src="${esc(iconUrl(p))}" alt="${esc(p.jp)}" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="palmark-fallback" hidden>${esc(initials(p))}</span></span>`;
}
function palHTML(p,sm=true){return `<div class="pal-inline">${mark(p,sm)}<div style="min-width:0"><strong>${esc(p.jp)}</strong><div class="enname">${esc(p.en)} · No.${String(p.no).padStart(3,"0")}${p.variant?"B":""}</div></div></div>`}
function slotHTML(p,label){
 return p?`${mark(p)}<div class="jpname">${esc(p.jp)}</div><div class="enname">${esc(p.en)}</div><div class="no">No.${String(p.no).padStart(3,"0")}${p.variant?"B":""}　配合値 ${p.power}</div>`
 :`${mark(null)}<div class="jpname">${label}</div><div class="enname">タップして検索</div>`;
}
function multiResultSlotHTML(results){
 const icons=results.map(r=>mark(r.child,true)).join("");
 return `<div style="display:flex;gap:8px;justify-content:center;align-items:center">${icons}</div><div class="jpname">性別で${results.length}通り</div><div class="enname">下の条件別結果を確認してください</div>`;
}
function pickButtonHTML(p,label){return p?`${mark(p,true)}<span class="grow"><small>${label}</small><strong>${esc(p.jp)}</strong><small>${esc(p.en)} · No.${p.no}${p.variant?"B":""}</small></span><b>変更</b>`:`${mark(null,true)}<span class="grow"><small>${label}</small><strong>パルを選択</strong><small>日本語名・番号で検索</small></span><b>選択</b>`}
function resultRow(r){
 return `<article class="result-row">${palHTML(r.first)}<span class="arrow">＋</span>${palHTML(r.second)}<span class="arrow">→</span>${palHTML(r.child)}<div class="note">${esc(r.note||"")}</div></article>`;
}
function getResults(a,b){return a&&b?(pairMap.get(pairKey(a.uid,b.uid))||[]):[]}
function renderParents(){
 $("#parentA").innerHTML=slotHTML(selected.a,"親Aを選択");$("#parentB").innerHTML=slotHTML(selected.b,"親Bを選択");
 const rs=getResults(selected.a,selected.b);
 $("#childSlot").innerHTML=rs.length===1
  ?slotHTML(rs[0].child,"子パル")
  :rs.length>1
   ?multiResultSlotHTML(rs)
   :`${mark(null)}<div class="jpname">結果</div><div class="enname">親を2体選択</div>`;
 $("#parentResults").innerHTML=rs.length>1?rs.map(resultRow).join(""):"";
}
function searchable(p,q){q=q.trim().toLowerCase();return !q||p.jp.toLowerCase().includes(q)||p.en.toLowerCase().includes(q)||String(p.no).includes(q)}
function renderTarget(){
 $("#targetPick").innerHTML=pickButtonHTML(selected.target,"作りたいパル");
 let list=selected.target?[...(parentsByChild.get(selected.target.uid)||[])]:[];
 const q=$("#targetFilter").value||"";list=list.filter(r=>searchable(r.first,q)||searchable(r.second,q));
 const sort=$("#targetSort").value;
 list.sort((x,y)=>sort==="name"?x.first.jp.localeCompare(y.first.jp,"ja"):sort==="power"?x.first.power-y.first.power:palSort(x.first,y.first)||palSort(x.second,y.second));
 $("#targetCount").textContent=selected.target?`${list.length.toLocaleString()}組`:"";
 $("#targetResults").innerHTML=list.length?list.slice(0,1200).map(resultRow).join(""):`<div class="empty">${selected.target?"該当する親候補がありません":"作りたいパルを選択してください"}</div>`;
}
function renderOffspring(){
 $("#singleParentPick").innerHTML=pickButtonHTML(selected.parent,"基準にする親");
 let list=selected.parent?[...(offspringByParent.get(selected.parent.uid)||[])]:[];
 const q=$("#offspringFilter").value||"";list=list.filter(r=>searchable(r.partner,q)||searchable(r.child,q));
 const sort=$("#offspringSort").value;
 list.sort((x,y)=>sort==="partner"?palSort(x.partner,y.partner):sort==="name"?x.child.jp.localeCompare(y.child.jp,"ja"):palSort(x.child,y.child)||palSort(x.partner,y.partner));
 $("#offspringCount").textContent=selected.parent?`${list.length.toLocaleString()}件`:"";
 $("#offspringResults").innerHTML=list.length?list.slice(0,1200).map(r=>resultRow({first:selected.parent,second:r.partner,child:r.child,note:r.note})).join(""):`<div class="empty">${selected.parent?"結果がありません":"親パルを選択してください"}</div>`;
}
function renderDex(){
 let list=[...pals],q=$("#dexSearch").value||"",v=$("#dexVariant").value,el=$("#dexElement").value,w=$("#dexWork").value,l=+$("#dexWorkLevel").value;
 list=list.filter(p=>searchable(p,q)&&(v==="all"||(v==="variant")===p.variant)&&(!el||p.elements.includes(el))&&(!w||(+p.work[w]||0)>=l));
 const s=$("#dexSort").value;list.sort((a,b)=>s==="desc"?palSort(b,a):s==="jp"?a.jp.localeCompare(b.jp,"ja"):s==="power"?a.power-b.power:palSort(a,b));
 $("#dexCount").textContent=`${list.length}形態`;
 $("#dexGrid").innerHTML=list.map(p=>`<article class="pal-card">${mark(p,true)}<div style="min-width:0;flex:1"><strong>${esc(p.jp)}</strong><div class="enname">${esc(p.en)}</div><div class="no">No.${p.no}${p.variant?"B":""} · 配合値 ${p.power}</div><div class="tags">${p.elements.map(e=>`<span class="tag">${esc(ELEMENT_JP[e]||e)}</span>`).join("")}${Object.entries(p.work).filter(([,x])=>x).map(([k,x])=>`<span class="tag">${esc(WORK_JP[k]||k)}Lv.${x}</span>`).join("")}</div></div></article>`).join("");
}
function fillFilterOptions(){
 const elements=[...new Set(pals.flatMap(p=>p.elements))].sort(),works=[...new Set(pals.flatMap(p=>Object.keys(p.work)))].sort();
 for(const id of ["dexElement","pickerElement"]){const el=$("#"+id);el.innerHTML='<option value="">全属性</option>';for(const e of elements)el.insertAdjacentHTML("beforeend",`<option value="${esc(e)}">${esc(ELEMENT_JP[e]||e)}</option>`)}
 for(const id of ["dexWork","pickerWork"]){const el=$("#"+id);el.innerHTML='<option value="">全作業適性</option>';for(const w of works)el.insertAdjacentHTML("beforeend",`<option value="${esc(w)}">${esc(WORK_JP[w]||w)}</option>`)}
}
