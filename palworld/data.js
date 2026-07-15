"use strict";

const DATA_URLS={
 csv:"https://raw.githubusercontent.com/tylercamp/palcalc/8b7e2f779e47fddae16ddcb973e828ba20c02b80/PalCalc.GenDB/out-csv/pals.csv",
 jp:"https://raw.githubusercontent.com/zaigie/palworld-server-tool/51ee50087165a9ed4930a5d1a1ad4b7ca49f87a8/web/src/assets/pal.json",
 meta:"https://raw.githubusercontent.com/bowenchen-1/palworld-guide/a27953c1226cabafd732da547e0a5cb22f872d00/public/data/pals.json"
};

const OVERRIDES=[
["Relaxaurus","Sparkit","Relaxaurus Lux"],["Incineram","Maraith","Incineram Noct"],["Mau","Pengullet","Mau Cryst"],
["Vanwyrm","Foxcicle","Vanwyrm Cryst"],["Eikthyrdeer","Hangyu","Eikthyrdeer Terra"],["Elphidran","Surfent","Elphidran Aqua"],
["Pyrin","Katress","Pyrin Noct"],["Mammorest","Wumpo","Mammorest Cryst"],["Mossanda","Grizzbolt","Mossanda Lux"],
["Dinossom","Rayhound","Dinossom Lux"],["Jolthog","Pengullet","Jolthog Cryst"],["Frostallion","Helzephyr","Frostallion Noct"],
["Kingpaca","Reindrix","Kingpaca Cryst"],["Lyleen","Menasting","Lyleen Noct"],["Leezpunk","Flambelle","Leezpunk Ignis"],
["Blazehowl","Felbat","Blazehowl Noct"],["Robinquill","Fuddler","Robinquill Terra"],["Broncherry","Fuack","Broncherry Aqua"],
["Surfent","Dumud","Surfent Terra"],["Gobfin","Rooby","Gobfin Ignis"],["Suzaku","Jormuntide","Suzaku Aqua"],
["Reptyro","Foxcicle","Reptyro Cryst"],["Hangyu","Swee","Hangyu Cryst"],["Mossanda","Petallia","Lyleen"],
["Vanwyrm","Anubis","Faleris"],["Mossanda","Rayhound","Grizzbolt"],["Grizzbolt","Relaxaurus","Orserk"],
["Kitsun","Astegon","Shadowbeak"],
["Foxparks","Foxcicle","Foxparks Cryst"],["Fuack","Flambelle","Fuack Ignis"],["Pengullet","Sparkit","Pengullet Lux"],
["Penking","Rayhound","Penking Lux"],["Killamari","Ribbuny","Killamari Primo"],["Celaray","Univolt","Celaray Lux"],
["Caprity","Tarantriss","Caprity Noct"],["Ribbuny","Bristla","Ribbuny Botan"],["Dumud","Eikthyrdeer Terra","Dumud Gild"],
["Loupmoon","Sweepa","Loupmoon Cryst"],["Gorirat","Kikit","Gorirat Terra"],["Chillet","Arsox","Chillet Ignis"],
["Kitsun","Nyafia","Kitsun Noct"],["Dazzi","Omascul","Dazzi Noct"],["Bushi","Sootseer","Bushi Noct"],
["Katress","Wixen","Katress Ignis"],["Azurobe","Frostplume","Azurobe Cryst"],["Cryolinx","Dazemu","Cryolinx Terra"],
["Warsect","Digtoise","Warsect Terra"],["Fenglope","Azurmane","Fenglope Lux"],["Quivern","Lullu","Quivern Botan"],
["Helzephyr","Beakon","Helzephyr Lux"],["Menasting","Knocklem","Menasting Terra"],["Faleris","Jormuntide","Faleris Aqua"],
["Croajiro","Bushi Noct","Croajiro Noct"],["Turtacle","Digtoise","Turtacle Terra"],["Finsider","Gobfin Ignis","Finsider Ignis"],
["Ghangler","Sootseer","Ghangler Ignis"],["Whalaska","Chillet Ignis","Whalaska Ignis"],
["Tanzee","Flambelle","Tanzee Ignis"],["Woolipop","Kikit","Woolipop Terra"],["Gloopie","Valentail","Gloopie Primo"],
["Polapup","Surfent Terra","Polapup Terra"],["Elgrove","Pierdon Cryst","Elgrove Cryst"],["Petallia","Bushi","Petallia Ignis"],
["Beakon","Frostplume","Beakon Cryst"],["Rayhound","Foxcicle","Rayhound Cryst"],["Needoll","Prunelia","Needoll Noct"],
["Moldron","Reptyro Cryst","Moldron Cryst"],["Sibelyx","Lapure","Sibelyx Primo"],["Skutlass","Gobfin Ignis","Skutlass Ignis"],
["Starryon","Celesdir","Starryon Primo"],["Pierdon","Wumpo","Pierdon Cryst"],["Dualith","Sootseer","Dualith Noct"],
["Prixter","Helzephyr Lux","Prixter Lux"],["Tetroise","Celesdir","Tetroise Primo"],["Nitemary","Petallia","Nitemary Botan"],
["Smokie","Munchill","Smokie Cryst"],["Celesdir","Kitsun Noct","Celesdir Noct"],["Knocklem","Ragnahawk","Knocklem Ignis"],
["Snock","Turtacle Terra","Snock Lux"],["Solmora","Slowatt","Solmora Lux"],["Eidrolon","Suzaku","Eidrolon Ignis"],
["Univolt","Frostplume","Univolt Cryst"]
];

