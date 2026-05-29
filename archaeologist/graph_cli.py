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
<script src="https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 100%; height: 100%; overflow: hidden; background: #0c0c0a; color: #e8e4dc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }

/* TOP BAR */
.topbar { height: 50px; background: #111110; border-bottom: 1px solid #2a2a24; display: flex; align-items: center; gap: 12px; padding: 0 18px; flex-shrink: 0; position: relative; z-index: 100; }
.logo { font-family: Georgia, serif; font-size: 14px; color: #c9a84c; font-style: italic; letter-spacing: .02em; }
.divider { color: #2a2a24; font-size: 18px; }
.stat { font-size: 11px; color: #6b6b5f; }
.stat b { color: #e8e4dc; }
.controls { margin-left: auto; display: flex; gap: 6px; align-items: center; }
.search { font-size: 12px; padding: 5px 14px; border-radius: 20px; border: 1px solid #2a2a24; background: #1a1a17; color: #e8e4dc; outline: none; width: 200px; transition: border .2s; }
.search:focus { border-color: #c9a84c; }
.search::placeholder { color: #3a3a30; }
.btn { font-size: 11px; padding: 5px 14px; border-radius: 20px; border: 1px solid #2a2a24; background: transparent; color: #6b6b5f; cursor: pointer; transition: all .15s; white-space: nowrap; font-family: inherit; }
.btn:hover { border-color: #c9a84c55; color: #c9a84c; }
.btn.on { background: #c9a84c; color: #0c0c0a; border-color: #c9a84c; font-weight: 600; }

/* LAYOUT */
.layout { display: flex; height: calc(100vh - 50px); }

/* SIDEBAR */
.sidebar { width: 210px; flex-shrink: 0; background: #111110; border-right: 1px solid #2a2a24; display: flex; flex-direction: column; overflow: hidden; }
.sb-head { padding: 10px 14px; border-bottom: 1px solid #2a2a24; font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #4a4a40; font-weight: 600; }
.sb-list { overflow-y: auto; flex: 1; }
.sb-item { padding: 8px 12px; border-bottom: 1px solid #181816; cursor: pointer; transition: background .1s; }
.sb-item:hover { background: #181816; }
.sb-item.sel { background: #1e1c14; border-left: 2px solid #c9a84c; padding-left: 10px; }
.sb-name { font-size: 12px; color: #e0dccc; font-family: 'SF Mono', 'Fira Code', monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sb-meta { font-size: 10px; color: #6b6b5f; margin-top: 2px; }
.dead-dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: #e05a3a; margin-right: 4px; vertical-align: middle; }

/* CANVAS */
.canvas-wrap { flex: 1; position: relative; overflow: hidden; }
svg#graph { position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: grab; }
svg#graph.drag { cursor: grabbing; }

/* SVG node cards */
.node-card { cursor: pointer; }
.node-card:hover .card-bg { filter: brightness(1.12); }
.card-bg { rx: 10; ry: 10; }
.card-header { font-family: 'SF Mono', 'Fira Code', monospace; font-weight: 600; }
.card-fn { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 10px; }

/* DETAIL PANEL */
.detail { width: 230px; flex-shrink: 0; background: #111110; border-left: 1px solid #2a2a24; padding: 14px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.d-empty { font-size: 12px; color: #3a3a30; font-style: italic; text-align: center; margin-top: 3rem; line-height: 1.8; }
.d-name { font-size: 13px; font-weight: 600; color: #e8e4dc; font-family: monospace; word-break: break-all; }
.d-path { font-size: 10px; color: #6b6b5f; margin-top: 2px; }
.d-badge { display: inline-block; font-size: 10px; padding: 2px 8px; border-radius: 99px; margin-top: 8px; }
.d-sec { font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: #3a3a30; font-weight: 600; margin: 10px 0 5px; }
.d-item { font-size: 11px; color: #74b9ff; font-family: monospace; cursor: pointer; padding: 2px 0; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.d-item:hover { color: #c9a84c; }
.d-none { font-size: 11px; color: #3a3a30; font-style: italic; }

/* ZOOM CONTROLS */
.zoom-wrap { position: absolute; bottom: 18px; right: 18px; display: flex; flex-direction: column; gap: 4px; align-items: center; z-index: 50; }
.zbtn { width: 32px; height: 32px; border-radius: 8px; background: #1a1a17; border: 1px solid #2a2a24; color: #c9a84c; font-size: 16px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s; font-family: inherit; }
.zbtn:hover { background: #c9a84c; color: #0c0c0a; border-color: #c9a84c; }
.zlabel { font-size: 10px; color: #4a4a40; font-family: monospace; margin-top: 2px; }

/* LEGEND */
.legend { position: absolute; bottom: 18px; left: 18px; background: rgba(17,17,16,.95); border: 1px solid #2a2a24; border-radius: 10px; padding: 10px 12px; z-index: 50; backdrop-filter: blur(8px); }
.leg-row { display: flex; align-items: center; gap: 7px; margin-bottom: 5px; font-size: 10px; color: #6b6b5f; }
.leg-row:last-child { margin-bottom: 0; }
.leg-sq { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }

/* TOOLTIP */
.tip { position: absolute; background: #1a1a17cc; border: 1px solid #2a2a24; border-radius: 8px; padding: 8px 12px; font-size: 11px; color: #b0aa9a; pointer-events: none; max-width: 200px; line-height: 1.6; display: none; z-index: 200; backdrop-filter: blur(8px); box-shadow: 0 4px 20px rgba(0,0,0,.5); }
.tip b { color: #e8e4dc; display: block; margin-bottom: 2px; font-size: 12px; }

::-webkit-scrollbar { width: 3px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: #2a2a24; border-radius: 2px; }
</style>
</head>
<body>

<div class="topbar">
  <span class="logo">☠ archaeologist-graph</span>
  <span class="divider">|</span>
  <span class="stat"><b id="s-fns">0</b> functions</span>
  <span class="divider" style="font-size:10px">·</span>
  <span class="stat"><b id="s-dead" style="color:#e05a3a">0</b> unused</span>
  <span class="divider" style="font-size:10px">·</span>
  <span class="stat"><b id="s-files">0</b> files</span>
  <div class="controls">
    <input class="search" type="text" placeholder="Search files…" oninput="doSearch(this.value)">
    <button class="btn" onclick="showDead(this)">Show unused only</button>
    <button class="btn" onclick="resetView()">Reset view</button>
    <button class="zbtn" onclick="adjustZoom(1.2)" style="border-radius:20px;width:auto;padding:5px 10px;font-size:13px">+</button>
    <button class="zbtn" onclick="adjustZoom(0.83)" style="border-radius:20px;width:auto;padding:5px 10px;font-size:13px">−</button>
  </div>
</div>

<div class="layout">
  <div class="sidebar">
    <div class="sb-head" id="sb-head">Files</div>
    <div class="sb-list" id="sb-list"></div>
  </div>

  <div class="canvas-wrap" id="wrap">
    <svg id="graph">
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M1,1 L9,5 L1,9" fill="none" stroke="#c9a84c44" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </marker>
        <marker id="arr-dead" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M1,1 L9,5 L1,9" fill="none" stroke="#e05a3a66" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </marker>
        <filter id="glow">
          <feGaussianBlur stdDeviation="3" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="glow-strong">
          <feGaussianBlur stdDeviation="6" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      <g id="zoom-group">
        <g id="edges-layer"></g>
        <g id="nodes-layer"></g>
      </g>
    </svg>
    <div class="tip" id="tip"></div>
    <div class="legend">
      <div class="leg-row"><div class="leg-sq" style="background:#1a3a2a;border:1px solid #0F6E56"></div>Clean file</div>
      <div class="leg-row"><div class="leg-sq" style="background:#3a2a0a;border:1px solid #c9a84c"></div>Has unused code</div>
      <div class="leg-row"><div class="leg-sq" style="background:#3a1010;border:1px solid #E24B4A"></div>All unused</div>
      <div class="leg-row"><div class="leg-sq" style="background:#1a1a3a;border:1px solid #534AB7"></div>Entry point</div>
    </div>
  </div>

  <div class="detail" id="detail">
    <div class="d-empty">Click any card<br>to inspect it</div>
  </div>
</div>

<script>
const DATA = __RAW_DATA__;
const svg = document.getElementById('graph');
const zg = document.getElementById('zoom-group');
const edgesLayer = document.getElementById('edges-layer');
const nodesLayer = document.getElementById('nodes-layer');
const tip = document.getElementById('tip');
const wrap = document.getElementById('wrap');

let zoom = 1, panX = 0, panY = 0;
let dragging = false, didDrag = false, lx = 0, ly = 0;
let selId = null, deadOnly = false, searchQ = '';
let allNodes = [], allEdges = [];

// Folder color palette — dark theme pastels
const FOLDER_COLORS = [
  {bg:'#0d1f17', border:'#1a4a2e', text:'#7ecfa0', head:'#4a9e6b'},
  {bg:'#0d1526', border:'#1a2e5a', text:'#7eb5ff', head:'#4a7ecc'},
  {bg:'#1f0d1f', border:'#4a1a4a', text:'#cf7ecf', head:'#9e4a9e'},
  {bg:'#1f1a0d', border:'#4a3a1a', text:'#cfb07e', head:'#9e7a4a'},
  {bg:'#1a0d0d', border:'#4a1a1a', text:'#cf7e7e', head:'#9e4a4a'},
  {bg:'#0d1a1f', border:'#1a3a4a', text:'#7ecfcf', head:'#4a9e9e'},
  {bg:'#1a1f0d', border:'#3a4a1a', text:'#b0cf7e', head:'#7a9e4a'},
  {bg:'#1f150d', border:'#4a2e1a', text:'#cfaa7e', head:'#9e6a4a'},
];

const SKIP = ['macos/','ios/','android/','windows/','linux/','ephemeral','.g.dart','GeneratedPlugin','Runner/','scripts/'];

function getFolderColor(folder) {
  const folders = [...new Set(allNodes.map(n=>n.folder))].sort();
  const idx = folders.indexOf(folder) % FOLDER_COLORS.length;
  return FOLDER_COLORS[Math.max(0,idx)];
}

function init() {
  document.getElementById('s-fns').textContent = DATA.functions.length;
  document.getElementById('s-dead').textContent = DATA.dead.length;
  document.getElementById('s-files').textContent = new Set(DATA.functions.map(f=>f.file)).size;
  buildGraph();
}

function buildGraph() {
  const fileMap = {};
  DATA.functions.forEach(f => {
    if (SKIP.some(s=>f.file.includes(s))) return;
    if (!fileMap[f.file]) fileMap[f.file] = {funcs:[], dead:0, folder:''};
    fileMap[f.file].funcs.push(f.name);
    const parts = f.file.replace(/^lib\//, '').split('/');
    fileMap[f.file].folder = parts.length >= 3 ? parts[0]+'/'+parts[1] : parts.length===2 ? parts[0] : '_root';
  });
  DATA.dead.forEach(d => {
    if (!fileMap[d.file]) fileMap[d.file] = {funcs:[], dead:0, folder:''};
    fileMap[d.file].dead++;
  });

  // Build node list — limit per folder
  const folderCounts = {};
  const MAX_PER_FOLDER = 10;
  allNodes = [];
  Object.keys(fileMap).forEach(f => {
    const fm = fileMap[f];
    const folder = fm.folder;
    folderCounts[folder] = (folderCounts[folder]||0) + 1;
    if (folderCounts[folder] > MAX_PER_FOLDER) return;
    const name = f.split('/').pop().replace(/\.[^.]+$/,'');
    const isEntry = name==='main' || f==='lib/main.dart';
    const allDead = fm.dead>0 && fm.dead>=fm.funcs.length && fm.funcs.length>0;
    const type = isEntry?'entry': allDead?'dead': fm.dead>0?'mixed':'clean';
    // Top functions to show inside card (prioritize dead ones)
    const deadFns = DATA.dead.filter(d=>d.file===f).map(d=>d.name);
    const liveFns = fm.funcs.filter(fn=>!deadFns.includes(fn)).slice(0,3);
    const showFns = [...deadFns.slice(0,3), ...liveFns].slice(0,5);
    allNodes.push({
      id: f, name, fullName: name, file: f, folder,
      type, isDead: fm.dead>0,
      deadCount: fm.dead, totalCount: fm.funcs.length,
      showFns, deadFns: new Set(deadFns),
      callers:[], callees:[]
    });
  });

  // Build edges (cross-folder only)
  const nm = {};
  allNodes.forEach(n=>nm[n.id]=n);
  const fnToFile = {};
  DATA.functions.forEach(f=>{ fnToFile[f.name]=f.file; });
  allEdges = [];
  DATA.calls.forEach(c => {
    if (!nm[c.file]) return;
    c.called.forEach(cal => {
      const tf = fnToFile[cal];
      if (!tf||tf===c.file||!nm[tf]) return;
      if (nm[c.file].folder===nm[tf].folder) return;
      if (!allEdges.find(e=>e.from===c.file&&e.to===tf)) {
        allEdges.push({from:c.file, to:tf, dead: nm[c.file].isDead&&nm[tf].isDead});
        nm[c.file].callees.push(tf);
        nm[tf].callers.push(c.file);
      }
    });
  });

  layoutAndRender();
}

function getCardDims(node) {
  const W = 175;
  const HEADER_H = 34;
  const FN_H = 16;
  const PAD_B = 10;
  const H = HEADER_H + node.showFns.length * FN_H + PAD_B;
  return {w: W, h: H};
}

function layoutAndRender() {
  const visible = getVisible();
  if (!visible.length) { edgesLayer.innerHTML=''; nodesLayer.innerHTML=''; renderSidebar(); return; }

  // Group visible nodes by folder
  const folderGroups = {};
  visible.forEach(n => {
    if (!folderGroups[n.folder]) folderGroups[n.folder] = [];
    folderGroups[n.folder].push(n);
  });

  // Sort folders by name
  const sortedFolders = Object.keys(folderGroups).sort();

  // Layout constants
  const CARD_GAP_X = 20;   // gap between cards horizontally
  const CARD_GAP_Y = 20;   // gap between rows within a folder
  const FOLDER_GAP_Y = 44; // gap between folders
  const MAX_COLS = 5;       // max cards per row
  const PAD_X = 36;
  let curY = 36;
  const nodePositions = {};

  sortedFolders.forEach(folder => {
    const fnodes = folderGroups[folder];

    // Split into rows of MAX_COLS
    let rowStartY = curY;
    for (let rowStart = 0; rowStart < fnodes.length; rowStart += MAX_COLS) {
      const rowNodes = fnodes.slice(rowStart, rowStart + MAX_COLS);
      const rowH = Math.max(...rowNodes.map(n => getCardDims(n).h));
      let curX = PAD_X;

      rowNodes.forEach(n => {
        const {w, h} = getCardDims(n);
        nodePositions[n.id] = {x: curX + w/2, y: rowStartY + h/2, w, h};
        curX += w + CARD_GAP_X;
      });

      rowStartY += rowH + CARD_GAP_Y;
    }

    curY = rowStartY + FOLDER_GAP_Y;
  });

  // Build dagre graph for edge routing only
  const g = new dagre.graphlib.Graph();
  g.setGraph({rankdir:'TB', ranksep:40, nodesep:16});
  g.setDefaultEdgeLabel(()=>({}));

  visible.forEach(n => {
    const pos = nodePositions[n.id];
    if (pos) g.setNode(n.id, {x: pos.x, y: pos.y, width: pos.w, height: pos.h, label: n.id});
  });

  const visIds = new Set(visible.map(n=>n.id));
  allEdges.forEach(e => {
    if (visIds.has(e.from) && visIds.has(e.to)) {
      g.setEdge(e.from, e.to, {dead: e.dead});
    }
  });

  // Apply our positions to dagre nodes
  visible.forEach(n => {
    const pos = nodePositions[n.id];
    if (pos && g.node(n.id)) {
      const gn = g.node(n.id);
      gn.x = pos.x; gn.y = pos.y;
    }
  });

  // Draw edges manually using our node positions
  edgesLayer.innerHTML = '';
  const posMap = {};
  visible.forEach(n => { posMap[n.id] = nodePositions[n.id]; });

  allEdges.forEach(e => {
    if (!posMap[e.from] || !posMap[e.to]) return;
    const a = posMap[e.from], b = posMap[e.to];
    const isConnected = selId && (e.from===selId||e.to===selId);
    const opacity = selId ? (isConnected?0.85:0.04) : 0.25;
    // always draw edges

    // Draw curved line from bottom of source to top of dest
    const x1 = a.x, y1 = a.y + a.h/2;
    const x2 = b.x, y2 = b.y - b.h/2;
    const cy = (y1+y2)/2;
    const d = `M${x1},${y1} C${x1},${cy} ${x2},${cy} ${x2},${y2}`;

    const path = document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d', d);
    path.setAttribute('fill','none');
    path.setAttribute('stroke', e.dead?'#e05a3a':'#c9a84c');
    path.setAttribute('stroke-width', isConnected?'3':'1.5');
    path.setAttribute('stroke-opacity', selId ? (isConnected?1:0.06) : 0.5);
    path.setAttribute('stroke-dasharray', e.dead?'5,4':'');
    path.setAttribute('marker-end', e.dead?'url(#arr-dead)':'url(#arr)');
    edgesLayer.appendChild(path);
  });

  // Render nodes
  nodesLayer.innerHTML = '';
  visible.forEach(n => {
    const gn = g.node(n.id);
    if (!gn) return;
    const {w,h} = getCardDims(n);
    const x = gn.x - w/2, y = gn.y - h/2;
    const col = getFolderColor(n.folder);
    const isSel = n.id===selId;
    const dimmed = selId && !isSel && !allNodes.find(x=>x.id===selId)?.callers.includes(n.id) && !allNodes.find(x=>x.id===selId)?.callees.includes(n.id);

    // Card type colors
    let bgColor, borderColor, headColor;
    if (n.type==='entry') { bgColor='#1a1a3a'; borderColor='#534AB7'; headColor='#7a76ff'; }
    else if (n.type==='dead') { bgColor='#2a0f0f'; borderColor='#E24B4A'; headColor='#ff6b6b'; }
    else if (n.type==='mixed') { bgColor='#2a1f0a'; borderColor='#c9a84c'; headColor='#e8c96d'; }
    else { bgColor=col.bg; borderColor=col.border; headColor=col.head; }

    const g_el = document.createElementNS('http://www.w3.org/2000/svg','g');
    g_el.setAttribute('class','node-card');
    g_el.setAttribute('opacity', dimmed?'0.15':'1');
    g_el.setAttribute('data-id', n.id);
    if (isSel) g_el.setAttribute('filter','url(#glow)');

    // Card background
    const rect = document.createElementNS('http://www.w3.org/2000/svg','rect');
    rect.setAttribute('x',x); rect.setAttribute('y',y);
    rect.setAttribute('width',w); rect.setAttribute('height',h);
    rect.setAttribute('rx','10'); rect.setAttribute('ry','10');
    rect.setAttribute('fill',bgColor);
    rect.setAttribute('stroke', isSel?'#fff':borderColor);
    rect.setAttribute('stroke-width', isSel?'2':'1');
    g_el.appendChild(rect);

    // Header background strip
    const headerRect = document.createElementNS('http://www.w3.org/2000/svg','rect');
    headerRect.setAttribute('x',x+1); headerRect.setAttribute('y',y+1);
    headerRect.setAttribute('width',w-2); headerRect.setAttribute('height','24');
    headerRect.setAttribute('rx','9'); headerRect.setAttribute('ry','9');
    headerRect.setAttribute('fill',borderColor+'33');
    g_el.appendChild(headerRect);

    // Bottom cover to make header rect look like top-only
    const headerCover = document.createElementNS('http://www.w3.org/2000/svg','rect');
    headerCover.setAttribute('x',x+1); headerCover.setAttribute('y',y+16);
    headerCover.setAttribute('width',w-2); headerCover.setAttribute('height','10');
    headerCover.setAttribute('fill',bgColor);
    g_el.appendChild(headerCover);

    // Dead count badge
    if (n.deadCount>0) {
      const badgeR = document.createElementNS('http://www.w3.org/2000/svg','rect');
      badgeR.setAttribute('x',x+w-36); badgeR.setAttribute('y',y+6);
      badgeR.setAttribute('width','28'); badgeR.setAttribute('height','14');
      badgeR.setAttribute('rx','7'); badgeR.setAttribute('fill','#E24B4A33');
      badgeR.setAttribute('stroke','#E24B4A66'); badgeR.setAttribute('stroke-width','0.5');
      g_el.appendChild(badgeR);
      const badgeT = document.createElementNS('http://www.w3.org/2000/svg','text');
      badgeT.setAttribute('x',x+w-22); badgeT.setAttribute('y',y+16);
      badgeT.setAttribute('text-anchor','middle'); badgeT.setAttribute('font-size','9');
      badgeT.setAttribute('fill','#E24B4A'); badgeT.setAttribute('font-family','monospace');
      badgeT.textContent = n.deadCount+'☠';
      g_el.appendChild(badgeT);
    }

    // File name
    const nameText = document.createElementNS('http://www.w3.org/2000/svg','text');
    nameText.setAttribute('x',x+10); nameText.setAttribute('y',y+16);
    nameText.setAttribute('font-size','12'); nameText.setAttribute('font-weight','600');
    nameText.setAttribute('fill',headColor); nameText.setAttribute('font-family','SF Mono, Fira Code, monospace');
    const dispName = n.name.length>17 ? n.name.slice(0,15)+'…' : n.name;
    nameText.textContent = dispName;
    g_el.appendChild(nameText);

    // Thin separator line
    const sep = document.createElementNS('http://www.w3.org/2000/svg','line');
    sep.setAttribute('x1',x+8); sep.setAttribute('y1',y+27);
    sep.setAttribute('x2',x+w-8); sep.setAttribute('y2',y+27);
    sep.setAttribute('stroke',borderColor); sep.setAttribute('stroke-width','0.5'); sep.setAttribute('stroke-opacity','0.4');
    g_el.appendChild(sep);

    // Function list
    n.showFns.forEach((fn, i) => {
      const isDead = n.deadFns.has(fn);
      const fnText = document.createElementNS('http://www.w3.org/2000/svg','text');
      fnText.setAttribute('x',x+10); fnText.setAttribute('y',y+42+i*16);
      fnText.setAttribute('font-size','10'); fnText.setAttribute('font-family','SF Mono, Fira Code, monospace');
      fnText.setAttribute('fill', isDead?'#e05a3a88':'#88887a');
      const dispFn = fn.length>20 ? fn.slice(0,18)+'…' : fn;
      fnText.textContent = (isDead?'☠ ':' ·  ') + dispFn;
      g_el.appendChild(fnText);
    });

    // Folder label at bottom
    const folderText = document.createElementNS('http://www.w3.org/2000/svg','text');
    folderText.setAttribute('x',x+w-8); folderText.setAttribute('y',y+h-5);
    folderText.setAttribute('text-anchor','end'); folderText.setAttribute('font-size','8');
    folderText.setAttribute('fill',borderColor); folderText.setAttribute('fill-opacity','0.5');
    folderText.setAttribute('font-family','SF Mono, monospace');
    folderText.textContent = n.folder.split('/').pop()+'/';
    g_el.appendChild(folderText);

    // Invisible click target
    const hitRect = document.createElementNS('http://www.w3.org/2000/svg','rect');
    hitRect.setAttribute('x',x); hitRect.setAttribute('y',y);
    hitRect.setAttribute('width',w); hitRect.setAttribute('height',h);
    hitRect.setAttribute('fill','transparent');
    hitRect.setAttribute('data-id', n.id);
    g_el.appendChild(hitRect);

    nodesLayer.appendChild(g_el);
  });

  // Auto-fit on first load
  if (!selId) fitToScreen(g);
  renderSidebar();
}

function fitToScreen(g) {
  try {
    // Always start at zoom=1, top-left corner visible
    // User scrolls down to see more
    zoom = 1.0;
    panX = 0;
    panY = 0;
    applyTransform();
  } catch(e) { zoom=1; panX=0; panY=0; applyTransform(); }
}

function applyTransform() {
  zg.setAttribute('transform', `translate(${panX},${panY}) scale(${zoom})`);
}

function adjustZoom(f) {
  const cx=wrap.clientWidth/2, cy=wrap.clientHeight/2;
  panX=(panX-cx)*f+cx; panY=(panY-cy)*f+cy;
  zoom=Math.max(0.15,Math.min(5,zoom*f));
  applyTransform();
}

function resetView() {
  // Rebuild and refit
  selId=null;
  layoutAndRender();
}

// Mouse events
svg.addEventListener('mousedown',e=>{
  dragging=true; didDrag=false; lx=e.clientX; ly=e.clientY;
  svg.classList.add('drag');
});
window.addEventListener('mousemove',e=>{
  if(!dragging) return;
  const dx=e.clientX-lx, dy=e.clientY-ly;
  if(Math.abs(dx)+Math.abs(dy)>3) didDrag=true;
  panX+=dx; panY+=dy; lx=e.clientX; ly=e.clientY;
  applyTransform();
});
window.addEventListener('mouseup',e=>{
  svg.classList.remove('drag');
  if(!dragging){dragging=false;return;}
  dragging=false;
  if(didDrag){didDrag=false;return;}
  const target=e.target.closest('[data-id]');
  if(target){ pickNode(target.getAttribute('data-id')); }
});
svg.addEventListener('wheel',e=>{
  e.preventDefault();
  if(Math.abs(e.deltaY)<5&&!e.ctrlKey){
    panX-=e.deltaX*0.8; panY-=e.deltaY*0.8; applyTransform(); return;
  }
  const f=e.deltaY>0?0.88:1.14;
  const r=svg.getBoundingClientRect();
  const mx=e.clientX-r.left, my=e.clientY-r.top;
  panX=(panX-mx)*f+mx; panY=(panY-my)*f+my;
  zoom=Math.max(0.15,Math.min(5,zoom*f));
  applyTransform();
},{passive:false});

// Hover tooltip
svg.addEventListener('mousemove',e=>{
  if(dragging) return;
  const target=e.target.closest('[data-id]');
  const r=svg.getBoundingClientRect();
  if(target){
    const id=target.getAttribute('data-id');
    const n=allNodes.find(x=>x.id===id);
    if(n){
      tip.style.display='block';
      tip.style.left=(e.clientX-r.left+14)+'px';
      tip.style.top=(e.clientY-r.top-8)+'px';
      tip.innerHTML=`<b>${n.fullName}</b>${n.folder}/<br>${n.totalCount} functions${n.deadCount?` · <span style="color:#e05a3a">${n.deadCount} unused</span>`:''}`;
    }
  } else {
    tip.style.display='none';
  }
});
svg.addEventListener('mouseleave',()=>tip.style.display='none');

function pickNode(id) {
  selId = selId===id ? null : id;
  layoutAndRender();
  if(selId) {
    renderDetail(selId);
    // Scroll sidebar to selected
    const selEl = document.querySelector('.sb-item.sel');
    if(selEl) selEl.scrollIntoView({block:'nearest'});
  } else {
    document.getElementById('detail').innerHTML='<div class="d-empty">Click any card<br>to inspect it</div>';
  }
}

function renderSidebar() {
  const vis = getVisible().sort((a,b)=>(b.isDead?1:0)-(a.isDead?1:0)||a.folder.localeCompare(b.folder)||a.name.localeCompare(b.name));
  document.getElementById('sb-head').textContent = vis.length+' files';
  document.getElementById('sb-list').innerHTML = vis.map(n=>{
    const dot = n.isDead ? '<span class="dead-dot"></span>' : '';
    return `<div class="sb-item${n.id===selId?' sel':''}" onclick="pickNode(${JSON.stringify(n.id)})">
      <div class="sb-name">${dot}${n.fullName}</div>
      <div class="sb-meta">${n.folder}/${n.deadCount?' · '+n.deadCount+' unused':''}</div>
    </div>`;
  }).join('');
}

function renderDetail(id) {
  const n = allNodes.find(x=>x.id===id);
  const d = document.getElementById('detail');
  if(!n){d.innerHTML='<div class="d-empty">Click any card<br>to inspect it</div>';return;}
  const callers = allNodes.filter(x=>n.callers.includes(x.id));
  const callees = allNodes.filter(x=>n.callees.includes(x.id));
  const typeLabels = {clean:'Clean file',mixed:'Has unused code',dead:'All unused',entry:'Entry point'};
  const typeColors = {clean:'#4a9e6b',mixed:'#c9a84c',dead:'#e05a3a',entry:'#534AB7'};
  let h = `<div class="d-name">${n.fullName}</div>
    <div class="d-path">${n.file}</div>
    <span class="d-badge" style="background:${typeColors[n.type]}22;color:${typeColors[n.type]};border:1px solid ${typeColors[n.type]}44">${typeLabels[n.type]}</span>
    <div class="d-sec">Functions</div>
    <div style="font-size:11px;color:#b0aa9a">${n.totalCount} total${n.deadCount?` · <span style="color:#e05a3a">${n.deadCount} unused</span>`:''}</div>`;
  if(n.showFns.length){
    h+=`<div class="d-sec">In this file</div>`;
    n.showFns.forEach(fn=>{
      const dead=n.deadFns.has(fn);
      h+=`<span class="d-item" style="color:${dead?'#e05a3a':'#74b9ff'}">${dead?'☠ ':''} ${fn}</span>`;
    });
  }
  h+=`<div class="d-sec">Called by (${callers.length})</div>`;
  if(callers.length) callers.slice(0,6).forEach(x=>h+=`<span class="d-fn d-item" onclick="pickNode(${JSON.stringify(x.id)})">${x.fullName}</span>`);
  else h+=`<div class="d-none">Nothing visible calls this</div>`;
  h+=`<div class="d-sec">Calls (${callees.length})</div>`;
  if(callees.length) callees.slice(0,6).forEach(x=>h+=`<span class="d-fn d-item" onclick="pickNode(${JSON.stringify(x.id)})">${x.fullName}</span>`);
  else h+=`<div class="d-none">No tracked outgoing calls</div>`;
  d.innerHTML=h;
}

function getVisible() {
  return allNodes.filter(n=>{
    if(deadOnly&&!n.isDead) return false;
    if(searchQ&&!n.fullName.toLowerCase().includes(searchQ)&&!n.file.toLowerCase().includes(searchQ)&&!n.folder.toLowerCase().includes(searchQ)) return false;
    return true;
  });
}
function doSearch(q){ searchQ=q.toLowerCase(); layoutAndRender(); }
function showDead(btn){ deadOnly=!deadOnly; btn.classList.toggle('on',deadOnly); layoutAndRender(); }

new ResizeObserver(()=>{ if(!selId) resetView(); }).observe(wrap);
window.addEventListener('load',init);
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
