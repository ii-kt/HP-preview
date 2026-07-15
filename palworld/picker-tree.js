function openPicker(cb){
 if(!pals.length){toast("データを読み込んでいます");return}
 pickerCallback=cb;$("#pickerSearch").value="";$("#pickerModal").classList.add("open");renderPicker();setTimeout(()=>$("#pickerSearch").focus(),30);
}
function closePicker(){$("#pickerModal").classList.remove("open");pickerCallback=null}
function pickerFiltered(){
 const q=$("#pickerSearch").value||"",v=$("#pickerVariant").value,el=$("#pickerElement").value,w=$("#pickerWork").value,l=+$("#pickerLevel").value,s=$("#pickerSort").value;
 let list=pals.filter(p=>searchable(p,q)&&(v==="all"||(v==="variant")===p.variant)&&(!el||p.elements.includes(el))&&(!w||(+p.work[w]||0)>=l));
 list.sort((a,b)=>s==="desc"?palSort(b,a):s==="jp"?a.jp.localeCompare(b.jp,"ja"):palSort(a,b));return list;
}
function renderPicker(){
 const list=pickerFiltered();
 $("#pickerList").innerHTML=list.map(p=>`<button class="picker-item" data-id="${esc(p.uid)}">${mark(p,true)}<span style="min-width:0"><strong>${esc(p.jp)}</strong><small class="enname">${esc(p.en)} · No.${p.no}${p.variant?"B":""} · 配合値${p.power}</small></span></button>`).join("");
}
function toast(msg){const t=$("#toast");t.textContent=msg;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),1800)}
function renderTree(){
 const canvas=$("#treeCanvas");if(!selected.tree){canvas.innerHTML=`<div class="empty" style="width:420px">起点パルを選択してください</div>`;return}
 const depth=+$("#treeDepth").value;
 canvas.innerHTML=treeOrientation==="result"?ancestorNode(selected.tree,0,depth,"r"):descendantNode(selected.tree,0,depth,"d");
 applyTreeTransform();
}
function nodeCard(p,pairs,path){
 const idx=Math.min(treeSelections.get(path)||0,Math.max(0,pairs.length-1));treeSelections.set(path,idx);
 return `<div class="tree-node">${palHTML(p,true)}<div class="no" style="text-align:center;margin-top:4px">配合値 ${p.power}</div>${pairs.length?`<div class="combo-nav"><button data-nav="${path}" data-d="-1">‹</button><span>${idx+1} / ${pairs.length}</span><button data-nav="${path}" data-d="1">›</button></div>`:""}</div>`;
}
function ancestorNode(p,level,max,path){
 const pairs=parentsByChild.get(p.uid)||[],idx=Math.min(treeSelections.get(path)||0,Math.max(0,pairs.length-1)),r=pairs[idx];
 if(level>=max||!r)return `<div class="tree-branch">${nodeCard(p,pairs,path)}</div>`;
 return `<div class="tree-branch">${nodeCard(p,pairs,path)}<div class="tree-edge"></div><div class="tree-children">${ancestorNode(r.first,level+1,max,path+"a")}${ancestorNode(r.second,level+1,max,path+"b")}</div></div>`;
}
function descendantNode(p,level,max,path){
 const pairs=offspringByParent.get(p.uid)||[],idx=Math.min(treeSelections.get(path)||0,Math.max(0,pairs.length-1)),r=pairs[idx];
 if(level>=max||!r)return `<div class="tree-branch">${nodeCard(p,pairs,path)}</div>`;
 return `<div class="tree-branch">${nodeCard(p,pairs,path)}<div class="tree-edge"></div><div class="tree-children"><div class="tree-branch">${nodeCard(r.partner,[],path+"p")}</div>${descendantNode(r.child,level+1,max,path+"c")}</div></div>`;
}
function applyTreeTransform(){$("#treeCanvas").style.transform=`translate(${panX}px,${panY}px) scale(${zoom})`}
function renderAll(){renderParents();renderTarget();renderOffspring();renderDex();renderTree()}