const ELEMENT_JP={Neutral:"無",Fire:"炎",Water:"水",Electric:"雷",Grass:"草",Dark:"闇",Dragon:"竜",Ground:"地",Ice:"氷"};
const WORK_JP={emitflame:"火おこし",watering:"水やり",seeding:"種まき",generateelectricity:"発電",handcraft:"手作業",collection:"採集",deforest:"伐採",mining:"採掘",productmedicine:"製薬",cool:"冷却",transport:"運搬",monsterfarm:"牧場"};

let pals=[],byName=new Map(),byId=new Map(),pairMap=new Map(),parentsByChild=new Map(),offspringByParent=new Map();
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
async function fetchText(url,timeout=9000){
 const ctrl=new AbortController();const t=setTimeout(()=>ctrl.abort(),timeout);
 try{const r=await fetch(url,{cache:"no-store",signal:ctrl.signal});if(!r.ok)throw Error(r.status);return await r.text()}finally{clearTimeout(t)}
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
function initialiseData(csv,jp,meta){
 pals=parseCSV(csv);byName.clear();byId.clear();pairMap.clear();parentsByChild.clear();offspringByParent.clear();
 mergeJP(jp);if(meta)mergeMeta(meta);
 pals.sort(palSort);pals.forEach((p,i)=>{p.uid=p.code+"#"+i;byId.set(p.uid,p);if(!byName.has(p.en))byName.set(p.en,p)});
 buildIndexes();fillFilterOptions();
 $("#dataStatus").textContent="データ読込完了";
 $("#dataStatus").className="badge ok";
 $("#palCount").textContent=pals.length+"体";
 $("#comboCount").textContent=pairMap.size.toLocaleString()+"組";
 renderAll();
}
async function load(){
 $("#dataStatus").textContent="データ読込中";
 $("#dataStatus").className="badge warn";
 try{
  const [ct,jt,mt]=await Promise.all([fetchText(DATA_URLS.csv,15000),fetchText(DATA_URLS.jp,15000),fetchText(DATA_URLS.meta,15000)]);
  initialiseData(ct,JSON.parse(jt).ja||{},JSON.parse(mt));
 }catch(e){
  console.error(e);
  $("#dataStatus").textContent="データ取得失敗・タップで再試行";
  $("#dataStatus").className="badge warn";
  $("#dataStatus").style.cursor="pointer";
  $("#dataStatus").onclick=()=>{ $("#dataStatus").onclick=null; load(); };
  toast("データ取得に失敗しました。通信状態を確認してください");
 }
}
function buildIndexes(){
 const overrides=new Map();
 OVERRIDES.forEach(([a,b,c])=>{if(byName.has(a)&&byName.has(b)&&byName.has(c))overrides.set(pairKey(a,b),byName.get(c))});
 function calculate(a,b){
  if(a.uid===b.uid)return [{first:a,second:b,child:a,note:"同種配合"}];
  const genderPair=(a.en==="Wixen"&&b.en==="Katress")||(a.en==="Katress"&&b.en==="Wixen");
  if(genderPair){
   return [
    {first:a,second:b,child:byName.get("Katress Ignis"),note:"親の性別で結果が変化"},
    {first:a,second:b,child:byName.get("Wixen Noct"),note:"親の性別で結果が変化"}
   ].filter(x=>x.child);
  }
  const ov=overrides.get(pairKey(a.en,b.en));
  if(ov)return [{first:a,second:b,child:ov,note:"固有配合"}];
  const target=Math.floor((a.power+b.power)/2);
  let best=null,dist=Infinity;
  for(const p of pals){
   const d=Math.abs(p.power-target);
   if(d<dist || (d===dist && (p.power<(best?.power??Infinity) || (p.power===best?.power&&p.index<best.index)))){
    best=p;dist=d;
   }
  }
  return best?[{first:a,second:b,child:best,note:"通常配合"}]:[];
 }
 for(let i=0;i<pals.length;i++){
  for(let j=i;j<pals.length;j++){
   const a=pals[i],b=pals[j],res=calculate(a,b);
   pairMap.set(pairKey(a.uid,b.uid),res);
   for(const r of res){
    if(!parentsByChild.has(r.child.uid))parentsByChild.set(r.child.uid,[]);
    parentsByChild.get(r.child.uid).push(r);
    for(const p of [a,b]){
     if(!offspringByParent.has(p.uid))offspringByParent.set(p.uid,[]);
     offspringByParent.get(p.uid).push({...r,partner:p.uid===a.uid?b:a});
    }
   }
  }
 }
}
