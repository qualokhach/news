(async()=>{
const labels={world:"THẾ GIỚI",vietnam:"VIỆT NAM",sports:"THỂ THAO",technology:"CÔNG NGHỆ"};
const categoryTitles={world:"Tin thế giới",vietnam:"Tin Việt Nam",sports:"Tin thể thao",technology:"Tin công nghệ"};
const dateFmt=v=>{if(!v)return "";const d=new Date(v);return isNaN(d)?"":d.toLocaleDateString("vi-VN",{day:"numeric",month:"short",year:"numeric",timeZone:"Asia/Ho_Chi_Minh"})};
const esc=s=>String(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const thumb={world:"https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_the_gioi.png",vietnam:"https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_Viet_Nam.png",sports:"https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_the_thao.png",technology:"https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_Cong_Nghe.png"};
const sorted=(a,b)=>new Date(b.published_at||b.fetched_at||0)-new Date(a.published_at||a.fetched_at||0);
const href=a=>`article.html?id=${encodeURIComponent(a.id)}`;
const card=a=>`<article class="news-card"><a class="card-image-link" href="${href(a)}"><img class="card-image" src="${esc(thumb[a.category]||a.image_thumbnail||"")}" alt="${esc(labels[a.category]||"AppNho News")}" loading="lazy"><span class="card-image-label">${esc(labels[a.category]||"BẢN TIN")}</span></a><div class="card-body"><div class="card-meta"><span class="tag">${esc(labels[a.category]||"TIN TỨC")}${a.collection==="archive"?" · NHÌN LẠI":""}</span><time>${esc(dateFmt(a.published_at))}</time></div><h3><a href="${href(a)}">${esc(a.title)}</a></h3><p>${esc(a.summary||"Cùng AppNho tìm hiểu diễn biến đáng chú ý này.")}</p><a class="read-more" href="${href(a)}">Đọc bản tin ↗</a></div></article>`;
const row=a=>`<article class="category-row"><a class="row-thumb" href="${href(a)}"><img src="${esc(thumb[a.category]||a.image_thumbnail||"")}" alt="" loading="lazy"></a><div class="row-copy"><h3><a href="${href(a)}">${esc(a.title)}</a></h3><time>${esc(dateFmt(a.published_at))}${a.collection==="archive"?" · Nhìn lại":""}</time><a class="read-more" href="${href(a)}">Đọc tiếp ↗</a></div></article>`;
const mini=a=>`<a class="side-item" href="${href(a)}"><img src="${esc(thumb[a.category]||a.image_thumbnail||"")}" alt="" loading="lazy"><span><strong>${esc(a.title)}</strong><time>${esc(dateFmt(a.published_at))}</time></span></a>`;
let current=[],archive=[],all=[];
async function fetchJson(path){const r=await fetch(path,{cache:"no-store"});if(!r.ok)throw new Error(`${path}: HTTP ${r.status}`);return r.json()}
async function loadAllArticles(){
  const [currentData,baseArchive,manifestData,catalogData]=await Promise.all([
    fetchJson("data/articles.json"),
    fetchJson("data/archive_articles.json").catch(e=>{console.warn("Base archive unavailable",e);return []}),
    fetchJson("data/archive_manifest.json").catch(e=>{console.warn("Archive manifest unavailable",e);return ["data/archive_articles.json"]}),
    fetchJson("data/archive_catalog.json").catch(e=>{console.warn("Archive catalog unavailable",e);return []})
  ]);
  current=(Array.isArray(currentData)?currentData:[]).filter(a=>a&&a.id).map(a=>({...a,collection:a.collection||"current"}));
  const paths=new Set(["data/archive_articles.json"]);
  if(Array.isArray(manifestData))manifestData.forEach(p=>{if(typeof p==="string"&&/^data\/archive(?:_articles|_batches)\/[^\s]+\.json$/.test(p))paths.add(p)});
  if(Array.isArray(catalogData))catalogData.forEach(x=>{if(x&&typeof x.file==="string"&&/^data\/archive(?:_articles|_batches)\/[^\s]+\.json$/.test(x.file))paths.add(x.file)});
  const batches=await Promise.all([...paths].map(async path=>{
    if(path==="data/archive_articles.json")return Array.isArray(baseArchive)?baseArchive:[];
    try{const d=await fetchJson(path);if(!Array.isArray(d))throw new Error("Archive batch is not an array");return d}
    catch(e){console.warn("Archive batch skipped:",path,e);return []}
  }));
  const byId=new Map();
  current.forEach(a=>{if(!byId.has(String(a.id)))byId.set(String(a.id),a)});
  batches.flat().filter(a=>a&&a.id).forEach(a=>{const item={...a,collection:"archive"};if(!byId.has(String(item.id)))byId.set(String(item.id),item)});
  // Catalog entries are metadata, not a second copy of article content.
  archive=[...byId.values()].filter(a=>a.collection==="archive");
  all=[...byId.values()].sort(sorted);
  if(!all.length)throw new Error("Không có bản tin hợp lệ");
}
try{await loadAllArticles()}catch(e){console.error("AppNho News data error:",e);current=[];archive=[];all=[]}
const active=all.filter(a=>a.collection!=="archive").sort(sorted),archived=all.filter(a=>a.collection==="archive").sort(sorted);
const q=new URLSearchParams(location.search),category=q.get("category"),grid=document.getElementById("newsGrid"),empty=document.getElementById("emptyState"),input=document.getElementById("searchInput");
const validCategory=Object.prototype.hasOwnProperty.call(categoryTitles,category)?category:null;
const homePage=document.body.classList.contains("home-page");
if(homePage&&validCategory){document.title=`${categoryTitles[validCategory]} | AppNho News`;const desc=document.querySelector('meta[name="description"]');if(desc)desc.content=`Tin tức ${categoryTitles[validCategory].toLocaleLowerCase("vi")} mới nhất và bài viết lưu trữ tại AppNho News.`;document.querySelectorAll(".hero,.category-tiles,.category-section").forEach(el=>el.classList.add("hidden"));const h=document.getElementById("latestHeading");if(h)h.textContent=categoryTitles[validCategory];const intro=document.querySelector(".section-intro");if(intro)intro.textContent="Tin đang hoạt động và bài nhìn lại trong chuyên mục, sắp xếp theo ngày công bố.";const sectionHeading=document.querySelector(".latest-block .section-heading > div");if(sectionHeading&&!document.getElementById("backToHome")){const back=document.createElement("a");back.id="backToHome";back.className="section-link";back.href="./";back.textContent="← Về trang chủ";sectionHeading.appendChild(back)}if(grid)grid.classList.add("category-page-grid");}
function renderRecent(){let ids=[];try{ids=JSON.parse(localStorage.getItem("appnhoNewsRead")||"[]")}catch(e){}const items=ids.map(id=>all.find(a=>a.id===id)).filter(Boolean).slice(0,5);const el=document.getElementById("recentList");if(el)el.innerHTML=items.map(mini).join("")||`<p class="side-empty">Các bài bạn đã xem sẽ xuất hiện tại đây.</p>`}
let categoryPageItems=[];let shownCount=12;
function render(query=""){if(!grid||!empty)return;const term=query.trim().toLocaleLowerCase("vi");let matches;if(validCategory){matches=all.filter(a=>a.category===validCategory);if(term)matches=matches.filter(a=>(a.title+" "+(a.summary||"")+" "+(a.keywords||[]).join(" ")).toLocaleLowerCase("vi").includes(term));categoryPageItems=matches.sort(sorted);grid.innerHTML=categoryPageItems.slice(0,shownCount).map(card).join("");let more=document.getElementById("loadMoreNews");if(more)more.remove();if(categoryPageItems.length>shownCount){more=document.createElement("button");more.id="loadMoreNews";more.className="load-more";more.type="button";more.textContent="Xem thêm bản tin";more.addEventListener("click",()=>{shownCount+=12;render(input?input.value:"")});grid.after(more)}}else{matches=term?all.filter(a=>(a.title+" "+(a.summary||"")+" "+(a.keywords||[]).join(" ")).toLocaleLowerCase("vi").includes(term)):active;grid.innerHTML=matches.slice(0,6).map(card).join("")}
empty.classList.toggle("hidden",matches.length>0);empty.textContent=term?"Chưa có bài phù hợp với từ khóa này.":"Chưa có bản tin trong chuyên mục này.";const heading=document.getElementById("latestHeading");if(heading&&!validCategory)heading.textContent=term?`Kết quả tìm kiếm (${matches.length})`:"Tin mới";
if(!validCategory){document.querySelectorAll("[data-category]").forEach(el=>{const cat=el.dataset.category;const items=all.filter(a=>a.category===cat).sort((a,b)=>{const aa=a.collection==="archive"?1:0,bb=b.collection==="archive"?1:0;return aa-bb||sorted(a,b)}).slice(0,4);el.innerHTML=items.map(row).join("")||`<p class="loading">Chưa có bản tin trong chuyên mục này.</p>`});const archiveEl=document.getElementById("archiveList");if(archiveEl){const grouped={};archived.forEach(a=>{const d=new Date(a.published_at||a.fetched_at);const key=isNaN(d)?"Chưa rõ thời gian":d.toLocaleDateString("vi-VN",{month:"long",year:"numeric",timeZone:"Asia/Ho_Chi_Minh"});(grouped[key]||(grouped[key]=[])).push(a)});archiveEl.innerHTML=Object.entries(grouped).map(([month,items])=>`<section class="archive-month"><h3>${esc(month)}</h3>${items.slice(0,5).map(row).join("")}</section>`).join("")||`<p class="loading">Chưa có bài nhìn lại.</p>`}const featured=document.getElementById("featuredList");if(featured)featured.innerHTML=active.slice(0,5).map(mini).join("")||`<p class="side-empty">Chưa có tin nổi bật.</p>`}}
if(input){input.value=q.get("q")||"";render(input.value);input.addEventListener("input",e=>{shownCount=12;render(e.target.value)})}else render(q.get("q")||"");renderRecent();const year=document.getElementById("year");if(year)year.textContent=new Date().getFullYear();
})();
