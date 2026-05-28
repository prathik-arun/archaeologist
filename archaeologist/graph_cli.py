#!/usr/bin/env python3
"""archaeologist-graph — interactive call graph visualizer."""
import os
import sys
import json
import webbrowser
import tempfile
from pathlib import Path

import click
from rich.console import Console

from archaeologist.scanner import scan_directory
from archaeologist.git_analyzer import analyze_git_history
from archaeologist.scorer import analyze

console = Console()

def build_html(project_name, raw_data_json):
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>archaeologist-graph — __PROJECT_NAME__</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 100%; height: 100%; overflow: hidden; background: #0a0a08; color: #e8e4dc; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }

.topbar { height: 52px; background: #111110; border-bottom: 1px solid #2a2a24; display: flex; align-items: center; gap: 12px; padding: 0 20px; flex-shrink: 0; }
.logo { font-size: 15px; color: #c9a84c; font-style: italic; font-family: Georgia, serif; }
.stat { font-size: 12px; color: #6b6b5f; }
.stat b { color: #e8e4dc; }
.sep { color: #2a2a24; }
.controls { margin-left: auto; display: flex; gap: 6px; align-items: center; }
.search-box { font-size: 12px; padding: 5px 12px; border-radius: 20px; border: 1px solid #2a2a24; background: #1a1a17; color: #e8e4dc; outline: none; width: 180px; }
.search-box:focus { border-color: #c9a84c; }
.search-box::placeholder { color: #4a4a40; }
.btn { font-size: 12px; padding: 5px 14px; border-radius: 20px; border: 1px solid #2a2a24; background: transparent; color: #6b6b5f; cursor: pointer; white-space: nowrap; }
.btn:hover, .btn.on { background: #c9a84c; color: #0a0a08; border-color: #c9a84c; font-weight: 600; }

.layout { display: flex; height: calc(100vh - 52px); }

/* SIDEBAR */
.sidebar { width: 220px; flex-shrink: 0; background: #111110; border-right: 1px solid #2a2a24; display: flex; flex-direction: column; overflow: hidden; }
.sb-head { padding: 10px 14px; border-bottom: 1px solid #2a2a24; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: #6b6b5f; font-weight: 600; }
.sb-list { overflow-y: auto; flex: 1; }
.sb-item { padding: 8px 14px; border-bottom: 1px solid #1a1a17; cursor: pointer; }
.sb-item:hover, .sb-item.sel { background: #1a1a17; }
.sb-item.sel { border-left: 3px solid #c9a84c; padding-left: 11px; }
.sb-name { font-size: 12px; color: #e8e4dc; font-family: monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sb-meta { font-size: 11px; color: #6b6b5f; margin-top: 2px; }
.dead-tag { display: inline-block; font-size: 9px; padding: 1px 5px; border-radius: 99px; background: #2a0808; color: #e05a3a; border: 1px solid #3a1010; margin-left: 4px; vertical-align: middle; }

/* CANVAS AREA */
.canvas-wrap { flex: 1; position: relative; overflow: hidden; background: #0d0d0b; }
canvas { position: absolute; top: 0; left: 0; cursor: grab; }
canvas.dragging { cursor: grabbing; }

/* ZOOM CONTROLS */
.zoom-controls { position: absolute; bottom: 20px; right: 20px; display: flex; flex-direction: column; gap: 4px; z-index: 10; }
.zoom-btn { width: 36px; height: 36px; border-radius: 8px; background: #1a1a17; border: 1px solid #2a2a24; color: #e8e4dc; font-size: 18px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s; }
.zoom-btn:hover { background: #c9a84c; color: #0a0a08; border-color: #c9a84c; }
.zoom-label { font-family: monospace; font-size: 11px; color: #6b6b5f; text-align: center; margin-top: 2px; }

/* TOOLTIP */
.tip { position: absolute; background: #1a1a17; border: 1px solid #2a2a24; border-radius: 8px; padding: 10px 14px; font-size: 12px; color: #b0aa9a; pointer-events: none; max-width: 220px; line-height: 1.6; display: none; z-index: 20; box-shadow: 0 4px 20px rgba(0,0,0,.6); }
.tip b { color: #e8e4dc; display: block; margin-bottom: 3px; font-size: 13px; }

/* DETAIL PANEL */
.detail { width: 240px; flex-shrink: 0; background: #111110; border-left: 1px solid #2a2a24; padding: 16px; overflow-y: auto; }
.d-empty { font-size: 13px; color: #4a4a40; font-style: italic; text-align: center; margin-top: 3rem; line-height: 1.8; }
.d-name { font-size: 14px; font-weight: 600; color: #e8e4dc; font-family: monospace; word-break: break-all; margin-bottom: 4px; }
.d-file { font-size: 11px; color: #6b6b5f; margin-bottom: 14px; }
.d-tag { display: inline-block; font-size: 11px; padding: 3px 10px; border-radius: 99px; margin-bottom: 12px; }
.d-sec { font-size: 10px; letter-spacing: .1em; text-transform: uppercase; color: #4a4a40; font-weight: 600; margin: 12px 0 6px; }
.d-stat { font-size: 13px; color: #b0aa9a; margin-bottom: 4px; }
.d-fn { font-size: 12px; color: #74b9ff; font-family: monospace; cursor: pointer; padding: 3px 0; display: block; }
.d-fn:hover { color: #c9a84c; }

/* LEGEND */
.legend { position: absolute; bottom: 20px; left: 20px; background: rgba(17,17,16,.92); border: 1px solid #2a2a24; border-radius: 8px; padding: 10px 14px; font-size: 11px; color: #6b6b5f; z-index: 10; backdrop-filter: blur(4px); }
.leg-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.leg-row:last-child { margin-bottom: 0; }
.leg-dot { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }

::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-track { background: #111110; } ::-webkit-scrollbar-thumb { background: #2a2a24; }
</style>
</head>
<body>

<div class="topbar">
  <span class="logo">☠ archaeologist-graph</span>
  <span class="sep">|</span>
  <span class="stat"><b id="s-fns">0</b> functions</span>
  <span class="sep">·</span>
  <span class="stat"><b id="s-dead" style="color:#e05a3a">0</b> dead</span>
  <span class="sep">·</span>
  <span class="stat"><b id="s-files">0</b> files</span>
  <div class="controls">
    <input class="search-box" type="text" placeholder="Search files or folders…" oninput="doSearch(this.value)" id="searchBox">
    <button class="btn on" onclick="setView('file',this)">Files</button>
    <button class="btn" onclick="setView('fn',this)">Functions</button>
    <button class="btn" onclick="showDead(this)">Dead only</button>
    <button class="btn" onclick="resetView()">Reset view</button>
  </div>
</div>

<div class="layout">
  <div class="sidebar">
    <div class="sb-head" id="sb-head">Files</div>
    <div class="sb-list" id="sb-list"></div>
  </div>

  <div class="canvas-wrap" id="wrap">
    <canvas id="cv"></canvas>
    <div class="tip" id="tip"></div>
    <div class="legend">
      <div class="leg-row"><div class="leg-dot" style="background:#3C3489"></div>Entry point</div>
      <div class="leg-row"><div class="leg-dot" style="background:#085041"></div>Clean file</div>
      <div class="leg-row"><div class="leg-dot" style="background:#5C4A00"></div>Has dead code</div>
      <div class="leg-row"><div class="leg-dot" style="background:#791F1F"></div>All dead</div>
    </div>
    <div class="zoom-controls">
      <button class="zoom-btn" onclick="adjustZoom(1.25)" title="Zoom in">+</button>
      <button class="zoom-btn" onclick="adjustZoom(0.8)" title="Zoom out">−</button>
      <button class="zoom-btn" onclick="resetView()" title="Reset" style="font-size:14px">⌖</button>
      <div class="zoom-label" id="zlbl">100%</div>
    </div>
  </div>

  <div class="detail" id="detail">
    <div class="d-empty">Click any node<br>to see details</div>
  </div>
</div>

<script>
const DATA = __RAW_DATA__;
const wrap = document.getElementById('wrap');
const cv = document.getElementById('cv');
const ctx = cv.getContext('2d');
const tip = document.getElementById('tip');

const COL = {
  entry:  {fill:'#3C3489', stroke:'#534AB7', text:'#EEEDFE'},
  active: {fill:'#085041', stroke:'#0F6E56', text:'#E1F5EE'},
  dead:   {fill:'#791F1F', stroke:'#E24B4A', text:'#FCEBEB'},
  mixed:  {fill:'#5C4A00', stroke:'#c9a84c', text:'#FFF3CC'},
};

let nodes=[], edges=[], view='file';
let zoom=1, panX=30, panY=30;
let dragging=false, didDrag=false, lx=0, ly=0;
let selId=null, hovId=null, deadOnly=false, searchQ='';
let folderPositions={};

// Node constants — big and readable
const NW=160, NH=38, FONT=13;

function init() {
  document.getElementById('s-fns').textContent = DATA.functions.length;
  document.getElementById('s-dead').textContent = DATA.dead.length;
  document.getElementById('s-files').textContent = new Set(DATA.functions.map(f=>f.file)).size;
  resize();
  buildFileGraph();
}

function resize() {
  cv.width = wrap.clientWidth;
  cv.height = wrap.clientHeight;
}

/* ── FILE GRAPH ─────────────────────────────────────────────── */
function buildFileGraph() {
  const SKIP = ['macos/','ios/','android/','windows/','linux/','ephemeral','.g.dart','GeneratedPlugin','Runner/','scripts/'];

  const fileMap = {};
  DATA.functions.forEach(f => {
    if (SKIP.some(s=>f.file.includes(s))) return;
    if (!fileMap[f.file]) fileMap[f.file] = {funcs:[],dead:0};
    fileMap[f.file].funcs.push(f.name);
  });
  DATA.dead.forEach(d => {
    if (!fileMap[d.file]) fileMap[d.file] = {funcs:[],dead:0};
    fileMap[d.file].dead++;
  });

  // 2-level folder grouping
  const folderMap = {};
  Object.keys(fileMap).forEach(f => {
    const parts = f.replace(/^lib\//, '').split('/');
    const folder = parts.length >= 3 ? parts[0]+'/'+parts[1] : parts.length===2 ? parts[0] : '_root';
    if (!folderMap[folder]) folderMap[folder]=[];
    folderMap[folder].push(f);
  });

  const MAX_PER = 12;
  const nm = {};
  nodes = [];
  folderPositions = {};

  // Sort folders biggest first
  const folders = Object.keys(folderMap).sort((a,b)=>folderMap[b].length-folderMap[a].length);

  // Pick top files per folder (dead first)
  folders.forEach(folder => {
    const files = folderMap[folder].sort((a,b) => {
      return (fileMap[b].dead>0?1:0) - (fileMap[a].dead>0?1:0) || fileMap[b].funcs.length - fileMap[a].funcs.length;
    }).slice(0, MAX_PER);

    files.forEach(f => {
      const dc = fileMap[f].dead, total = fileMap[f].funcs.length;
      const name = f.split('/').pop().replace(/\.[^.]+$/,'');
      const isEntry = name==='main' || f==='lib/main.dart';
      const type = isEntry?'entry': dc===total&&dc>0?'dead': dc>0?'mixed':'active';
      const node = {
        id:f, name: name.length>16?name.slice(0,14)+'…':name, fullName:name,
        file:f, folder, type, isDead:dc>0,
        deadCount:dc, totalCount:total,
        callers:[], callees:[],
        x:0, y:0, r:0
      };
      nm[f]=node; nodes.push(node);
    });
  });

  // Cross-folder edges only
  edges=[];
  const fnToFile={};
  DATA.functions.forEach(f=>{ fnToFile[f.name]=f.file; });
  DATA.calls.forEach(c=>{
    if (!nm[c.file]) return;
    c.called.forEach(cal=>{
      const tf=fnToFile[cal];
      if (!tf||tf===c.file||!nm[tf]) return;
      if (nm[c.file].folder===nm[tf].folder) return;
      if (!edges.find(e=>e.from===c.file&&e.to===tf)) {
        edges.push({from:c.file, to:tf, dead:nm[c.file].isDead&&nm[tf].isDead});
        nm[c.file].callees.push(tf);
        nm[tf].callers.push(c.file);
      }
    });
  });

  // Layout — 3 folder columns, generous spacing
  const COLS=3, HGAP=16, VGAP=16, PAD=20, LHGT=32, FGAPX=50, FGAPY=50;
  const folderSizes={};
  folders.forEach(folder=>{
    const files=(folderMap[folder]||[]).filter(f=>nm[f]);
    if (!files.length){folderSizes[folder]={w:0,h:0,files:[],nc:0};return;}
    const nc=Math.min(3,files.length), nr=Math.ceil(files.length/nc);
    folderSizes[folder]={
      w: nc*(NW+HGAP)-HGAP+PAD*2,
      h: LHGT+PAD+nr*(NH+VGAP)-VGAP+PAD,
      files, nc, nr
    };
  });

  // Compute col widths
  const colW=[0,0,0];
  folders.forEach((f,i)=>{ const c=i%COLS; colW[c]=Math.max(colW[c],(folderSizes[f]||{w:0}).w); });

  // Place folders
  let col=0, curY=FGAPY;
  let rowH=0;
  const folderXs=[FGAPX, FGAPX+colW[0]+FGAPX, FGAPX+colW[0]+FGAPX+colW[1]+FGAPX];

  folders.forEach((folder,fi)=>{
    const sz=folderSizes[folder];
    if (!sz||!sz.w) return;
    col=fi%COLS;
    if (fi>0&&col===0) { curY+=rowH+FGAPY; rowH=0; }
    rowH=Math.max(rowH,sz.h);
    const bx=folderXs[col], by=curY;
    folderPositions[folder]={bx,by,w:sz.w,h:sz.h,label:folder.split('/').pop()+'/'};
    sz.files.filter(f=>nm[f]).forEach((f,i)=>{
      const nc2=i%sz.nc, nr2=Math.floor(i/sz.nc);
      nm[f].x=bx+PAD+nc2*(NW+HGAP)+NW/2;
      nm[f].y=by+LHGT+PAD+nr2*(NH+VGAP)+NH/2;
    });
  });

  // Start zoomed in — show top portion clearly
  panX=30; panY=30; zoom=1.0;
  updateZoomLabel();
  renderSidebar();
  draw();
}

/* ── FUNCTION GRAPH ─────────────────────────────────────────── */
function buildFnGraph() {
  const NOISE=new Set(['toJson','fromJson','toMap','fromMap','copyWith','toString','hashCode',
    'build','createState','initState','dispose','setState','equals','compareTo']);
  const SKIP=['macos/','ios/','android/','windows/','scripts/'];
  const deadSet=new Set(DATA.dead.map(d=>d.name+'|'+d.file));
  const calledNames=new Set();
  DATA.calls.forEach(c=>c.called.forEach(n=>calledNames.add(n)));

  nodes=DATA.functions.filter(f=>
    !NOISE.has(f.name) && !SKIP.some(s=>f.file.includes(s))
  ).slice(0,150).map(f=>{
    const id=f.name+'|'+f.file;
    const isDead=deadSet.has(id)||DATA.dead.some(d=>d.name===f.name);
    const isEntry=['main','app','runApp'].includes(f.name);
    const type=isDead?'dead':isEntry?'entry':calledNames.has(f.name)?'active':'mixed';
    return {id,name:f.name.length>16?f.name.slice(0,14)+'…':f.name,fullName:f.name,
      file:f.file,folder:'',type,isDead,deadCount:0,totalCount:0,
      callers:[],callees:[],x:0,y:0,r:NW/2};
  });

  const nm={};
  nodes.forEach(n=>nm[n.id]=n);
  edges=[];

  // Force layout
  const W=cv.width*2,H=cv.height*2;
  nodes.forEach((n,i)=>{
    n.x=W/2+Math.cos(i/nodes.length*Math.PI*2)*W*0.3;
    n.y=H/2+Math.sin(i/nodes.length*Math.PI*2)*H*0.3;
  });
  for(let it=0;it<60;it++){
    nodes.forEach(n=>{n.vx=0;n.vy=0;});
    for(let i=0;i<nodes.length;i++) for(let j=i+1;j<nodes.length;j++){
      const a=nodes[i],b=nodes[j],dx=a.x-b.x,dy=a.y-b.y,d=Math.sqrt(dx*dx+dy*dy)||1,f=5000/(d*d);
      a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f;
    }
    nodes.forEach(n=>{n.x=Math.max(80,Math.min(W-80,n.x+n.vx*0.4));n.y=Math.max(40,Math.min(H-40,n.y+n.vy*0.4));});
  }
  panX=30;panY=30;zoom=Math.min(cv.width/(cv.width*2),cv.height/(cv.height*2))*0.8;
  updateZoomLabel();
  renderSidebar();
  draw();
}

/* ── DRAW ─────────────────────────────────────────────────────── */
function draw() {
  ctx.clearRect(0,0,cv.width,cv.height);
  ctx.save();
  ctx.translate(panX,panY);
  ctx.scale(zoom,zoom);

  const vis=new Set(visible().map(n=>n.id));
  const nm={};
  nodes.forEach(n=>nm[n.id]=n);

  // Folder backgrounds
  if (view==='file') {
    Object.entries(folderPositions).forEach(([f,p])=>{
      ctx.globalAlpha=0.07;
      ctx.fillStyle='#c9a84c';
      ctx.strokeStyle='#c9a84c55';
      ctx.lineWidth=1;
      ctx.beginPath();
      ctx.roundRect(p.bx,p.by,p.w,p.h,10);
      ctx.fill(); ctx.stroke();
      ctx.globalAlpha=1;
      ctx.font='bold 13px -apple-system,sans-serif';
      ctx.textAlign='left'; ctx.textBaseline='top';
      ctx.fillStyle='#c9a84c99';
      ctx.fillText(p.label, p.bx+10, p.by+7);
    });
  }

  // Edges
  edges.forEach(e=>{
    if (!vis.has(e.from)||!vis.has(e.to)) return;
    const a=nm[e.from],b=nm[e.to];
    const hl=selId&&(e.from===selId||e.to===selId);
    if (!selId&&!e.dead) return;
    ctx.globalAlpha=hl?0.85:selId?0.05:0.15;
    ctx.strokeStyle=e.dead?'#E24B4A':'#c9a84c';
    ctx.lineWidth=hl?2:1;
    ctx.setLineDash(e.dead?[4,3]:[]);
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
    ctx.setLineDash([]);
  });

  // Nodes
  visible().forEach(n=>{
    const c=COL[n.type]||COL.active;
    const isSel=n.id===selId, isHov=n.id===hovId;
    const connected=selId&&(nm[selId]?.callers.includes(n.id)||nm[selId]?.callees.includes(n.id));
    const dim=selId&&!isSel&&!connected?0.15:1;
    ctx.globalAlpha=dim;
    if(isSel){ctx.shadowColor=c.stroke;ctx.shadowBlur=16;}
    ctx.fillStyle=c.fill;
    ctx.strokeStyle=isSel?'#fff':isHov?c.stroke:c.stroke+'88';
    ctx.lineWidth=isSel?2.5:isHov?1.5:0.8;
    ctx.beginPath();
    ctx.roundRect(n.x-NW/2,n.y-NH/2,NW,NH,8);
    ctx.fill(); ctx.stroke();
    ctx.shadowBlur=0;
    ctx.fillStyle=c.text;
    ctx.font=(isSel?'600 ':'500 ')+FONT+'px -apple-system,sans-serif';
    ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText(n.name,n.x,n.y);
  });

  ctx.globalAlpha=1;
  ctx.restore();
}

/* ── SIDEBAR ─────────────────────────────────────────────────── */
function renderSidebar() {
  const v=visible().sort((a,b)=>(b.isDead?1:0)-(a.isDead?1:0)||a.name.localeCompare(b.name));
  document.getElementById('sb-head').textContent=v.length+' '+(view==='file'?'files':'functions');
  document.getElementById('sb-list').innerHTML=v.map(n=>{
    const tag=n.isDead?'<span class="dead-tag">dead</span>':'';
    const meta=view==='file'&&n.deadCount?n.deadCount+' dead fn':(n.file.split('/').slice(-2).join('/'));
    return `<div class="sb-item${n.id===selId?' sel':''}" onclick="pickNode(${JSON.stringify(n.id)})">
      <div class="sb-name">${n.fullName||n.name}${tag}</div>
      <div class="sb-meta">${meta}</div>
    </div>`;
  }).join('');
}

/* ── DETAIL ──────────────────────────────────────────────────── */
function renderDetail(id) {
  const d=document.getElementById('detail');
  const n=nodes.find(x=>x.id===id);
  if(!n){d.innerHTML='<div class="d-empty">Click any node<br>to see details</div>';return;}
  const c=COL[n.type]||COL.active;
  const crs=nodes.filter(x=>n.callers.includes(x.id));
  const ces=nodes.filter(x=>n.callees.includes(x.id));
  const labels={entry:'Entry point',active:'Clean file',dead:'All dead',mixed:'Has dead code'};
  let h=`<div class="d-name">${n.fullName||n.name}</div>
    <div class="d-file">${n.file}</div>
    <span class="d-tag" style="background:${c.fill};color:${c.text};border:1px solid ${c.stroke}">${labels[n.type]||n.type}</span>`;
  if(n.totalCount){
    h+=`<div class="d-sec">Functions</div>
      <div class="d-stat">${n.totalCount} total${n.deadCount?` · <span style="color:#e05a3a">${n.deadCount} dead</span>`:''}</div>`;
  }
  h+=`<div class="d-sec">Imported by (${crs.length})</div>`;
  if(crs.length) crs.slice(0,8).forEach(x=>h+=`<span class="d-fn" onclick="pickNode(${JSON.stringify(x.id)})">${x.fullName||x.name}</span>`);
  else h+=`<div style="font-size:12px;color:#4a4a40;font-style:italic">Nothing calls this</div>`;
  h+=`<div class="d-sec">Imports (${ces.length})</div>`;
  if(ces.length) ces.slice(0,8).forEach(x=>h+=`<span class="d-fn" onclick="pickNode(${JSON.stringify(x.id)})">${x.fullName||x.name}</span>`);
  else h+=`<div style="font-size:12px;color:#4a4a40;font-style:italic">No tracked imports</div>`;
  d.innerHTML=h;
}

function pickNode(id) {
  selId=selId===id?null:id;
  renderSidebar(); renderDetail(selId); draw();
  // Scroll to node
  if(selId){
    const n=nodes.find(x=>x.id===id);
    if(n){
      panX=wrap.clientWidth/2-n.x*zoom;
      panY=wrap.clientHeight/2-n.y*zoom;
      draw();
    }
  }
}

/* ── MOUSE EVENTS ────────────────────────────────────────────── */
cv.addEventListener('mousedown',e=>{
  dragging=true; didDrag=false; lx=e.clientX; ly=e.clientY;
  cv.classList.add('dragging');
});
cv.addEventListener('mousemove',e=>{
  if(dragging){
    const dx=e.clientX-lx, dy=e.clientY-ly;
    if(Math.abs(dx)+Math.abs(dy)>4) didDrag=true;
    panX+=dx; panY+=dy; lx=e.clientX; ly=e.clientY;
    draw(); return;
  }
  const r=cv.getBoundingClientRect();
  const wx=(e.clientX-r.left-panX)/zoom, wy=(e.clientY-r.top-panY)/zoom;
  const hit=visible().find(n=>Math.abs(n.x-wx)<NW/2+4&&Math.abs(n.y-wy)<NH/2+4);
  hovId=hit?.id||null;
  cv.style.cursor=hit?'pointer':'grab';
  if(hit){
    tip.style.display='block';
    tip.style.left=(e.clientX-r.left+16)+'px';
    tip.style.top=(e.clientY-r.top-10)+'px';
    tip.innerHTML=`<b>${hit.fullName||hit.name}</b>${hit.file}<br>${hit.totalCount||''} functions${hit.deadCount?' · <span style="color:#e05a3a">'+hit.deadCount+' dead</span>':''}`;
  } else tip.style.display='none';
  draw();
});
cv.addEventListener('mouseup',e=>{
  cv.classList.remove('dragging');
  dragging=false;
  if(didDrag){didDrag=false;return;}
  const r=cv.getBoundingClientRect();
  const wx=(e.clientX-r.left-panX)/zoom, wy=(e.clientY-r.top-panY)/zoom;
  const hit=visible().find(n=>Math.abs(n.x-wx)<NW/2+4&&Math.abs(n.y-wy)<NH/2+4);
  if(hit) pickNode(hit.id);
});

// Smooth scroll-to-zoom (trackpad friendly)
cv.addEventListener('wheel',e=>{
  e.preventDefault();
  if(e.ctrlKey || Math.abs(e.deltaY)>50) {
    // Pinch or scroll zoom
    const f=e.deltaY>0?0.9:1.1;
    const r=cv.getBoundingClientRect();
    const mx=e.clientX-r.left, my=e.clientY-r.top;
    panX=(panX-mx)*f+mx; panY=(panY-my)*f+my;
    zoom=Math.max(0.2,Math.min(4,zoom*f));
  } else {
    // Two-finger pan
    panX-=e.deltaX; panY-=e.deltaY;
  }
  updateZoomLabel(); draw();
},{passive:false});

function adjustZoom(f) {
  const cx=wrap.clientWidth/2, cy=wrap.clientHeight/2;
  panX=(panX-cx)*f+cx; panY=(panY-cy)*f+cy;
  zoom=Math.max(0.2,Math.min(4,zoom*f));
  updateZoomLabel(); draw();
}
function updateZoomLabel(){ document.getElementById('zlbl').textContent=Math.round(zoom*100)+'%'; }
function resetView(){ panX=30;panY=30;zoom=1.0;updateZoomLabel();draw(); }

/* ── FILTERS ─────────────────────────────────────────────────── */
function visible() {
  return nodes.filter(n=>{
    if(deadOnly&&!n.isDead) return false;
    if(searchQ&&!n.fullName?.toLowerCase().includes(searchQ)&&!n.file.toLowerCase().includes(searchQ)) return false;
    return true;
  });
}
function doSearch(q){ searchQ=q.toLowerCase(); renderSidebar(); draw(); }
function showDead(btn){ deadOnly=!deadOnly; btn.classList.toggle('on',deadOnly); renderSidebar(); draw(); }
function setView(v,btn){
  view=v; selId=null;
  document.querySelectorAll('.controls .btn').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  if(v==='file') buildFileGraph(); else buildFnGraph();
}

new ResizeObserver(()=>{resize();draw();}).observe(wrap);
window.addEventListener('load', init);
</script>
</body>
</html>"""
    # Inject data - replace placeholders
    html = html.replace("__PROJECT_NAME__", project_name)
    html = html.replace("__RAW_DATA__", raw_data_json)
    return html


@click.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--no-git", is_flag=True, help="Skip git history analysis")
@click.option("--output", default=None, help="Save HTML to file instead of opening browser")
@click.option("--min-confidence", default=40, help="Min confidence for dead code flagging")
def cli(path, no_git, output, min_confidence):
    """
    Generate an interactive call graph of your codebase.

    Examples:

      archaeologist-graph ./my-project

      archaeologist-graph . --output graph.html

      archaeologist-graph . --no-git
    """
    abs_path = os.path.abspath(path)
    project_name = Path(abs_path).name

    console.print(f"\n[dim]  ☠ archaeologist-graph — {project_name}[/dim]\n")

    with console.status("[dim]Parsing files...[/dim]", spinner="dots"):
        scan_result = scan_directory(abs_path)

    total = sum(len(v) for v in scan_result.definitions.values())
    console.print(f"[dim]  Found {total} functions across {len(scan_result.calls)} files[/dim]")

    git_info_map = {}
    if not no_git:
        with console.status("[dim]Analyzing git history...[/dim]", spinner="dots"):
            git_info_map = analyze_git_history(abs_path, list(scan_result.calls.keys()))

    with console.status("[dim]Scoring...[/dim]", spinner="dots"):
        candidates = analyze(scan_result, git_info_map, min_confidence=min_confidence)

    # Count duplicate names
    name_counts = {}
    for name, defs in scan_result.definitions.items():
        name_counts[name] = len([d for d in defs if not d.is_test])

    # Pre-filter in Python before sending to browser
    SKIP_PATHS = ['macos/', 'ios/', 'android/', 'windows/', 'linux/',
                  'ephemeral', 'GeneratedPlugin', '.g.dart', 'AppDelegate',
                  'scripts/', 'test/', 'generated/', 'Runner/']
    # Only filter genuinely universal boilerplate - NOT app-specific names
    NOISE_NAMES = {
        # Serialization boilerplate
        'toJson','fromJson','toMap','fromMap','copyWith','toList','fromList',
        'toDict','fromDict','to_json','from_json','serialize','deserialize',
        'encode','decode','marshal','unmarshal','props',
        # Universal language builtins
        'toString','hashCode','equals','compareTo','from','into','fmt',
        'noSuchMethod',
        # Flutter widget lifecycle (every widget has these)
        'build','createState','initState','dispose','setState',
        'didChangeDependencies','didUpdateWidget','deactivate',
        'reassemble','debugFillProperties',
        # Flutter/platform generated boilerplate
        'RegisterGeneratedPlugins','registerWith','attachBaseContext',
        'configureFlutterEngine','awakeFromNib','viewDidLoad',
        'applicationShouldTerminate','applicationSupportsSecureRestorableState',
        # One-letter or very generic
        'main',
    }

    functions = []
    for name, defs in scan_result.definitions.items():
        if name in NOISE_NAMES:
            continue
        for d in defs:
            if d.is_test:
                continue
            rel = os.path.relpath(d.file, abs_path)
            # Skip platform/generated files
            if any(p in rel for p in SKIP_PATHS):
                continue
            functions.append({
                "name": d.name,
                "file": rel,
                "line": d.line,
                "language": d.language,
                "duplicate": name_counts.get(name, 0) > 1,
            })

    dead = []
    for c in candidates:
        dead.append({
            "name": c.name,
            "file": os.path.relpath(c.file, abs_path),
            "confidence": c.confidence,
            "label": c.label,
            "reasons": c.reasons,
        })

    calls = []
    for filepath, called_names in scan_result.calls.items():
        rel = os.path.relpath(filepath, abs_path)
        clean = [n for n in called_names
                 if not n.startswith("__qualified__") and not n.startswith("__imported__")]
        if clean:
            calls.append({"file": rel, "called": list(clean)[:40]})

    raw_data = {
        "project": project_name,
        "functions": functions[:500],
        "dead": dead,
        "calls": calls[:500],
    }

    html_content = build_html(project_name, json.dumps(raw_data))

    if output:
        out_path = os.path.abspath(output)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        console.print(f"\n[green]✓ Graph saved:[/green] {out_path}")
        console.print(f"[dim]  Open with: open {out_path}[/dim]\n")
    else:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.html', delete=False,
            prefix='archaeologist_graph_', encoding='utf-8'
        ) as f:
            f.write(html_content)
            tmp_path = f.name
        webbrowser.open(f'file://{tmp_path}')
        console.print(f"\n[green]✓ Graph opened in browser![/green]")
        console.print(f"[dim]  To save permanently: archaeologist-graph . --output graph.html[/dim]\n")


if __name__ == "__main__":
    cli()
