"""Génération du dashboard HTML interactif — Projet ascenseur SOFIA."""
from __future__ import annotations

import json
import sqlite3

from ..config import (
    EXPORTS_DIR, MAJORITE_ART25, SEUIL_PASSERELLE,
    TANTIEMES_TOTAL_COPRO, TANTIEMES_BAT_A, TANTIEMES_ASCENSEUR_TOTAL,
)
from .devis import get_devis_comparison
from .simulation import calculer_repartition
from .votes import calculer_resultats, get_votes_detail
from .strategy import get_full_canvassing_list

OUTPUT_PATH = EXPORTS_DIR / "dashboard_ascenseur.html"


def generate_dashboard_data(conn: sqlite3.Connection) -> dict:
    """Assemble toutes les données en un dict JSON-serializable."""
    comp = get_devis_comparison(conn)
    votes_res = calculer_resultats(conn)
    votes_detail = get_votes_detail(conn)
    canvassing = get_full_canvassing_list(conn)

    # Simulations pour les 3 devis comparables
    simulations = {}
    for d in comp["comparables"]:
        lots = calculer_repartition(conn, d["montant_ttc"])
        simulations[d["fournisseur"]] = {
            "montant": d["montant_ttc"],
            "lots": lots,
        }

    # Frais annexes
    frais = conn.execute(
        "SELECT * FROM frais_annexes ORDER BY obligatoire DESC, categorie"
    ).fetchall()

    # Action plan
    actions = conn.execute("SELECT * FROM action_plan ORDER BY etape").fetchall()

    return {
        "devis": {
            "comparables": comp["comparables"],
            "reference": comp["reference"],
            "recommande": comp["recommande"]["fournisseur"],
        },
        "simulations": simulations,
        "votes": {
            "resultats": votes_res,
            "detail": votes_detail,
        },
        "canvassing": canvassing,
        "frais_annexes": [dict(f) for f in frais],
        "action_plan": [dict(a) for a in actions],
        "constantes": {
            "tantiemes_total": TANTIEMES_TOTAL_COPRO,
            "tantiemes_bat_a": TANTIEMES_BAT_A,
            "majorite_art25": MAJORITE_ART25,
            "seuil_passerelle": SEUIL_PASSERELLE,
            "tantiemes_ascenseur": TANTIEMES_ASCENSEUR_TOTAL,
        },
    }


def generate_html(data: dict) -> str:
    """Génère un fichier HTML auto-contenu avec CSS/JS embarqué."""
    data_json = json.dumps(data, ensure_ascii=False, default=str)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ascenseur Bât A — Copropriété SOFIA</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f6fa; color: #2d3436; font-size: 14px; }}
