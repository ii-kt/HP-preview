"use strict";

const DATA_URLS={
 csv:"https://raw.githubusercontent.com/tylercamp/palcalc/8b7e2f779e47fddae16ddcb973e828ba20c02b80/PalCalc.GenDB/out-csv/pals.csv",
 breeding:"https://raw.githubusercontent.com/tylercamp/palcalc/8b7e2f779e47fddae16ddcb973e828ba20c02b80/PalCalc.Model/breeding.json",
 jp:"https://raw.githubusercontent.com/zaigie/palworld-server-tool/51ee50087165a9ed4930a5d1a1ad4b7ca49f87a8/web/src/assets/pal.json",
 meta:"https://raw.githubusercontent.com/bowenchen-1/palworld-guide/a27953c1226cabafd732da547e0a5cb22f872d00/public/data/pals.json"
};

const ELEMENT_JP={Neutral:"無",Fire:"炎",Water:"水",Electric:"雷",Grass:"草",Dark:"闇",Dragon:"竜",Ground:"地",Ice:"氷"};
const WORK_JP={emitflame:"火おこし",watering:"水やり",seeding:"種まき",generateelectricity:"発電",handcraft:"手作業",collection:"採集",deforest:"伐採",mining:"採掘",productmedicine:"製薬",cool:"冷却",transport:"運搬",monsterfarm:"牧場"};

let pals=[],byName=new Map(),byCode=new Map(),byId=new Map(),pairMap=new Map(),parentsByChild=new Map(),offspringByParent=new Map();
let selected={a:null,b:null,target:null,parent:null,tree:null};
let pickerCallback=null, treeOrientation="result", treeSelections=new Map();
let zoom=1,panX=0,panY=0;

