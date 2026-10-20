#!/usr/bin/env python3
"""Render groups.json as one static, bilingual page: a map of institutions and a list of group cards.

  group_map.py groups.json [--out site/index.html] [--correction-url URL] [--about-url URL]

The page lists groups by institution and then PI name; nothing on it ranks groups or countries. A card shows the PI,
institution, homepage, direction tags, topics, members by role, funding, evidence links and the date the group was
last verified, with a link to report a correction. Leaflet and the basemap tiles load from the network when the page
is opened (Leaflet pinned as in talent_map.py); everything else is inline. Standard library only.
"""
from __future__ import annotations
import argparse, html, json, re, sys
from pathlib import Path
from person_fields import normalized

# Placeholder for a run's own page; publish_site.py passes the repository's correction form. Each card appends
# group=<id> to it, after "&" when the URL already carries a query.
CORRECTION_URL = 'https://example.invalid/report-a-correction'
# The in-page about section; a published page links the site's about page instead.
ABOUT_URL = '#about'


def render_html(doc: dict, correction_url: str = CORRECTION_URL, about_url: str = ABOUT_URL) -> str:
    groups = sorted(doc['groups'], key=lambda g: (normalized(g['institution']['name']), normalized(g['pi']['name']), g['id']))
    # No markup characters inside the data block: "</script>" would close it and "<!--<script>" would swallow the page.
    payload = (json.dumps({**doc, 'groups': groups}, ensure_ascii=False)
               .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))
    meta = doc.get('meta', {})
    title = html.escape(f"Research groups · {meta.get('domain') or 'field'} · {meta.get('as_of', '')}")
    # Neither URL may carry markup into the script block; json.dumps quotes them for JavaScript. The card appends the
    # group to the correction URL's query, which a fragment would swallow.
    urls = {'__CORRECTION_URL__': correction_url, '__ABOUT_URL__': about_url}
    if any(re.search(r'[<>"\'\\\s]', url) for url in urls.values()) or '#' in correction_url:
        raise ValueError(f'a correction or about URL with quotes, brackets or spaces, or a correction URL with a fragment: {urls}')
    page = TEMPLATE.replace('__TITLE__', title)
    for marker, url in urls.items():
        page = page.replace(marker, json.dumps(url))
    return page.replace('__DATA__', payload)


TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--bg:#fff;--fg:#1b1b1b;--muted:#6b6b6b;--line:#e4e4e4;--panel:#f7f7f8;--card:#fff;--hover:#eef3fb;--chip:#eef3fb;--accent:#1f5fbf}
@media (prefers-color-scheme: dark){:root{--bg:#121212;--fg:#ececec;--muted:#a3a3a3;--line:#2e2e2e;--panel:#181818;--card:#202020;--hover:#263244;--chip:#263244;--accent:#6fa3ef}}
*{box-sizing:border-box}
html,body{height:100%;margin:0;font:14px/1.5 -apple-system,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",Helvetica,Arial,sans-serif;color:var(--fg);background:var(--bg)}
header{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;padding:8px 14px;border-bottom:1px solid var(--line)}
header h1{font-size:16px;margin:0 6px 0 0}
.counts{color:var(--muted);font-size:12.5px;white-space:nowrap}
header input,header select,header button,.mapctl select{font:inherit;font-size:13px;padding:4px 7px;border:1px solid var(--line);border-radius:5px;background:var(--card);color:var(--fg)}
header input{flex:1 1 260px;min-width:180px}
header button{cursor:pointer}
header .about{font-size:13px}
#lang{margin-left:auto}
main{display:grid;grid-template-columns:minmax(0,1fr) clamp(400px,38vw,700px);height:calc(100% - 50px)}
#mapwrap{position:relative;min-width:0}
#map{height:100%}
.mapctl{position:absolute;top:10px;right:10px;z-index:500}
aside{border-left:1px solid var(--line);background:var(--panel);overflow:auto;padding:10px 16px 24px}
.crumbs{font-size:12.5px;color:var(--muted);margin:2px 0 8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.crumbs a{color:var(--accent);cursor:pointer;text-decoration:none}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin-bottom:10px}
.card h2{margin:0 0 2px;font-size:16px;line-height:1.3}
.card h3{margin:10px 0 4px;font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.sub{color:var(--muted);font-size:12.5px;margin-bottom:6px}
.inst{padding:8px 4px 2px;font-weight:600;cursor:pointer;border-bottom:1px solid var(--line)}
.inst .m{font-weight:400;color:var(--muted);font-size:12.5px}
.lab{margin-left:14px;border-left:2px solid var(--line);padding-left:4px}
.lab>.m{display:block;padding:6px 4px 2px;font-size:12.5px;color:var(--muted)}
.row{padding:6px 4px 6px 14px;border-bottom:1px solid var(--line);cursor:pointer;border-radius:4px}
.row:hover,.inst:hover{background:var(--hover)}
.row .t{font-weight:500}
.row .k{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.role{display:inline-block;font-size:11.5px;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 5px;line-height:17px;vertical-align:1px}
.muted{color:var(--muted)}
dl{display:grid;grid-template-columns:max-content 1fr;gap:3px 12px;margin:4px 0}
dt{color:var(--muted);font-size:12.5px;max-width:130px}
dd{margin:0;min-width:0;word-break:break-word}
a{color:var(--accent)}
.topic{display:inline-block;background:var(--chip);border-radius:4px;padding:1px 7px;margin:2px 4px 2px 0;font-size:12px}
.tag{display:inline-block;border:1px solid var(--accent);color:var(--accent);border-radius:4px;padding:0 5px;margin:1px 4px 1px 0;font-size:11px;line-height:16px}
.names{margin:0 0 4px}
.actions{margin-top:8px;font-size:12.5px;display:flex;gap:14px;flex-wrap:wrap}
.btn{font:inherit;font-size:12px;padding:2px 8px;border:1px solid var(--line);border-radius:4px;background:var(--card);color:var(--accent);cursor:pointer}
details summary{cursor:pointer;color:var(--muted);font-size:12.5px}
#about p{margin:6px 0}
.leaflet-container{font:inherit}
@media (max-width:900px){main{grid-template-columns:1fr;grid-template-rows:45% 55%}aside{border-left:0;border-top:1px solid var(--line)}#lang{margin-left:0}}
</style>
</head>
<body>
<header>
  <h1 id="title"></h1>
  <span class="counts" id="counts"></span>
  <input id="q" type="search">
  <select id="f-country"></select>
  <span id="facets"></span>
  <button id="reset"></button>
  <a class="about" id="about-link"></a>
  <button id="lang">中文</button>
</header>
<main>
  <div id="mapwrap"><div id="map"></div>
    <div class="mapctl"><select id="basemap"></select> <span class="counts" id="tilehint"></span></div></div>
  <aside>
    <div class="crumbs" id="crumbs"></div>
    <div id="panel"></div>
    <section class="card" id="about"></section>
  </aside>
</main>
<script id="group-data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('group-data').textContent);
const CORRECTION_URL = __CORRECTION_URL__;
const ABOUT_URL = __ABOUT_URL__;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Only web links become anchors: a value from a page cannot smuggle in a javascript: URL.
const link = (u, t) => /^https?:\/\//i.test(u || '') ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t || u.replace(/^https?:\/\/(www\.)?/, '').slice(0, 72))}</a>` : esc(t || u);

const I18N = {
  en: {
    title: d => `Research groups · ${d}`, search: 'search PI, institution, member, topic', allCountries: 'all countries', reset: 'reset',
    about: 'About this map', all: 'all', showing: (n, total) => `showing ${n} of ${total} groups`, back: '← back', list: 'All groups',
    showOnMap: 'show on map', approx: 'approximate position', noMatch: 'nothing matches', homepage: 'homepage', lab: 'lab', piPage: 'PI page', tags: 'direction tags',
    topics: 'topics', funding: 'funding records', openSource: 'open source', sources: 'found through', lastVerified: 'last verified',
    fromPage: 'page read', fromRecord: 'date of the newest record, no page read', never: 'not verified', members: 'members', evidence: 'evidence links',
    coauthors: n => `and ${n} coauthor${n === 1 ? '' : 's'} of shared papers, not listed`, project: 'project', correction: 'Report a correction',
    noMembers: 'members not yet collected',
    roles: {professor: 'professor', group_leader: 'group leader', researcher: 'researcher / postdoc', phd_student: 'PhD student', industry: 'industry', unknown: 'role unknown'},
    basemaps: {esri: 'Esri light gray', osmde: 'OpenStreetMap (DE mirror)', osm: 'OpenStreetMap', none: 'no basemap'},
    tileHint: n => `basemap "${n}" is not loading on this network; pick another one, the markers still work`,
    aboutText: m => [
      `A public map of research groups in ${m.domain || 'one field'}, in ${m.region}, as of ${m.as_of}. One entry per group: its PI, institution and homepage. People appear only as names with a role under their group.`,
      'Built from academic public pages (lab, group and institutional pages, read page by page; a sample is checked by hand) and public funding and paper records since ' + m.window_start + '. No LinkedIn data.',
      'Roles come from titles on public pages and from funding records and can be wrong. Groups are listed by institution and then PI name; the order carries no judgement.',
      'Institution positions come from a manual table or a ROR name search; "approximate position" means the centre of the country.',
      'Something wrong or missing? Every card has a "Report a correction" link.'],
  },
  zh: {
    title: d => `研究课题组 · ${d}`, search: '搜索负责人、机构、成员、方向', allCountries: '所有国家', reset: '重置',
    about: '关于本图', all: '全部', showing: (n, total) => `显示 ${n} / ${total} 个课题组`, back: '← 返回', list: '全部课题组',
    showOnMap: '在地图上显示', approx: '位置为近似', noMatch: '没有匹配结果', homepage: '主页', lab: '实验室', piPage: '负责人页面', tags: '方向标签',
    topics: '方向', funding: '资助记录', openSource: '开源', sources: '发现渠道', lastVerified: '最近核实',
    fromPage: '读过页面', fromRecord: '最新记录日期，未读页面', never: '未核实', members: '成员', evidence: '证据链接',
    coauthors: n => `另有 ${n} 位合著者（只共同发表过论文，不列出）`, project: '项目', correction: '报告错误',
    noMembers: '成员未采集',
    roles: {professor: '教授', group_leader: '课题组长', researcher: '研究员/博后', phd_student: '博士生', industry: '业界', unknown: '角色未定'},
    basemaps: {esri: 'Esri 浅灰底图', osmde: 'OpenStreetMap（德国镜像）', osm: 'OpenStreetMap', none: '无底图'},
    tileHint: n => `底图 "${n}" 在当前网络加载不了，换一个即可，圆点不受影响`,
    aboutText: m => [
      `欧洲${m.domain || '某一领域'}研究课题组的公开地图，区域 ${m.region}，截至 ${m.as_of}。每个课题组一条：负责人、机构和主页。人员只以姓名和角色列在所属课题组下。`,
      `数据来自学术公开页面（实验室、课题组和机构页面，逐页阅读，抽样人工核查）以及 ${m.window_start} 以来的公开资助和论文记录。不含领英数据。`,
      '角色取自公开页面上的头衔和资助记录，可能有错。课题组按机构、再按负责人姓名排列，顺序不代表任何评价。',
      '机构位置来自手工表或 ROR 名称检索；"位置为近似"表示用的是国家中心点。',
      '发现错误或遗漏？每张卡片都有"报告错误"链接。'],
  },
};
const FUNDING_ZH = {erc_stg: 'ERC Starting Grant', erc_cog: 'ERC Consolidator', erc_adg: 'ERC Advanced', erc_syg: 'ERC Synergy', erc_poc: 'ERC Proof of Concept',
  dfg_project: 'DFG 项目', dfg_emmy_noether: 'DFG Emmy Noether', snsf_project: 'SNSF 项目', snsf_ambizione: 'SNSF Ambizione', national_project: '国家项目',
  national_fellowship: '国家级资助', swecris_project: '瑞典项目', fris_project: '佛兰德项目', aei_project: '西班牙项目', rcn_project: '挪威项目', fwf_project: '奥地利项目'};
const CHANNEL_ZH = {'funding-de-ch': '德瑞资助', 'funding-eu': 'EU 资助', 'funding-fr-es-nl-be': '法西荷比资助', 'funding-at-se-no-dk': '奥瑞挪丹资助',
  'awards-papers': '获奖论文', competitions: '竞赛', industry: '业界', 'national-prizes': '国家奖项', 'open-source': '开源', startups: '创业'};
let lang = 'en';
try { lang = localStorage.getItem('group-map.lang') || (navigator.language.startsWith('zh') ? 'zh' : 'en'); } catch (e) {}
if (/^(en|zh)$/.test(new URLSearchParams(location.search).get('lang') || '')) lang = new URLSearchParams(location.search).get('lang');
const T = () => I18N[lang];
const fundingLabel = t => lang === 'zh' ? (FUNDING_ZH[t] || t.replace(/_/g, ' ')) : t.replace(/_/g, ' ');
const channelLabel = c => lang === 'zh' ? (CHANNEL_ZH[c] || c) : c;
const roleLabel = r => T().roles[r] || r;
const FACETS = DATA.meta.facets || [];
const TAGS = Object.fromEntries(FACETS.flatMap(f => f.tags.map(t => [t.id, t])));
const i18nLabel = (x, fallback) => (x && (x[lang] || x.en || x.zh)) || fallback;
const tagLabel = id => i18nLabel((TAGS[id] || {}).label, id);
const tagChips = tags => tags.map(t => `<span class="tag">${esc(tagLabel(t))}</span>`).join('');
const ROLE_ORDER = ['professor', 'group_leader', 'researcher', 'phd_student', 'industry', 'unknown'];

// ---- filters (the data arrives sorted by institution, then PI name; filtering keeps that order)
const filters = {q: '', country: '', tags: {}, inst: ''};
function matches(g) {
  if (filters.country && g.institution.country !== filters.country) return false;
  for (const tag of Object.values(filters.tags)) if (tag && !g.tags.includes(tag)) return false;
  if (filters.q) {
    const hay = [g.pi.name, g.institution.name, g.institution.country, ...g.topics, ...g.tags.map(tagLabel), ...g.members.map(m => m.name)].join(' ').toLowerCase();
    if (!hay.includes(filters.q)) return false;
  }
  return true;
}
const visible = () => DATA.groups.filter(matches);
const byId = id => DATA.groups.find(g => g.id === id);

// ---- map: one marker per institution, all the same size
const map = L.map('map', {worldCopyJump: false}).setView([50.5, 9], 5);
const OSM_CREDIT = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const BASEMAPS = {
  esri: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {maxZoom: 16, attribution: 'Tiles &copy; Esri'}],
  osmde: ['https://tile.openstreetmap.de/{z}/{x}/{y}.png', {maxZoom: 19, attribution: OSM_CREDIT}],
  osm: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: OSM_CREDIT}],
};
let tiles = null, tileErrors = 0;
function useBasemap(name) {
  if (tiles) map.removeLayer(tiles);
  tiles = null; tileErrors = 0; $('#tilehint').textContent = '';
  if (!BASEMAPS[name]) return;
  tiles = L.tileLayer(...BASEMAPS[name]).addTo(map);
  tiles.on('tileerror', () => { if (++tileErrors === 3) $('#tilehint').textContent = T().tileHint(T().basemaps[name]); });
}
const layer = L.layerGroup().addTo(map);
let fitPending = true;
function places(groups) {
  const out = new Map();
  for (const g of groups) {
    const loc = g.institution.location;
    if (loc && !out.has(g.institution.name)) out.set(g.institution.name, {name: g.institution.name, ...loc});
  }
  return [...out.values()];
}
function drawMarkers(groups) {
  layer.clearLayers();
  const points = [];
  for (const p of places(groups)) {
    const approx = p.source === 'country centroid';
    const m = L.circleMarker([p.lat, p.lng], {radius: 7, color: '#1f5fbf', weight: 1.5, dashArray: approx ? '3' : null, fillColor: '#1f5fbf', fillOpacity: 0.45});
    m.bindTooltip(`<b>${esc(p.name)}</b>${p.city ? '<br>' + esc(p.city) : ''}${approx ? '<br><i>' + T().approx + '</i>' : ''}`);
    m.on('click', () => show('inst', p.name));
    m.addTo(layer); points.push([p.lat, p.lng]);
  }
  if (fitPending && points.length) { map.fitBounds(points, {padding: [30, 30], maxZoom: 7}); fitPending = false; }
}
function flyTo(name) {
  const p = places(DATA.groups).find(x => x.name === name);
  if (p) map.flyTo([p.lat, p.lng], Math.max(map.getZoom(), 8), {duration: 0.6});
}

// ---- panel
let view = null;
function show(kind, key) {
  view = {kind, key};
  history.replaceState(null, '', `#${kind}=${encodeURIComponent(key)}`);
  render();
}
function home() { view = null; history.replaceState(null, '', '#'); render(); }
// A changed filter shows the filtered list: an open card that no longer matches would contradict the map and the count.
function filtersChanged() { fitPending = true; home(); }
function openFromHash() {
  const m = /^#(group|inst)=(.*)$/.exec(location.hash);
  if (m) show(m[1], decodeURIComponent(m[2]));
}
function groupRow(g) {
  return `<div class="row" data-group="${esc(g.id)}"><span class="t">${esc(g.pi.name)}</span> <span class="role">${esc(roleLabel(g.pi.role_class))}</span>
    ${g.tags.length ? `<div>${tagChips(g.tags.slice(0, 6))}</div>` : ''}${g.topics.length ? `<div class="k">${esc(g.topics.slice(0, 3).join(' · '))}</div>` : ''}</div>`;
}
// Groups that share a homepage are PI groups of one lab: the list draws the lab once, with each group as a row inside.
function labBlock(g, groups) {
  const inLab = groups.filter(x => x.lab && x.lab.homepage === g.lab.homepage && x.institution.name === g.institution.name);
  return `<div class="lab"><span class="m">${esc(T().lab)} · ${link(g.lab.homepage)}</span>${inLab.map(groupRow).join('')}</div>`;
}
function listView(groups) {
  let html = '', current = null;
  const drawn = new Set();
  for (const g of groups) {
    const key = g.lab ? g.institution.name + '|' + g.lab.homepage : '';
    if (key && drawn.has(key)) continue;
    if (g.institution.name !== current) {
      current = g.institution.name;
      const loc = g.institution.location || {};
      html += `<div class="inst" data-inst="${esc(current)}">${esc(current)} <span class="m">${esc(g.institution.country)}${loc.city ? ' · ' + esc(loc.city) : ''}</span></div>`;
    }
    if (key) drawn.add(key);
    html += g.lab ? labBlock(g, groups) : groupRow(g);
  }
  return `<div class="card">${html || `<span class="muted">${T().noMatch}</span>`}</div>`;
}
function membersByRole(g) {
  return ROLE_ORDER.map(role => [role, g.members.filter(m => m.role_class === role)]).filter(([, ms]) => ms.length)
    .map(([role, ms]) => `<h3>${esc(roleLabel(role))} (${ms.length})</h3><p class="names">${ms.map(m => esc(m.name) + (m.link === 'project' ? ` <span class="muted">(${T().project})</span>` : '')).join(', ')}</p>`).join('');
}
function card(g) {
  const t = T(), loc = g.institution.location || {};
  const verified = g.last_verified ? `${esc(g.last_verified)} <span class="muted">(${g.last_verified_from === 'final_pass' ? t.fromPage : t.fromRecord})</span>` : `<span class="muted">${t.never}</span>`;
  const correction = CORRECTION_URL + (CORRECTION_URL.includes('?') ? '&' : '?') + 'group=' + encodeURIComponent(g.id);
  return `<div class="card"><h2>${esc(g.pi.name)} <span class="role">${esc(roleLabel(g.pi.role_class))}</span></h2>
    <div class="sub"><a data-inst="${esc(g.institution.name)}" href="#">${esc(g.institution.name)}</a> · ${esc(g.institution.country)}${loc.city ? ' · ' + esc(loc.city) : ''}${loc.source === 'country centroid' ? ' · ' + t.approx : ''}
      ${g.institution.location ? `<button class="btn" data-fly="${esc(g.institution.name)}">${t.showOnMap}</button>` : ''}</div>
    <dl>${g.homepage ? `<dt>${t.homepage}</dt><dd>${link(g.homepage)}</dd>` : g.pi.homepage ? `<dt>${t.piPage}</dt><dd>${link(g.pi.homepage)}</dd>` : ''}
    ${g.lab ? `<dt>${t.lab}</dt><dd>${g.lab.groups.filter(id => id !== g.id).map(byId).filter(Boolean).map(o => `<a href="#" data-group="${esc(o.id)}">${esc(o.pi.name)}</a>`).join(', ')}</dd>` : ''}
    ${g.homepage && g.pi.homepage && g.pi.homepage !== g.homepage ? `<dt>${t.piPage}</dt><dd>${link(g.pi.homepage)}</dd>` : ''}
    ${FACETS.length ? `<dt>${t.tags}</dt><dd>${tagChips(g.tags) || '<span class="muted">—</span>'}</dd>` : ''}
    <dt>${t.topics}</dt><dd>${g.topics.map(x => `<span class="topic">${esc(x)}</span>`).join('') || '<span class="muted">—</span>'}</dd>
    ${g.active_funding.length ? `<dt>${t.funding}</dt><dd>${g.active_funding.map(f => esc(fundingLabel(f.type)) + (f.date ? ' · ' + esc(f.date) : '')).join('<br>')}</dd>` : ''}
    ${g.open_source.length ? `<dt>${t.openSource}</dt><dd>${g.open_source.slice(0, 8).map(u => link(u)).join('<br>')}</dd>` : ''}
    <dt>${t.sources}</dt><dd>${g.sources.map(c => esc(channelLabel(c))).join(', ') || '—'}</dd>
    <dt>${t.lastVerified}</dt><dd>${verified}</dd></dl>
    <h3>${t.members}</h3>${g.members.length ? membersByRole(g) : `<p class="muted">${t.noMembers}</p>`}
    ${g.coauthors_count ? `<p class="muted">${esc(t.coauthors(g.coauthors_count))}</p>` : ''}
    <details><summary>${t.evidence} (${g.evidence_urls.length})</summary>${g.evidence_urls.slice(0, 60).map(u => link(u)).join('<br>')}</details>
    <div class="actions"><a href="${esc(correction)}" target="_blank" rel="noopener">${t.correction}</a><a href="${esc(ABOUT_URL)}">${t.about}</a></div></div>`;
}
function render() {
  const groups = visible();
  drawMarkers(groups);
  $('#counts').textContent = T().showing(groups.length, DATA.groups.length);
  const crumbs = [`<a data-home>${esc(T().list)}</a>`];
  let html;
  if (view && view.kind === 'group') {
    const g = byId(view.key);
    crumbs.push(`<span>›</span><span>${esc(g ? g.pi.name : view.key)}</span>`);
    html = g ? card(g) : `<div class="card muted">${T().noMatch}</div>`;
  } else if (view && view.kind === 'inst') {
    crumbs.push(`<span>›</span><span>${esc(view.key)}</span>`);
    html = groups.filter(g => g.institution.name === view.key).map(card).join('') || `<div class="card muted">${T().noMatch}</div>`;
  } else {
    html = listView(groups);
  }
  if (view) crumbs.push(`<a data-home>${T().back}</a>`);
  $('#crumbs').innerHTML = crumbs.join(' ');
  $('#panel').innerHTML = html;
  document.querySelector('aside').scrollTop = 0;
}
function about() {
  $('#about').innerHTML = `<h3>${esc(T().about)}</h3>` + T().aboutText(DATA.meta).map(p => `<p>${esc(p)}</p>`).join('');
}

// ---- chrome (labels that change with the language)
function applyLanguage() {
  const t = T();
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  $('#lang').textContent = lang === 'zh' ? 'EN' : '中文';
  $('#title').textContent = t.title(`${DATA.meta.domain || ''} · ${DATA.meta.as_of}`);
  $('#q').placeholder = t.search; $('#reset').textContent = t.reset; $('#about-link').textContent = t.about; $('#about-link').href = ABOUT_URL;
  const country = $('#f-country'), cur = country.value;
  country.innerHTML = `<option value="">${esc(t.allCountries)}</option>` +
    [...new Set(DATA.groups.map(g => g.institution.country))].filter(Boolean).sort().map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
  country.value = cur;
  const used = new Set(DATA.groups.flatMap(g => g.tags));
  $('#facets').innerHTML = FACETS.map(f => `<select id="f-facet-${esc(f.id)}" data-facet="${esc(f.id)}"></select>`).join(' ');
  for (const f of FACETS) {
    const el = document.querySelector(`select[data-facet="${f.id}"]`);
    el.innerHTML = `<option value="">${esc(i18nLabel(f.label, f.id))}: ${esc(t.all)}</option>` +
      f.tags.filter(x => used.has(x.id)).map(x => `<option value="${esc(x.id)}">${esc(i18nLabel(x.label, x.id))}</option>`).join('');
    el.value = filters.tags[f.id] || '';
    el.addEventListener('change', e => { filters.tags[f.id] = e.target.value; filtersChanged(); });
  }
  const bm = $('#basemap'), bmCur = bm.value;
  bm.innerHTML = ['esri', 'osmde', 'osm', 'none'].map(v => `<option value="${v}">${esc(t.basemaps[v])}</option>`).join('');
  bm.value = bmCur || 'esri';
  about();
}

// ---- events
document.addEventListener('click', e => {
  const t = e.target.closest('[data-group],[data-inst],[data-fly],[data-home]');
  if (!t) return;
  if (t.tagName === 'A') e.preventDefault();
  if (t.dataset.group) show('group', t.dataset.group);
  else if (t.dataset.inst) { flyTo(t.dataset.inst); show('inst', t.dataset.inst); }
  else if (t.dataset.fly) { e.stopPropagation(); flyTo(t.dataset.fly); }
  else if ('home' in t.dataset) home();
});
$('#q').addEventListener('input', e => { filters.q = e.target.value.trim().toLowerCase(); filtersChanged(); });
$('#f-country').addEventListener('change', e => { filters.country = e.target.value; filtersChanged(); });
$('#reset').addEventListener('click', () => { filters.q = ''; filters.country = ''; filters.tags = {}; $('#q').value = '';
  document.querySelectorAll('header select').forEach(s => s.value = ''); fitPending = true; home(); });
$('#lang').addEventListener('click', () => { lang = lang === 'zh' ? 'en' : 'zh'; try { localStorage.setItem('group-map.lang', lang); } catch (e) {} applyLanguage(); render(); });
let basemap = 'esri';
try { basemap = localStorage.getItem('group-map.basemap') || basemap; } catch (e) {}
$('#basemap').addEventListener('change', e => { useBasemap(e.target.value); try { localStorage.setItem('group-map.basemap', e.target.value); } catch (err) {} });
window.addEventListener('hashchange', openFromHash);
applyLanguage();
$('#basemap').value = basemap;
useBasemap(basemap);
render();
openFromHash();
</script>
</body>
</html>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('groups')
    parser.add_argument('--out', default='index.html')
    parser.add_argument('--correction-url', default=CORRECTION_URL,
                        help='form a card links to report a correction; the card appends group=<id>')
    parser.add_argument('--about-url', default=ABOUT_URL, help='where the about links point (default: the in-page section)')
    args = parser.parse_args()
    try:
        doc = json.loads(Path(args.groups).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f'cannot read {args.groups}: {exc}')
    if not isinstance(doc, dict) or not isinstance(doc.get('meta'), dict) or not isinstance(doc.get('groups'), list):
        raise SystemExit(f'{args.groups}: expected an object with "meta" and "groups" (written by group_export.py)')
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        page = render_html(doc, args.correction_url, args.about_url)
    except ValueError as exc:
        raise SystemExit(str(exc))
    out.write_text(page, encoding='utf-8')
    print(f"wrote {out}: {len(doc['groups'])} groups", file=sys.stderr)


if __name__ == '__main__':
    main()