.header {{ background: linear-gradient(135deg, #2f5496, #4472c4); color: white; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }}
.header h1 {{ font-size: 18px; font-weight: 600; }}
.header .subtitle {{ font-size: 12px; opacity: 0.85; }}
.tabs {{ display: flex; background: #fff; border-bottom: 2px solid #e0e0e0; overflow-x: auto; -webkit-overflow-scrolling: touch; position: sticky; top: 50px; z-index: 99; }}
.tab {{ padding: 12px 20px; cursor: pointer; font-weight: 500; color: #636e72; border-bottom: 3px solid transparent; white-space: nowrap; transition: all 0.2s; }}
.tab:hover {{ color: #2f5496; background: #f0f4ff; }}
.tab.active {{ color: #2f5496; border-bottom-color: #2f5496; background: #f0f4ff; }}
.panel {{ display: none; padding: 20px; max-width: 1200px; margin: 0 auto; }}
.panel.active {{ display: block; }}
.card {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.card h2 {{ font-size: 16px; color: #2f5496; margin-bottom: 12px; }}
.card h3 {{ font-size: 14px; color: #636e72; margin-bottom: 8px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: #4472c4; color: white; padding: 8px 10px; text-align: left; }}
td {{ padding: 6px 10px; border-bottom: 1px solid #eee; vertical-align: middle; line-height: 1.3; }}
tr:nth-child(even) {{ background: #f8f9ff; }}
tr:hover {{ background: #e8edff; }}
.tag {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }}
.tag-pour {{ background: #c6efce; color: #006100; }}
.tag-contre {{ background: #ffc7ce; color: #9c0006; }}
.tag-abstention {{ background: #ffeb9c; color: #9c5700; }}
.tag-absent {{ background: #d9d9d9; color: #333; }}
.tag-inconnu {{ background: #f0f0f0; color: #666; }}
.tag-certain {{ background: #2f5496; color: #fff; }}
.tag-probable {{ background: #4472c4; color: #fff; }}
.tag-possible {{ background: #8faadc; color: #fff; }}
.metric {{ text-align: center; padding: 16px; }}
.metric .value {{ font-size: 28px; font-weight: 700; color: #2f5496; }}
.metric .label {{ font-size: 12px; color: #636e72; margin-top: 4px; }}
.metrics-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 16px; }}
.progress-bar {{ height: 24px; background: #e0e0e0; border-radius: 12px; overflow: hidden; position: relative; }}
.progress-fill {{ height: 100%; border-radius: 12px; transition: width 0.5s; }}
.progress-label {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 12px; font-weight: 600; color: #333; }}
.slider-container {{ margin: 16px 0; }}
.slider-container input[type=range] {{ width: 100%; }}
.btn {{ display: inline-block; padding: 6px 14px; border-radius: 6px; border: 1px solid #ccc; background: #fff; cursor: pointer; font-size: 12px; margin: 2px; transition: all 0.2s; }}
.btn:hover {{ background: #4472c4; color: white; border-color: #4472c4; }}
.btn.active {{ background: #2f5496; color: white; border-color: #2f5496; }}
.highlight-box {{ background: #fff2cc; border-left: 4px solid #ed7d31; padding: 12px 16px; margin: 12px 0; border-radius: 0 8px 8px 0; }}
.reco-box {{ background: #c6efce; border-left: 4px solid #70ad47; padding: 12px 16px; margin: 12px 0; border-radius: 0 8px 8px 0; }}
select.vote-select {{ padding: 2px 6px; border-radius: 4px; font-size: 12px; border: 1px solid #ccc; }}
.timeline {{ position: relative; padding-left: 30px; }}
.timeline-item {{ position: relative; padding-bottom: 20px; border-left: 2px solid #ccc; padding-left: 20px; }}
.timeline-item:last-child {{ border-left: 2px solid transparent; }}
.timeline-dot {{ position: absolute; left: -8px; top: 2px; width: 14px; height: 14px; border-radius: 50%; border: 2px solid #fff; }}
.timeline-dot.a_faire {{ background: #ccc; }}
.timeline-dot.en_cours {{ background: #ed7d31; }}
.timeline-dot.fait {{ background: #70ad47; }}
.timeline-dot.bloque {{ background: #ff6b6b; }}
.checkbox-contact {{ cursor: pointer; width: 18px; height: 18px; }}
.chart-container {{ max-width: 350px; margin: 0 auto; }}
.radar-container {{ max-width: 400px; margin: 0 auto; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
@media (max-width: 768px) {{
    .grid-2 {{ grid-template-columns: 1fr; }}
    .header h1 {{ font-size: 15px; }}
    .tab {{ padding: 10px 14px; font-size: 13px; }}
    .panel {{ padding: 12px; }}
    td, th {{ padding: 4px 6px; font-size: 12px; }}
}}
</style>
</head>
<body>

<div class="header">
    <div>
        <h1>Projet Ascenseur — Bâtiment A</h1>
        <div class="subtitle">Copropriété SOFIA — 5 rue de Sofia, 75018 Paris</div>
    </div>
</div>

<div class="tabs" id="tabs">
    <div class="tab active" data-panel="devis">Devis</div>
    <div class="tab" data-panel="simulation">Simulation</div>
    <div class="tab" data-panel="votes">Votes</div>
    <div class="tab" data-panel="demarchage">Démarchage</div>
    <div class="tab" data-panel="plan">Plan d'action</div>
</div>

<!-- ═══════════════ DEVIS ═══════════════ -->
<div class="panel active" id="panel-devis">
    <div class="card">
        <h2>Comparaison des devis</h2>
        <div style="overflow-x:auto">
            <table id="devis-table"></table>
        </div>
    </div>
    <div class="reco-box" id="reco-box"></div>
    <div class="grid-2">
        <div class="card">
            <h2>Profil radar</h2>
            <div class="radar-container"><canvas id="radar-chart"></canvas></div>
        </div>
        <div class="card">
            <h2>Coût sur 10 ans</h2>
            <div class="chart-container"><canvas id="cost-chart"></canvas></div>
        </div>
    </div>
</div>

<!-- ═══════════════ SIMULATION ═══════════════ -->
<div class="panel" id="panel-simulation">
    <div class="card">
        <h2>Simulation des quote-parts</h2>
        <div class="slider-container">
            <label>Montant TTC : <strong id="montant-label">181 123 €</strong></label>
            <input type="range" id="montant-slider" min="150000" max="200000" step="100" value="181123">
        </div>
        <div style="margin-bottom:12px" id="montant-buttons"></div>
        <div class="highlight-box" id="lot27-box" style="display:none"></div>
        <div style="overflow-x:auto">
            <table id="sim-table"></table>
        </div>
    </div>
    <div class="card">
        <h2>Prises en charge entre copropriétaires</h2>
        <p style="font-size:12px; color:#636e72; margin-bottom:12px">
            Un copropriétaire peut prendre en charge un pourcentage de la quote-part d'un autre lot
            (ex. : pour faciliter l'adhésion d'un voisin réticent).
        </p>
        <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:end; margin-bottom:12px">
            <div>
                <label style="font-size:12px; display:block; margin-bottom:2px">Payeur (qui prend en charge)</label>
                <select id="pec-payeur" style="padding:6px; border-radius:4px; border:1px solid #ccc; min-width:180px"></select>
            </div>
            <div>
                <label style="font-size:12px; display:block; margin-bottom:2px">Bénéficiaire (lot allégé)</label>
                <select id="pec-beneficiaire" style="padding:6px; border-radius:4px; border:1px solid #ccc; min-width:180px"></select>
            </div>
            <div>
                <label style="font-size:12px; display:block; margin-bottom:2px">% pris en charge</label>
                <input type="number" id="pec-pct" min="1" max="100" value="50" style="padding:6px; border-radius:4px; border:1px solid #ccc; width:70px">
            </div>
            <button class="btn" id="pec-add" style="padding:8px 16px; background:#4472c4; color:white; border:none; font-weight:600">Ajouter</button>
        </div>
        <div id="pec-list"></div>
    </div>
</div>

<!-- ═══════════════ VOTES ═══════════════ -->
<div class="panel" id="panel-votes">
    <div class="card" style="margin-bottom:16px">
        <h2>Scénario juridique de vote</h2>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px">
            <button class="btn scenario-btn active" data-scenario="bat_a" style="padding:10px 18px; font-size:13px">Parties communes spéciales (Bât A seul)</button>
            <button class="btn scenario-btn" data-scenario="tous" style="padding:10px 18px; font-size:13px">AG générale (tous bâtiments)</button>
        </div>
        <div id="scenario-desc"></div>
    </div>
    <div class="metrics-row" id="vote-metrics"></div>
    <div class="card">
        <h2>Progression vers la majorité art.25</h2>
        <div class="progress-bar" id="art25-bar">
            <div class="progress-fill" style="background: linear-gradient(90deg, #70ad47, #4472c4);"></div>
            <div class="progress-label"></div>
        </div>
        <div id="art25-seuils" style="margin-top:8px; font-size:12px; color:#636e72"></div>
    </div>
    <div class="card" id="card-par-bat">
        <h2>Par bâtiment</h2>
        <div class="chart-container" style="max-width:500px"><canvas id="vote-bat-chart"></canvas></div>
    </div>
    <div class="card">
        <h2>Détail des votes</h2>
        <div id="vote-filters" style="display:flex; flex-wrap:wrap; gap:10px; align-items:end; margin-bottom:8px; padding:10px; background:#f0f4ff; border-radius:6px; position:sticky; top:96px; z-index:50; box-shadow:0 2px 4px rgba(0,0,0,0.1)">
            <div>
                <label style="font-size:11px; display:block; margin-bottom:2px; font-weight:600; color:#2f5496">Filtrer — Bâtiment</label>
                <select id="vote-filter-bat" style="padding:5px 8px; border-radius:4px; border:1px solid #ccc; font-size:13px">
                    <option value="">Tous</option>
                    <option value="A">Bât A</option>
                    <option value="B">Bât B</option>
                    <option value="C">Bât C</option>
                </select>
            </div>
            <div>
                <label style="font-size:11px; display:block; margin-bottom:2px; font-weight:600; color:#2f5496">Filtrer — Vote</label>
                <select id="vote-filter-vote" style="padding:5px 8px; border-radius:4px; border:1px solid #ccc; font-size:13px">
                    <option value="">Tous</option>
                    <option value="pour">Pour</option>
                    <option value="contre">Contre</option>
                    <option value="abstention">Abstention</option>
                    <option value="absent">Absent</option>
                    <option value="inconnu">Inconnu</option>
                </select>
            </div>
            <div>
                <label style="font-size:11px; display:block; margin-bottom:2px; font-weight:600; color:#2f5496">Filtrer — Confiance</label>
                <select id="vote-filter-confiance" style="padding:5px 8px; border-radius:4px; border:1px solid #ccc; font-size:13px">
                    <option value="">Toutes</option>
                    <option value="certain">Certain</option>
                    <option value="probable">Probable</option>
                    <option value="possible">Possible</option>
                    <option value="inconnu">Inconnu</option>
                </select>
            </div>
            <div style="border-left:2px solid #ccc; padding-left:10px">
                <label style="font-size:11px; display:block; margin-bottom:2px; font-weight:600; color:#ed7d31">Tri principal</label>
                <select id="vote-sort1" style="padding:5px 8px; border-radius:4px; border:1px solid #ccc; font-size:13px">
                    <option value="bat-asc">Bâtiment A→C</option>
                    <option value="bat-desc">Bâtiment C→A</option>
                    <option value="ta-desc">T. ascenseur ↓</option>
                    <option value="ta-asc">T. ascenseur ↑</option>
                    <option value="tant-desc">Tantièmes ↓</option>
                    <option value="tant-asc">Tantièmes ↑</option>
                    <option value="etage-desc">Étage ↓</option>
                    <option value="etage-asc">Étage ↑</option>
                    <option value="lot-asc">N° lot ↑</option>
                    <option value="vote">Vote</option>
                </select>
            </div>
            <div>
                <label style="font-size:11px; display:block; margin-bottom:2px; font-weight:600; color:#ed7d31">Tri secondaire</label>
                <select id="vote-sort2" style="padding:5px 8px; border-radius:4px; border:1px solid #ccc; font-size:13px">
                    <option value="none">—</option>
                    <option value="ta-desc" selected>T. ascenseur ↓</option>
                    <option value="ta-asc">T. ascenseur ↑</option>
                    <option value="tant-desc">Tantièmes ↓</option>
                    <option value="tant-asc">Tantièmes ↑</option>
                    <option value="etage-desc">Étage ↓</option>
                    <option value="etage-asc">Étage ↑</option>
                    <option value="lot-asc">N° lot ↑</option>
                    <option value="vote">Vote</option>
                </select>
            </div>
            <div style="border-left:2px solid #ccc; padding-left:10px">
                <button id="vote-reset" class="btn" style="padding:8px 14px; background:#ff6b6b; color:white; border:none; font-weight:600; font-size:12px; margin-top:14px; cursor:pointer">Réinitialiser</button>
            </div>
        </div>
        <div id="vote-filter-count" style="font-size:12px; color:#636e72; margin-bottom:8px"></div>
        <div style="overflow-x:auto">
            <table id="votes-table"></table>
        </div>
    </div>
</div>

<!-- ═══════════════ DÉMARCHAGE ═══════════════ -->
<div class="panel" id="panel-demarchage">
    <div class="card">
        <h2>Liste de démarchage priorisée</h2>
        <div style="overflow-x:auto">
            <table id="canvassing-table"></table>
        </div>
    </div>
</div>

<!-- ═══════════════ PLAN D'ACTION ═══════════════ -->
<div class="panel" id="panel-plan">
    <div class="card">
        <h2>Timeline du projet</h2>
        <div class="timeline" id="timeline"></div>
    </div>
</div>

<script>
const DATA = {data_json};
const C = DATA.constantes;

// ═══════════════ TABS ═══════════════
document.querySelectorAll('.tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('panel-' + tab.dataset.panel).classList.add('active');
    }});
}});

// ═══════════════ UTILS ═══════════════
function fmtEur(n) {{ return n.toLocaleString('fr-FR', {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) + ' €'; }}
function fmtProp(s) {{ if (!s) return '-'; return s.split(',').map(n => n.trim()).join(', '); }}

// ═══════════════ DEVIS ═══════════════
function renderDevis() {{
    const comparables = DATA.devis.comparables;
    const ref = DATA.devis.reference;
    const all = [...comparables, ...ref];
    let html = '<tr><th>Critère</th>';
    all.forEach(d => html += `<th>${{d.fournisseur}}${{d.recommande ? ' ★' : ''}}</th>`);
    html += '</tr>';

    const rows = [
        ['Montant TTC', d => d.montant_ttc ? d.montant_ttc.toLocaleString('fr-FR') + ' €' : '-'],
        ['Capacité', d => d.capacite_kg ? `${{d.capacite_kg}} kg / ${{d.capacite_pers || '?'}} pers` : '-'],
        ['Passage', d => d.passage_mm ? d.passage_mm + ' mm' : '-'],
        ['Cuvette', d => d.cuvette_mm ? d.cuvette_mm + ' mm' : '-'],
        ['PMR EN 81-70', d => d.pmr_en81_70 ? '<span class="tag tag-pour">Oui</span>' : '<span class="tag tag-contre">Non</span>'],
        ['Niveaux', d => d.niveaux],
        ['Maintenance HT/an', d => d.maintenance_ht ? d.maintenance_ht.toLocaleString('fr-FR') + ' €' : '-'],
        ['Durée travaux', d => d.duree_travaux || '-'],
    ];

    rows.forEach(([label, fn]) => {{
        html += `<tr><td><strong>${{label}}</strong></td>`;
        all.forEach(d => html += `<td>${{fn(d)}}</td>`);
        html += '</tr>';
    }});

    document.getElementById('devis-table').innerHTML = html;
    document.getElementById('reco-box').innerHTML =
        `<strong>Recommandation :</strong> ${{DATA.devis.recommande}} — Seul devis conforme PMR (EN 81-70), passage 700mm permettant l'accès fauteuil roulant, cuvette réduite 350mm.`;

    // Radar chart
    const labels = ['Prix', 'Capacité', 'Accessibilité', 'Rapidité', 'Maintenance', 'Niveaux'];
    const colors = ['#4472c4', '#ed7d31', '#70ad47', '#9b59b6'];
    const bgColors = ['rgba(68,114,196,0.1)', 'rgba(237,125,49,0.1)', 'rgba(112,173,71,0.1)', 'rgba(155,89,182,0.1)'];
    const datasets = comparables.map((d, i) => ({{
        label: d.fournisseur,
        data: [d.score_prix, d.score_capacite, d.score_accessibilite, d.score_rapidite, d.score_maintenance, d.score_niveaux || 3],
        borderColor: colors[i % colors.length],
        backgroundColor: bgColors[i % bgColors.length],
        pointRadius: 4,
    }}));
    new Chart(document.getElementById('radar-chart'), {{
        type: 'radar',
        data: {{ labels, datasets }},
        options: {{ scales: {{ r: {{ min: 0, max: 5, ticks: {{ stepSize: 1 }} }} }}, plugins: {{ legend: {{ position: 'bottom' }} }} }}
    }});

    // Cost 10y chart
    const cost10y = comparables.map(d => d.montant_ttc + (d.maintenance_ht || 0) * 1.2 * 10);
    new Chart(document.getElementById('cost-chart'), {{
        type: 'bar',
        data: {{
            labels: comparables.map(d => d.fournisseur),
            datasets: [{{ label: 'Coût 10 ans (€)', data: cost10y, backgroundColor: ['#4472c4', '#ed7d31', '#70ad47'] }}]
        }},
        options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, ticks: {{ callback: v => (v/1000).toFixed(0) + 'k €' }} }} }} }}
    }});
}}
renderDevis();

// ═══════════════ SIMULATION ═══════════════
// Générer les boutons de simulation dynamiquement
const simKeys = Object.keys(DATA.simulations);
const btnContainer = document.getElementById('montant-buttons');
simKeys.forEach(key => {{
    const sim = DATA.simulations[key];
    const btn = document.createElement('span');
    btn.className = 'btn';
    btn.dataset.montant = sim.montant;
    btn.textContent = key + ' ' + sim.montant.toLocaleString('fr-FR') + ' €';
    btnContainer.appendChild(btn);
}});

const baseKey = simKeys[0];
const baseLots = DATA.simulations[baseKey].lots;
const payeurs = baseLots.filter(l => l.tantieme_ascenseur > 0);
const totalTA = baseLots.reduce((s, l) => s + l.tantieme_ascenseur, 0);

// Prises en charge : [{{ payeur: lot_numero, beneficiaire: lot_numero, pct: 0-100 }}]
let prisesEnCharge = [];

// Populate PEC selects
function populatePecSelects() {{
    const opts = payeurs.map(l =>
        `<option value="${{l.lot_numero}}">#${{l.lot_numero}} — ${{(l.proprietaire || '?').split(',')[0]}} (ét.${{l.etage}})</option>`
    ).join('');
    document.getElementById('pec-payeur').innerHTML = opts;
    document.getElementById('pec-beneficiaire').innerHTML = opts;
    // Default: payeur = lot 27, bénéficiaire = first lot
    const selPayeur = document.getElementById('pec-payeur');
    const opt27 = selPayeur.querySelector('option[value="27"]');
    if (opt27) opt27.selected = true;
}}
populatePecSelects();

document.getElementById('pec-add').addEventListener('click', () => {{
    const payeur = +document.getElementById('pec-payeur').value;
    const benef = +document.getElementById('pec-beneficiaire').value;
    const pct = Math.min(100, Math.max(1, +document.getElementById('pec-pct').value || 50));
    if (payeur === benef) return;
    // Check total PEC on this beneficiary doesn't exceed 100%
    const existPct = prisesEnCharge.filter(p => p.beneficiaire === benef).reduce((s, p) => s + p.pct, 0);
    if (existPct + pct > 100) return;
    prisesEnCharge.push({{ payeur, beneficiaire: benef, pct }});
    renderSimulation(+document.getElementById('montant-slider').value);
}});

function removePec(idx) {{
    prisesEnCharge.splice(idx, 1);
    renderSimulation(+document.getElementById('montant-slider').value);
}}

function renderSimulation(montant) {{
    // Base quote-parts
    const qpBase = {{}};
    payeurs.forEach(l => {{
        qpBase[l.lot_numero] = totalTA > 0 ? montant * l.tantieme_ascenseur / totalTA : 0;
    }});

    // Apply prises en charge : transferts
    const transferts = {{}};  // lot_numero -> adjustment (+/-)
    payeurs.forEach(l => {{ transferts[l.lot_numero] = 0; }});

    prisesEnCharge.forEach(p => {{
        const montantTransfert = qpBase[p.beneficiaire] * p.pct / 100;
        transferts[p.beneficiaire] -= montantTransfert;  // bénéficiaire paie moins
        transferts[p.payeur] += montantTransfert;         // payeur paie plus
    }});

    // Render PEC list
    let pecHtml = '';
    if (prisesEnCharge.length > 0) {{
        pecHtml = '<table style="font-size:13px; margin-bottom:8px"><tr><th>Payeur</th><th>Bénéficiaire</th><th>%</th><th>Montant transféré</th><th></th></tr>';
        prisesEnCharge.forEach((p, i) => {{
            const mt = qpBase[p.beneficiaire] * p.pct / 100;
            const payeurName = payeurs.find(l => l.lot_numero === p.payeur)?.proprietaire?.split(',')[0] || '?';
            const benefName = payeurs.find(l => l.lot_numero === p.beneficiaire)?.proprietaire?.split(',')[0] || '?';
            pecHtml += `<tr>
                <td>#${{p.payeur}} ${{payeurName}}</td>
                <td>#${{p.beneficiaire}} ${{benefName}}</td>
                <td>${{p.pct}}%</td>
                <td><strong>${{fmtEur(mt)}}</strong></td>
                <td><span onclick="removePec(${{i}})" style="cursor:pointer; color:#ff6b6b; font-weight:bold" title="Supprimer">✕</span></td>
            </tr>`;
        }});
        pecHtml += '</table>';
    }}
    document.getElementById('pec-list').innerHTML = pecHtml;

    // Render main table
    const hasPec = prisesEnCharge.length > 0;
    let html = '<tr><th>Lot</th><th>Étage</th><th>Localisation</th><th>Propriétaire</th><th>Coef.</th><th>Tant. Asc.</th><th>Quote-part</th>';
    if (hasPec) html += '<th>Coût ajusté</th>';
    html += '</tr>';

    let totalQP = 0;
    let lot27QP = 0;
    let lot27Adj = 0;
    let currentEtage = null;

    baseLots.forEach(l => {{
        const isPayer = l.tantieme_ascenseur > 0;
        const qp = qpBase[l.lot_numero] || 0;
        const adj = isPayer ? qp + (transferts[l.lot_numero] || 0) : 0;
        totalQP += qp;
        if (l.lot_numero === 27) {{ lot27QP = qp; lot27Adj = adj; }}

        if (l.etage !== currentEtage) {{
            if (currentEtage !== null) html += `<tr><td colspan="${{hasPec ? 8 : 7}}" style="height:4px; background:#e0e0e0"></td></tr>`;
            currentEtage = l.etage;
        }}

        const estMark = l.estime ? ' *' : '';
        const delta = isPayer ? (transferts[l.lot_numero] || 0) : 0;
        let adjCell = '';
        if (hasPec) {{
            if (isPayer && Math.abs(delta) > 0.01) {{
                const color = delta > 0 ? '#c0392b' : '#27ae60';
                const sign = delta > 0 ? '+' : '';
                adjCell = `<td style="color:${{color}}; font-weight:bold">${{fmtEur(adj)}} <span style="font-size:11px">(${{sign}}${{delta.toFixed(0)}})</span></td>`;
            }} else {{
                adjCell = isPayer ? `<td>${{fmtEur(adj)}}</td>` : '<td>-</td>';
            }}
        }}

        const rowStyle = !isPayer ? ' style="color:#999"' : '';
        html += `<tr${{rowStyle}}>
            <td>#${{l.lot_numero}}</td><td>${{l.etage}}</td><td>${{l.localisation}}</td>
            <td>${{fmtProp(l.proprietaire)}}</td><td>${{l.coef_ascenseur}}</td>
            <td>${{l.tantieme_ascenseur.toFixed(1)}}${{estMark}}</td>
            <td>${{isPayer ? '<strong>' + fmtEur(qp) + '</strong>' : '-'}}</td>
            ${{adjCell}}
        </tr>`;
    }});

    html += `<tr style="background:#fff2cc; font-weight:bold"><td colspan="6" style="text-align:right">TOTAL</td><td>${{fmtEur(totalQP)}}</td>`;
    if (hasPec) html += `<td>${{fmtEur(totalQP)}}</td>`;
    html += '</tr>';

    document.getElementById('sim-table').innerHTML = html;
    document.getElementById('montant-label').textContent = montant.toLocaleString('fr-FR') + ' €';

    let lot27Html = `<strong>Lot #27 (CLAVÉ) :</strong> ${{fmtEur(lot27QP)}}`;
    if (hasPec && Math.abs(lot27Adj - lot27QP) > 0.01) {{
        lot27Html += ` → <strong style="color:${{lot27Adj > lot27QP ? '#c0392b' : '#27ae60'}}">${{fmtEur(lot27Adj)}}</strong>`;
    }}
    lot27Html += ` pour un montant de ${{fmtEur(montant)}}`;
    document.getElementById('lot27-box').innerHTML = lot27Html;
}}

document.getElementById('montant-slider').addEventListener('input', e => renderSimulation(+e.target.value));
document.querySelectorAll('[data-montant]').forEach(btn => {{
    btn.addEventListener('click', () => {{
        const val = +btn.dataset.montant;
        document.getElementById('montant-slider').value = val;
        renderSimulation(val);
        document.querySelectorAll('[data-montant]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }});
}});
renderSimulation(DATA.simulations[simKeys[0]].montant);

// ═══════════════ VOTES ═══════════════
let votesState = JSON.parse(JSON.stringify(DATA.votes.detail));
let currentScenario = 'bat_a';

function getScenarioParams() {{
    if (currentScenario === 'bat_a') {{
        const total = C.tantiemes_bat_a;
        return {{
            total,
            majorite: Math.floor(total / 2) + 1,
            passerelle: Math.ceil(total / 3),
            filterBat: 'A',
            label: 'Bât A seul',
        }};
    }} else {{
        return {{
            total: C.tantiemes_total,
            majorite: C.majorite_art25,
            passerelle: C.seuil_passerelle,
            filterBat: null,
            label: 'Tous bâtiments',
        }};
    }}
}}

function renderScenarioDesc() {{
    const el = document.getElementById('scenario-desc');
    if (currentScenario === 'bat_a') {{
        el.innerHTML = `<div class="highlight-box"><strong>Scénario 1 — Parties communes spéciales par bâtiment</strong><br>
            Le règlement prévoit des parties communes spéciales pour chaque bâtiment.
            Seuls les copropriétaires du <strong>bâtiment A</strong> votent, sur la base de leurs tantièmes propres
            (${{C.tantiemes_bat_a.toLocaleString('fr-FR')}} tantièmes). Les copropriétaires de B et C ne participent pas.</div>`;
    }} else {{
        el.innerHTML = `<div class="highlight-box" style="background:#fce4ec; border-left-color:#c0392b"><strong>Scénario 2 — AG générale (pas de parties communes spéciales)</strong><br>
            Le règlement ne prévoit ni parties communes spéciales ni syndicat secondaire.
            <strong>Tous les copropriétaires (A, B et C)</strong> doivent voter en AG
            (${{C.tantiemes_total.toLocaleString('fr-FR')}} tantièmes).
            <em>Attention : les copropriétaires de B et C peuvent bloquer un projet qui ne les concerne pas.</em></div>`;
    }}
}}

function recalcVotes() {{
    const S = getScenarioParams();
    const eligible = S.filterBat
        ? votesState.filter(v => v.batiment === S.filterBat)
        : votesState;

    let tPour = 0, tContre = 0, tAbst = 0, tAbsent = 0, tInconnu = 0;
    eligible.forEach(v => {{
        const t = v.tantiemes || 0;
        if (v.vote === 'pour') {{ tPour += t; }}
        else if (v.vote === 'contre') {{ tContre += t; }}
        else if (v.vote === 'abstention') {{ tAbst += t; }}
        else if (v.vote === 'absent') {{ tAbsent += t; }}
        else {{ tInconnu += t; }}
    }});

    const art25 = tPour >= S.majorite;
    const passerelle = tPour >= S.passerelle && !art25;
    const manquants = Math.max(0, S.majorite - tPour);

    // Metrics
    document.getElementById('vote-metrics').innerHTML = `
        <div class="card metric"><div class="value" style="color:#70ad47">${{tPour}}</div><div class="label">Tantièmes POUR</div></div>
        <div class="card metric"><div class="value" style="color:#ff6b6b">${{tContre}}</div><div class="label">Tantièmes CONTRE</div></div>
        <div class="card metric"><div class="value">${{tInconnu}}</div><div class="label">Tantièmes INCONNUS</div></div>
        <div class="card metric"><div class="value" style="color:${{art25 ? '#70ad47' : passerelle ? '#ed7d31' : '#ff6b6b'}}">${{art25 ? 'ART.25 OK' : passerelle ? 'PASSERELLE' : 'INSUFFISANT'}}</div><div class="label">${{manquants > 0 ? 'Manque ' + manquants : 'Majorité atteinte'}}</div></div>
    `;

    // Progress bar
    const pct = Math.min(100, (tPour / S.majorite) * 100);
    const bar = document.getElementById('art25-bar');
    bar.querySelector('.progress-fill').style.width = pct + '%';
    bar.querySelector('.progress-label').textContent = `${{tPour}} / ${{S.majorite}} (${{pct.toFixed(0)}}%)`;

    // Dynamic thresholds display
    document.getElementById('art25-seuils').innerHTML =
        `<span>Seuil passerelle art.24 : <strong>${{S.passerelle}}</strong></span> | ` +
        `<span>Majorité art.25 : <strong>${{S.majorite}}</strong></span> | ` +
        `<span>Total ${{S.filterBat ? 'Bât ' + S.filterBat : 'copro'}} : <strong>${{S.total}}</strong></span>`;

    // Scenarios
    return {{ tPour, tContre, tAbst, tAbsent, tInconnu, eligible }};
}}

function renderVotes() {{
    const stats = recalcVotes();
    const S = getScenarioParams();

    // Chart by building — hide if bat_a only
    const cardBat = document.getElementById('card-par-bat');
    if (S.filterBat) {{
        cardBat.style.display = 'none';
    }} else {{
        cardBat.style.display = '';
        const batData = {{}};
        votesState.forEach(v => {{
            if (!batData[v.batiment]) batData[v.batiment] = {{ pour: 0, contre: 0, autre: 0 }};
            if (v.vote === 'pour') batData[v.batiment].pour += (v.tantiemes || 0);
            else if (v.vote === 'contre') batData[v.batiment].contre += (v.tantiemes || 0);
            else batData[v.batiment].autre += (v.tantiemes || 0);
        }});
        const chartEl = document.getElementById('vote-bat-chart');
        if (window._voteBatChart) window._voteBatChart.destroy();
        const bats = Object.keys(batData).sort();
        window._voteBatChart = new Chart(chartEl, {{
            type: 'bar',
            data: {{
                labels: bats.map(b => 'Bât ' + b),
                datasets: [
                    {{ label: 'Pour', data: bats.map(b => batData[b].pour), backgroundColor: '#70ad47' }},
                    {{ label: 'Contre', data: bats.map(b => batData[b].contre), backgroundColor: '#ff6b6b' }},
                    {{ label: 'Autre', data: bats.map(b => batData[b].autre), backgroundColor: '#d9d9d9' }},
                ]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }} }}
        }});
    }}

    // Apply filters — start from eligible lots only
    const filterBat = document.getElementById('vote-filter-bat').value;
    const filterVote = document.getElementById('vote-filter-vote').value;
    const filterConfiance = document.getElementById('vote-filter-confiance').value;
    const sort1 = document.getElementById('vote-sort1').value;
    const sort2 = document.getElementById('vote-sort2').value;

    // Build indexed list for stable reference back to votesState
    let filtered = votesState.map((v, i) => ({{ ...v, _idx: i }}));
    // Scenario filter first
    if (S.filterBat) filtered = filtered.filter(v => v.batiment === S.filterBat);
    // User filters
    if (filterBat) filtered = filtered.filter(v => v.batiment === filterBat);
    if (filterVote) filtered = filtered.filter(v => v.vote === filterVote);
    if (filterConfiance) filtered = filtered.filter(v => v.confiance === filterConfiance);

    // Sort comparator builder
    const voteOrder = {{ pour: 0, contre: 1, abstention: 2, absent: 3, inconnu: 4 }};
    function cmpFor(key) {{
        if (key === 'bat-asc') return (a, b) => (a.batiment || '').localeCompare(b.batiment || '');
        if (key === 'bat-desc') return (a, b) => (b.batiment || '').localeCompare(a.batiment || '');
        if (key === 'ta-desc') return (a, b) => (b.tantieme_ascenseur || 0) - (a.tantieme_ascenseur || 0);
        if (key === 'ta-asc') return (a, b) => (a.tantieme_ascenseur || 0) - (b.tantieme_ascenseur || 0);
        if (key === 'tant-desc') return (a, b) => (b.tantiemes || 0) - (a.tantiemes || 0);
        if (key === 'tant-asc') return (a, b) => (a.tantiemes || 0) - (b.tantiemes || 0);
        if (key === 'etage-desc') return (a, b) => (b.etage || 0) - (a.etage || 0);
        if (key === 'etage-asc') return (a, b) => (a.etage || 0) - (b.etage || 0);
        if (key === 'lot-asc') return (a, b) => (a.numero || 0) - (b.numero || 0);
        if (key === 'vote') return (a, b) => (voteOrder[a.vote] ?? 9) - (voteOrder[b.vote] ?? 9);
        return () => 0;
    }}
    const cmp1 = cmpFor(sort1);
    const cmp2 = sort2 !== 'none' ? cmpFor(sort2) : () => 0;
    filtered.sort((a, b) => cmp1(a, b) || cmp2(a, b));

    // Summary
    const totalEligible = S.filterBat
        ? votesState.filter(v => v.batiment === S.filterBat).length
        : votesState.length;
    const filteredTantiemes = filtered.reduce((s, v) => s + (v.tantiemes || 0), 0);
    document.getElementById('vote-filter-count').textContent =
        `${{filtered.length}} lots affichés / ${{totalEligible}} — ${{filteredTantiemes}} tantièmes`;

    // Table — compute quote-part from default simulation (CEPA)
    const simMontant = DATA.simulations[Object.keys(DATA.simulations)[0]].montant;
    const simLots = DATA.simulations[Object.keys(DATA.simulations)[0]].lots;
    const qpMap = {{}};
    simLots.forEach(sl => {{ qpMap[sl.lot_numero] = sl; }});

    let html = '<tr><th>Lot</th><th>Bât</th><th>Étage</th><th>Propriétaire</th><th>Tant.</th><th>Tant. Asc.</th><th>Quote-part</th><th>Vote</th><th>Confiance</th></tr>';
    filtered.forEach(v => {{
        const i = v._idx;
        const ta = v.tantieme_ascenseur || 0;
        const sl = qpMap[v.numero];
        const qp = sl ? simMontant * sl.tantieme_ascenseur / totalTA : 0;
        html += `<tr>
            <td>#${{v.numero}}</td><td>${{v.batiment}}</td><td>${{v.etage}}</td>
            <td>${{fmtProp(v.proprietaire)}}</td><td>${{v.tantiemes || 0}}</td>
            <td>${{ta > 0 ? ta.toFixed(1) : '-'}}</td>
            <td>${{ta > 0 ? fmtEur(qp) : '-'}}</td>
            <td><select class="vote-select" data-idx="${{i}}" data-field="vote">
                ${{['pour','contre','abstention','absent','inconnu'].map(o =>
                    `<option value="${{o}}" ${{v.vote===o?'selected':''}}>${{o}}</option>`
                ).join('')}}
            </select></td>
            <td><select class="confiance-select" data-idx="${{i}}" style="padding:2px 4px; border-radius:4px; font-size:12px; border:1px solid #ccc">
                ${{['certain','probable','possible','inconnu'].map(o =>
                    `<option value="${{o}}" ${{v.confiance===o?'selected':''}}>${{o}}</option>`
                ).join('')}}
            </select></td>
        </tr>`;
    }});
    document.getElementById('votes-table').innerHTML = html;

    // Event handlers for vote changes
    document.querySelectorAll('.vote-select').forEach(sel => {{
        sel.addEventListener('change', async e => {{
            const idx = +e.target.dataset.idx;
            const lot = votesState[idx];
            lot.vote = e.target.value;
            renderVotes();
            await fetch(`/api/votes/${{lot.lot_id}}`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ vote: lot.vote, confiance: lot.confiance }})
            }}).catch(err => console.error('Erreur sauvegarde:', err));
        }});
    }});
    // Event handlers for confiance changes
    document.querySelectorAll('.confiance-select').forEach(sel => {{
        sel.addEventListener('change', async e => {{
            const idx = +e.target.dataset.idx;
            const lot = votesState[idx];
            lot.confiance = e.target.value;
            renderVotes();
            await fetch(`/api/votes/${{lot.lot_id}}`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ vote: lot.vote, confiance: lot.confiance }})
            }}).catch(err => console.error('Erreur sauvegarde:', err));
        }});
    }});
}}

// Scenario buttons
document.querySelectorAll('.scenario-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('.scenario-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentScenario = btn.dataset.scenario;
        renderScenarioDesc();
        renderVotes();
    }});
}});
renderScenarioDesc();

// Filter/sort event handlers
['vote-filter-bat', 'vote-filter-vote', 'vote-filter-confiance', 'vote-sort1', 'vote-sort2'].forEach(id => {{
    document.getElementById(id).addEventListener('change', () => renderVotes());
}});
// Reset button
document.getElementById('vote-reset').addEventListener('click', async () => {{
    await fetch('/api/votes/reset', {{ method: 'POST' }}).catch(err => console.error('Erreur reset:', err));
    votesState = JSON.parse(JSON.stringify(DATA.votes.detail));
    document.getElementById('vote-filter-bat').value = '';
    document.getElementById('vote-filter-vote').value = '';
    document.getElementById('vote-filter-confiance').value = '';
    document.getElementById('vote-sort1').value = 'bat-asc';
    document.getElementById('vote-sort2').value = 'ta-desc';
    renderVotes();
}});
renderVotes();

// ═══════════════ DÉMARCHAGE ═══════════════
function formatPhones(raw) {{
    if (!raw) return '-';
    return raw.split(/[,\\n]+/)
        .map(s => s.replace(/[\u200e\u200f\u202a-\u202e]/g, '').trim())
        .filter(s => s && s !== 'na')
        .map(s => {{
            const digits = s.replace(/\D/g, '');
            if (digits.length === 10) return digits.replace(/(\d{{2}})(?=\d)/g, '$1.').slice(0, 14);
            if (digits.length === 11 && digits.startsWith('33')) return '0' + digits.slice(2).replace(/(\d{{2}})(?=\d)/g, '$1.').slice(0, 13);
            if (digits.length === 12 && digits.startsWith('33')) return '0' + digits.slice(2).replace(/(\d{{2}})(?=\d)/g, '$1.').slice(0, 14);
            return s;
        }})
        .join('<br>');
}}

function renderCanvassing() {{
    let html = '<tr><th>Priorité</th><th>Lot</th><th>Bât</th><th>Étage</th><th>Propriétaire</th><th>Téléphone</th><th>Tant.</th><th>Vote actuel</th><th>Argument</th><th>Contacté</th></tr>';
    DATA.canvassing.forEach((c, i) => {{
        html += `<tr>
            <td>${{c.priorite_demarchage}}</td>
            <td>#${{c.numero}}</td><td>${{c.batiment}}</td><td>${{c.etage}}</td>
            <td>${{fmtProp(c.proprietaire)}}</td>
            <td>${{formatPhones(c.telephone)}}</td>
            <td>${{c.tantiemes || 0}}</td>
            <td><span class="tag tag-${{c.vote}}">${{c.vote}}</span></td>
            <td style="max-width:250px; font-size:11px">${{c.argument_demarchage}}</td>
            <td><input type="checkbox" class="checkbox-contact" ${{c.contact_fait ? 'checked' : ''}} data-idx="${{i}}"></td>
        </tr>`;
    }});
    document.getElementById('canvassing-table').innerHTML = html;
}}
renderCanvassing();

// ═══════════════ PLAN D'ACTION ═══════════════
function renderPlan() {{
    let html = '';
    DATA.action_plan.forEach(a => {{
        html += `<div class="timeline-item">
            <div class="timeline-dot ${{a.statut}}"></div>
            <div style="margin-bottom:4px">
                <strong>Étape ${{a.etape}}</strong> — ${{a.titre}}
                <span class="tag tag-${{a.statut === 'fait' ? 'pour' : a.statut === 'en_cours' ? 'abstention' : a.statut === 'bloque' ? 'contre' : 'inconnu'}}">${{a.statut.replace('_', ' ')}}</span>
            </div>
            <div style="font-size:12px; color:#636e72; margin-bottom:4px">${{a.description || ''}}</div>
            <div style="font-size:11px; color:#999">Cible : ${{a.date_cible || '?'}} | Responsable : ${{a.responsable || '?'}}</div>
        </div>`;
    }});
    document.getElementById('timeline').innerHTML = html;
}}
renderPlan();
</script>
</body>
</html>"""


def generate_dashboard(conn: sqlite3.Connection) -> str:
    """Génère le dashboard et retourne le chemin du fichier."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    data = generate_dashboard_data(conn)
    html = generate_html(data)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    return str(OUTPUT_PATH)