const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pairKey=(a,b)=>[a,b].sort().join("|");
const palSort=(a,b)=>a.no-b.no || Number(a.variant)-Number(b.variant) || a.index-b.index;
function parseCSV(text){
 const lines=text.replace(/^\uFEFF/,"").trim().split(/\r?\n/); lines.shift();
 return lines.map((line,i)=>{
  const c=line.split(",");
  return {id:c[1],en:c[0],code:c[1],no:+c[2],variant:c[3]==="True",power:+c[4],male:+c[5]||50,price:+c[6]||0,index:+c[7]||i,min:+c[8]||null,max:+c[9]||null,elements:[],work:{}};
 }).filter(p=>p.no<10000);
}
async function fetchText(url,timeout=30000){
 const ctrl=new AbortController();const t=setTimeout(()=>ctrl.abort(),timeout);
 try{const r=await fetch(url,{cache:"no-store",signal:ctrl.signal});if(!r.ok)throw Error(`${r.status} ${url}`);return await r.text()}finally{clearTimeout(t)}
}
function mergeJP(jp){
 pals.forEach(p=>{
  let n=jp?.[p.code]||p.en;
  if(!n||n==="-"||/^[A-Za-z_]+$/.test(n))n=p.en;
  p.jp=n;
  if(p.code==="PlantSlime_Flower")p.jp="ナエモチ（花付き）";
 });
}
function mergeMeta(meta){
 const aliases={"Kingpaca Cryst":"Ice Kingpaca","Reptyro Cryst":"Ice Reptyro"};
 const byMeta=new Map(meta.map(x=>[x.name,x]));
 pals.forEach(p=>{
  const m=byMeta.get(p.en)||byMeta.get(aliases[p.en]);
  if(m){p.elements=m.elements||[];p.work=m.work||{};p.slug=m.slug||""}
 });
}
function genderMark(g){return g==="MALE"?"♂":g==="FEMALE"?"♀":""}
function normalizedResultSignature(first,second,child,gender1,gender2){
 const a={uid:first.uid,gender:gender1},b={uid:second.uid,gender:gender2};
 const [left,right]=a.uid<=b.uid?[a,b]:[b,a];
 return [left.uid,left.gender,right.uid,right.gender,child.uid].join("|");
}
function initialiseData(csv,jp,meta,breedingData){
 pals=parseCSV(csv);
 byName.clear();byCode.clear();byId.clear();pairMap.clear();parentsByChild.clear();offspringByParent.clear();
 mergeJP(jp);if(meta)mergeMeta(meta);
 pals.sort(palSort);
 pals.forEach((p,i)=>{
  p.uid=p.code+"#"+i;
  byId.set(p.uid,p);
  byCode.set(p.code,p);
  if(!byName.has(p.en))byName.set(p.en,p);
 });
 buildIndexes(breedingData?.Breeding||[]);
 validateIndexes();
 fillFilterOptions();
 $("#dataStatus").textContent="ゲームデータ配合表 読込完了";
 $("#dataStatus").className="badge ok";
 $("#dataStatus").style.cursor="default";
 $("#dataStatus").onclick=null;
 $("#palCount").textContent=pals.length+"形態";
 $("#comboCount").textContent=pairMap.size.toLocaleString()+"組";
 renderAll();
}
async function load(){
 $("#dataStatus").textContent="確定配合表を読込中";
 $("#dataStatus").className="badge warn";
 pairMap.clear();parentsByChild.clear();offspringByParent.clear();
 try{
  const [ct,bt,jt,mt]=await Promise.all([
   fetchText(DATA_URLS.csv),fetchText(DATA_URLS.breeding),fetchText(DATA_URLS.jp),fetchText(DATA_URLS.meta)
  ]);
  initialiseData(ct,JSON.parse(jt).ja||{},JSON.parse(mt),JSON.parse(bt));
 }catch(e){
  console.error(e);
  pals=[];byName.clear();byCode.clear();byId.clear();pairMap.clear();parentsByChild.clear();offspringByParent.clear();
  $("#palCount").textContent="0形態";$("#comboCount").textContent="0組";
  $("#dataStatus").textContent="確定配合表の取得・検証失敗　タップで再試行";
  $("#dataStatus").className="badge warn";
  $("#dataStatus").style.cursor="pointer";
  $("#dataStatus").onclick=()=>{$("#dataStatus").onclick=null;load()};
  renderAll();
  toast("確定配合表を検証できないため、配合結果は表示しません");
 }
}
function buildIndexes(rows){
 const seenByPair=new Map();
 for(const row of rows){
  const first=byCode.get(row.Parent1InternalName);
  const second=byCode.get(row.Parent2InternalName);
  const child=byCode.get(row.ChildInternalName);
  if(!first||!second||!child)continue;
  const key=pairKey(first.uid,second.uid);
  if(!pairMap.has(key))pairMap.set(key,[]);
  if(!seenByPair.has(key))seenByPair.set(key,new Set());
  const sig=normalizedResultSignature(first,second,child,row.Parent1Gender,row.Parent2Gender);
  if(seenByPair.get(key).has(sig))continue;
  seenByPair.get(key).add(sig);
  const genderSpecific=row.Parent1Gender!=="WILDCARD"||row.Parent2Gender!=="WILDCARD";
  const note=genderSpecific
   ?`${first.jp}${genderMark(row.Parent1Gender)} × ${second.jp}${genderMark(row.Parent2Gender)} の場合`
   :"ゲームデータ確定配合";
  pairMap.get(key).push({
   first,second,child,note,
   parent1Gender:row.Parent1Gender,parent2Gender:row.Parent2Gender
  });
 }
 for(const results of pairMap.values()){
  results.sort((a,b)=>palSort(a.child,b.child)||a.note.localeCompare(b.note,"ja"));
  for(const r of results){
   if(!parentsByChild.has(r.child.uid))parentsByChild.set(r.child.uid,[]);
   parentsByChild.get(r.child.uid).push(r);
   const uniqueParents=r.first.uid===r.second.uid?[r.first]:[r.first,r.second];
   for(const p of uniqueParents){
    if(!offspringByParent.has(p.uid))offspringByParent.set(p.uid,[]);
    offspringByParent.get(p.uid).push({...r,partner:p.uid===r.first.uid?r.second:r.first});
   }
  }
 }
}
function validateIndexes(){
 const expectedPairs=pals.length*(pals.length+1)/2;
 if(pairMap.size!==expectedPairs)throw new Error(`配合表が不完全です: ${pairMap.size}/${expectedPairs}組`);
 if(parentsByChild.size!==pals.length)throw new Error(`逆引き表が不完全です: ${parentsByChild.size}/${pals.length}形態`);
 for(const [key,results] of pairMap){
  if(!results.length)throw new Error(`結果が空の配合ペアです: ${key}`);
  const seen=new Set();
  for(const r of results){
   const sig=normalizedResultSignature(r.first,r.second,r.child,r.parent1Gender,r.parent2Gender);
   if(seen.has(sig))throw new Error(`配合結果が重複しています: ${key}`);
   seen.add(sig);
  }
 }
 for(const parent of pals){
  let expected=0;
  for(const partner of pals)expected+=(pairMap.get(pairKey(parent.uid,partner.uid))||[]).length;
  const actual=(offspringByParent.get(parent.uid)||[]).length;
  if(actual!==expected)throw new Error(`全子一覧の件数が不正です: ${parent.code} ${actual}/${expected}`);
 }
}
