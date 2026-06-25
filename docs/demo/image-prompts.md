# Demo image-generation prompts

Ready-to-paste generative-AI prompts for **every entity across all six
SimpleVTT demo campaigns** (`app/demo_seed.py` + `app/demo_campaigns.py`).
Pick a demo with the tabs below — each tab opens with a **progress
checklist** showing which tokens and maps still need art, the exact path to
drop each file at, and a copy-paste prompt grounded in that character's
race / class / subclass / weapons / personality.

The flagship **Sundered Vault** demo already ships its tokens; the five
leveled demos (L3 / L5 / L9 / L13 / L18) currently render every token as a
plain coloured ring (`image_url=None`) and are waiting on art.

> **Thumbnails appear automatically.** Each checklist row and each prompt
> derives its thumbnail from the path shown for that entity (e.g.
> `app/static/demo/tokens/l3-thorin.jpg` → `/static/demo/tokens/l3-thorin.jpg`).
> Save your generated art at exactly that path and rebuild the container — the
> thumbnail shows up next to the prompt and in the row on the next load, no
> edits to this page needed. (The archived Sundered Vault's shipped tokens
> already preview this way.)

## Overall progress — 10 / 58 images

| Demo | Map | Tokens | Done |
|---|---|---|---|
| Level 3 : The Goblin Warrens | ⬜ | ⬜ 0 / 9 | **0 / 10** |
| Level 5 : The Tide-Wracked Catacombs | ⬜ | ⬜ 0 / 9 | **0 / 10** |
| Level 9 : Storm Over Saltmarsh | ⬜ | ⬜ 0 / 9 | **0 / 10** |
| Level 13 : The Shadowfell Spire | ⬜ | ⬜ 0 / 8 | **0 / 9** |
| Level 18 : The Dragon's Apotheosis | ⬜ | ⬜ 0 / 8 | **0 / 9** |
| ARCHIVE : The Sundered Vault *(flagship)* | 🟡 placeholder | ✅ 9 / 9 shipped | **10 / 10** |

<style>
/* Client-side tab UI for the demo image-prompt sets. The page is plain
   markdown; the script below partitions the rendered sections (delimited by
   HTML-comment TAB markers) into selectable panels. With JS off it degrades
   to the full document as one long scroll. */
.demo-tabbar{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 4px;
  position:sticky;top:0;z-index:5;background:var(--bg);
  padding:10px 0;border-bottom:1px solid var(--border);}
.demo-tab{padding:8px 16px;border:1px solid var(--border);
  background:var(--bg-2);color:var(--fg);border-radius:8px;cursor:pointer;
  font-size:13px;font-weight:600;line-height:1.2;white-space:nowrap;}
.demo-tab:hover{border-color:var(--accent);}
.demo-tab.active{background:var(--accent);color:var(--bg);border-color:var(--accent);}
.demo-panel{animation:demofade .15s ease;}
.demo-panel h3,.demo-panel h4{clear:both;}
@keyframes demofade{from{opacity:0}to{opacity:1}}
/* Auto-thumbnails: derived from each checklist row's path. Hidden until the
   file exists at that path (img.onerror), so they appear automatically once
   art is dropped in. Small inline thumb in the table, larger preview by the prompt. */
.demo-thumb{width:34px;height:34px;object-fit:cover;border-radius:6px;
  border:1px solid var(--border);vertical-align:middle;margin-right:8px;}
.demo-thumb-side{float:right;width:104px;height:104px;object-fit:cover;
  border-radius:10px;border:1px solid var(--border);margin:0 0 8px 14px;
  box-shadow:0 1px 4px rgba(0,0,0,.25);}
</style>

<div class="demo-tabbar" id="demo-tabbar" role="tablist" aria-label="Demo selector"></div>
<div id="demo-panels"></div>

<script>
(function(){
  function init(){
    var article=document.querySelector('article.wiki-md');
    var bar=document.getElementById('demo-tabbar');
    var mount=document.getElementById('demo-panels');
    if(!article||!bar||!mount) return;
    var nodes=Array.prototype.slice.call(article.childNodes);
    var tabs=[],current=null,ended=false;
    nodes.forEach(function(n){
      if(ended) return;
      if(n.nodeType===8){ // HTML comment marker
        var v=n.nodeValue||'';
        var m=v.match(/^\s*TAB:(.+?)\s*$/);
        if(m){ current={title:m[1],nodes:[]}; tabs.push(current); return; }
        if(/^\s*ENDTABS\s*$/.test(v)){ ended=true; current=null; return; }
      }
      if(current){ current.nodes.push(n); }
    });
    if(!tabs.length) return;
    // Derive a web path ("app/static/…" → "/static/…") from a checklist cell.
    function webPath(s){ var t=(s||'').trim(); var i=t.indexOf('static/'); return i<0?null:'/'+t.slice(i); }
    // Normalize a label to letters/digits for fuzzy heading↔row matching.
    function normName(s){ return (s||'').replace(/\([^)]*\)/g,'').replace(/[^A-Za-z0-9' -]/g,'').replace(/\s+/g,' ').trim().toLowerCase(); }
    // Thumbnail that hides itself if the file 404s — so it only shows once art exists.
    function thumb(src,cls,alt){ var im=document.createElement('img'); im.className=cls; im.src=src; im.loading='lazy'; im.alt=alt||''; im.onerror=function(){ im.style.display='none'; }; return im; }
    function decorate(panel){
      var nameToPath={};
      var table=panel.querySelector('table');
      if(table){
        Array.prototype.forEach.call(table.querySelectorAll('tbody tr'),function(tr){
          var c=tr.querySelectorAll('td'); if(c.length<2) return;
          var code=c[1].querySelector('code'); if(!code) return;
          var path=webPath(code.textContent); if(!path) return;
          nameToPath[normName(c[0].textContent)]=path;
          c[0].insertBefore(thumb(path,'demo-thumb',''),c[0].firstChild); // inline thumb in the row
        });
      }
      // Larger preview beside each entity prompt (map = h3, characters/NPCs = h4).
      Array.prototype.forEach.call(panel.querySelectorAll('h3, h4'),function(h){
        if(h.getAttribute('data-thumbed')) return;
        var hn=normName(h.textContent), best=null;
        for(var k in nameToPath){ if(k && hn.indexOf(k)!==-1 && (!best||k.length>best.length)) best=k; }
        if(!best) return;
        h.setAttribute('data-thumbed','1');
        h.parentNode.insertBefore(thumb(nameToPath[best],'demo-thumb-side','art preview'),h.nextSibling);
      });
    }
    function select(i,push){
      tabs.forEach(function(t,j){
        t.panel.style.display=(j===i)?'':'none';
        t.btn.classList.toggle('active',j===i);
        t.btn.setAttribute('aria-selected',j===i?'true':'false');
      });
      if(!tabs[i].decorated){ decorate(tabs[i].panel); tabs[i].decorated=true; } // lazy: only the viewed tab fetches
      if(push){ try{ history.replaceState(null,'','#demo-'+i); }catch(e){} }
    }
    tabs.forEach(function(t,i){
      var p=document.createElement('section');
      p.className='demo-panel';
      t.nodes.forEach(function(n){ p.appendChild(n); });
      mount.appendChild(p);
      t.panel=p;
      var b=document.createElement('button');
      b.className='demo-tab';
      b.type='button';
      b.textContent=t.title;
      b.setAttribute('role','tab');
      b.addEventListener('click',function(){ select(i,true); });
      bar.appendChild(b);
      t.btn=b;
    });
    var start=0,hm=(location.hash||'').match(/^#demo-(\d+)$/);
    if(hm){ var hi=parseInt(hm[1],10); if(hi>=0&&hi<tabs.length) start=hi; }
    select(start,false);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init);
  else init();
})();
</script>

<!--TAB:Level 3 : Goblin Warrens-->
## ⚔️ Demo L3 — The Goblin Warrens  ·  *party level 3*

Tier-1 starter dungeon. A goblin warband raids the trade road from a warren of tunnels.

**Progress: 0 / 10 images generated** — every token below still renders as a plain coloured ring (`image_url=None`). Generate the art, drop it at the listed path, then wire it in `app/demo_campaigns.py`.

| Entity | Drop file at | Status |
|---|---|---|
| 🗺️ The Goblin Warrens (map) | `app/static/demo/maps/goblin-warrens.png` | ⬜ needs art |
| 🛡️ Thorin Battlehammer | `app/static/demo/tokens/l3-thorin.jpg` | ⬜ needs art |
| 🗡️ Nyx Shadowstep | `app/static/demo/tokens/l3-nyx.jpg` | ⬜ needs art |
| ✨ Sister Elsbeth | `app/static/demo/tokens/l3-elsbeth.jpg` | ⬜ needs art |
| 🔥 Aldric the Sudden | `app/static/demo/tokens/l3-aldric.jpg` | ⬜ needs art |
| 🏹 Brisa Quickarrow | `app/static/demo/tokens/l3-brisa.jpg` | ⬜ needs art |
| 👹 Grukk the Warlord | `app/static/demo/tokens/l3-grukk.jpg` | ⬜ needs art |
| 👺 Goblin Skirmisher | `app/static/demo/tokens/l3-goblin-skirmisher.jpg` | ⬜ needs art |
| 👺 Goblin Sneak | `app/static/demo/tokens/l3-goblin-sneak.jpg` | ⬜ needs art |
| 🐺 Warg | `app/static/demo/tokens/l3-warg.jpg` | ⬜ needs art |

### 🗺️ Battle map — The Goblin Warrens (1400×1000)

> Top-down tabletop battle map of a goblin warren entrance carved into a rocky hillside. A jagged cave mouth opens into branching tunnels of packed earth and stone; a crude wooden palisade of lashed, sharpened stakes guards the approach, hung with bone totems and tattered goblin banners. Scattered animal bones, a cold fire-pit ringed with cooking spits, gnawed crates from raided trade caravans, and muddy worg tracks litter the ground. Painterly fantasy cartography, muted earth tones with cold green shadow in the tunnel mouths, slight three-quarter overhead angle, crisp 5-foot square grid overlay across the whole map, no characters, no tokens. 1400×1000.

Negative prompt: `text, characters, tokens, UI overlay, modern objects`

### 🛡️ Player characters

#### Thorin Battlehammer — Mountain Dwarf Fighter 3 (Battle Master)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle warm rim-lighting, no frame, no text. A stout, broad-shouldered mountain dwarf front-liner with a gruff, clan-proud bearing and braided iron-grey beard clasped with clan rings. He wears battered, well-fitted plate armor (AC 18) etched with hammer-and-anvil clan heraldry, and stands in a poised duelist's stance rather than a wall's brace. He grips a rune-stamped warhammer in one fist with a pair of handaxes tucked at his belt. Deep-set determined eyes, dwarven craftsmanship in every buckle, warm forge-light glinting off the steel. Recommended 1:1 square, 1024×1024.

#### Nyx Shadowstep — Wood Elf Rogue 3 (Assassin)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle warm rim-lighting, no frame, no text. A lithe, silent wood-elf scout and assassin, half-lost in shadow, with sharp angular features, leaf-green eyes, and dark hair bound back for the hunt. She wears supple muted-green and grey leather armor over a hooded cloak, half-drawn so shadow pools in the cowl. A slim rapier rides at her hip and a shortbow is slung over one shoulder; one gloved hand rests near the blade as if to open a fight from the dark. Cool low-key lighting with a single warm rim-light along her cheek and shoulder. Recommended 1:1 square, 1024×1024.

#### Sister Elsbeth — Human Cleric 3 (Light Domain)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle warm rim-lighting, no frame, no text. A human radiant battle-priestess of the Light Domain, warm but unyielding, with a steady compassionate gaze and short practical hair. She wears polished chain mail draped with a white-and-gold tabard, and holds aloft a sunburst holy symbol that sheds golden radiant light across her face and armor. A flanged mace hangs ready at her side. The glow burns away surrounding shadow with halo-bright, sun-warm light. Recommended 1:1 square, 1024×1024.

#### Aldric the Sudden — Forest Gnome Wizard 3 (Evocation)

> Painterly digital fantasy character portrait, full body for this small race, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle warm rim-lighting, no frame, no text. A small, twitchy forest gnome evoker with wide alert eyes, a wild shock of hair, and the tense look of someone silently counting seconds before a fireball. He wears scorch-marked arcane robes in deep reds and oranges, a dagger at his belt, and one hand cupped around a flickering ember of evocation flame that casts warm orange light over his face. Embers and faint heat-shimmer trail from his fingertips. Recommended 1:1 square, 1024×1024.

#### Brisa Quickarrow — Lightfoot Halfling Ranger 3 (Hunter)

> Painterly digital fantasy character portrait, full body for this small race, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle warm rim-lighting, no frame, no text. A cheerful lightfoot halfling archer with curly hair, freckles, and a bright confident grin. She wears practical brown-and-green leather armor and carries a longbow nocked-ready in one hand with a shortsword at her hip. Her quiver is notched with tiny carved tally-marks — her running kill-count — and she stands light on her feet, mid-step, as if already sighting the next goblin. Warm woodland rim-lighting. Recommended 1:1 square, 1024×1024.

### 👹 NPCs — the encounter

#### Grukk the Warlord — goblin warlord (Bandit Captain)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, menacing expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle warm rim-lighting, no frame, no text. A hulking, battle-scarred goblin warlord — bigger and meaner than his kin — with mottled green skin, a notched ear, yellow eyes, and a fanged sneer of command. He wears scavenged mismatched plate and chain looted from fallen caravan guards, a trophy-strung cloak of bones and broken weapons, and a crude crown of bent swords. He brandishes a wicked scimitar in one hand and a hand-axe in the other, every inch the bandit captain who rules by force. Cruel firelight glints off his armor. Recommended 1:1 square, 1024×1024.

#### Goblin Skirmisher — goblin warband fighter

> Painterly digital fantasy character portrait, full body for this small race, snarling expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle warm rim-lighting, no frame, no text. A wiry, hunched goblin skirmisher with mottled green-grey skin, oversized pointed ears, a flat broad nose, and sharp little fangs bared in a battle-snarl. He wears scrappy patchwork leather and rusted scavenged scraps of armor, and brandishes a notched scimitar with a small battered shield. Quick, vicious, and feral, crouched low for a darting strike. Cold cave light with a warm rim along one shoulder. Recommended 1:1 square, 1024×1024.

#### Goblin Sneak — goblin ambusher

> Painterly digital fantasy character portrait, full body for this small race, sly expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle warm rim-lighting, no frame, no text. A skulking goblin sneak with mottled green-grey skin, oversized ears flattened back, and narrowed cunning eyes over a thin sly grin. He wears a dark ragged hood and muted scavenged leathers built for ambush, creeping low with a wicked dagger held in a reverse grip and a sling tucked at his belt. Hunched and furtive, half-melting into shadow, ready to backstab. Cool low-key light with a single warm rim. Recommended 1:1 square, 1024×1024.

#### Warg — fanged goblin-mount wolf

> Painterly digital fantasy creature portrait, full body, snarling aggressive expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle warm rim-lighting, no frame, no text. A massive, shaggy warg — an oversized evil wolf used as a goblin mount — with coarse grey-black fur, glowing yellow eyes, a scarred muzzle, and a slavering jaw of yellowed fangs bared in a snarl. Lean and powerful, hackles raised, muscles tensed mid-prowl. A crude goblin riding harness of rope and bone is buckled across its back. Cold predatory light with a warm rim along its raised hackles. Recommended 1:1 square, 1024×1024.

<!--TAB:Level 5 : Tide-Wracked Catacombs-->
## 🌊 Demo L5 — The Tide-Wracked Catacombs  ·  *party level 5*

The Tier-2 power-spike tier. A drowned crypt beneath a ruined lighthouse spills undead onto the coast at every high tide.

**Progress: 0 / 10 images generated** — every token below still renders as a plain coloured ring (`image_url=None`). Generate the art, drop it at the listed path, then wire it in `app/demo_campaigns.py`.

| Entity | Drop file at | Status |
|---|---|---|
| 🗺️ The Tide-Wracked Catacombs (map) | `app/static/demo/maps/tide-wracked-catacombs.png` | ⬜ needs art |
| 🛡️ Sir Gareth Tidebreaker (Human Fighter 5) | `app/static/demo/tokens/l5tide-gareth.jpg` | ⬜ needs art |
| 🛡️ Maelis Stormcaller (High Elf Wizard 5) | `app/static/demo/tokens/l5tide-maelis.jpg` | ⬜ needs art |
| 🛡️ Mother Coralind (Half-Elf Cleric 5) | `app/static/demo/tokens/l5tide-coralind.jpg` | ⬜ needs art |
| 🛡️ Vesh Quillon (Wood Elf Rogue 5) | `app/static/demo/tokens/l5tide-vesh.jpg` | ⬜ needs art |
| 🛡️ Hrudd Saltmane (Half-Orc Barbarian 5) | `app/static/demo/tokens/l5tide-hrudd.jpg` | ⬜ needs art |
| 💀 Brine Skeleton | `app/static/demo/tokens/l5tide-brine-skeleton.jpg` | ⬜ needs art |
| 💀 Drowned Zombie | `app/static/demo/tokens/l5tide-drowned-zombie.jpg` | ⬜ needs art |
| 💀 Tide Ghoul | `app/static/demo/tokens/l5tide-tide-ghoul.jpg` | ⬜ needs art |
| 💀 Captain of the Drowned (Wight) | `app/static/demo/tokens/l5tide-drowned-captain.jpg` | ⬜ needs art |

### 🗺️ Battle map — The Tide-Wracked Catacombs (1400×1000)

> Top-down fantasy battle map, slight overhead three-quarter tilt, of a drowned crypt beneath a ruined seaside lighthouse. Seawater floods the lower halls in murky teal pools, lapping through cracked stone corridors and spilling between toppled, barnacle-crusted sarcophagi. Seaweed and kelp drape the broken pillars, mussels and brine-crust cling to the walls, and a wide central stone stair rises out of the water to a sealed crypt door — the last dry ground holding back the tide. Shafts of cold storm-grey light fall through a collapsed ceiling onto a tide-line of foam and bone. Crumbled funerary niches, rusted iron grates, scattered ribcages and waterlogged coffins fill the flanking chambers. Clean 5-foot square grid overlay across the whole map, muted cold sea-storm palette of teal, slate, bone-white and rust. Painterly digital fantasy cartography, high detail, no characters.

Negative prompt: `text, characters, tokens, UI overlay, modern objects`

### 🛡️ Player characters

#### Sir Gareth Tidebreaker — Human Fighter 5 (Champion)

> A steadfast human knight in storm-darkened full plate armour, salt-rimed and dented from holding the crypt stair, a heavy weather-beaten storm-cloak billowing from his pauldrons. He grips a longsword with a brace of javelins slung at his back, jaw set in dutiful resolve, sea-spray beading on the metal. Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle cold sea-storm rim-lighting, no frame, no text.

#### Maelis Stormcaller — High Elf Wizard 5 (Evocation)

> A theatrical, tempest-touched high elf wizard with windswept pale hair crackling at the tips, one hand raised mid-flourish as a curl of orange firelight and storm-static dances over the fingertips. Elegant teal-and-grey arcane robes trimmed with lightning motifs, a slim dagger at the belt, eyes alight with the showman's glee of narrating a blast radius. Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle cold sea-storm rim-lighting, no frame, no text.

#### Mother Coralind — Half-Elf Cleric 5 (Tempest Domain)

> A grave half-elf storm-priestess of the drowned coast, plate-and-vestment armour the colour of deep sea-glass, a faint ring of spectral storm-wrath shimmering at her shoulders. She bears a rune-etched warhammer, holy symbol shaped like a cresting wave clutched at her chest, brine-soaked braids and a tidal calm in her steady eyes. Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle cold sea-storm rim-lighting, no frame, no text.

#### Vesh Quillon — Wood Elf Rogue 5 (Assassin)

> A laconic, marsh-born wood elf assassin half-melted into shadow, hood drawn low over sharp angular features and watchful pale-green eyes. Mottled grey-green leather armour streaked with bog-mud, a slender rapier drawn low in one hand and a hand crossbow ready in the other, poised to open from the dark. Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle cold sea-storm rim-lighting, no frame, no text.

#### Hrudd Saltmane — Half-Orc Barbarian 5 (Path of the Berserker)

> A loud, fearless half-orc reaver, broad and battle-scarred with a tangled salt-crusted mane and tusked grin, drenched to the waist from wading flooded halls. He hefts a massive greataxe over one shoulder with handaxes lashed across his chest, half-plate and hide armour barnacled and dripping, green-grey skin slick with seawater. Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle cold sea-storm rim-lighting, no frame, no text.

### 💀 NPCs — the encounter

#### Brine Skeleton

> A waterlogged undead skeleton risen from the drowned crypt, yellowed bones crusted with white brine and clinging barnacles, ribbons of green seaweed snagged in its empty ribcage. Hollow eye-sockets glow faint sea-green, a rusted notched cutlass gripped in skeletal fingers, seawater dripping from every joint. Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle cold sea-storm rim-lighting, no frame, no text.

#### Drowned Zombie

> A bloated, drowned undead zombie, grey-green waterlogged flesh sloughing from its frame, kelp and mussels matted into its rotting clothes. Milky drowned eyes stare blankly, seawater and silt spilling from its slack jaw, arms reaching forward in shambling hunger as brine streams down its swollen limbs. Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle cold sea-storm rim-lighting, no frame, no text.

#### Tide Ghoul

> A gaunt, feral tide ghoul, slick grey-blue skin stretched over sharp bones, webbed claws and a maw of needle teeth flecked with brine. Sunken predatory eyes gleam pale in the gloom, lank seaweed-tangled hair plastered to its skull, water sheeting off its hunched, twitching frame as it crouches to spring. Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression unless noted, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle cold sea-storm rim-lighting, no frame, no text.

#### Captain of the Drowned (Wight)

> A commanding undead wight captain, the Captain of the Drowned, clad in corroded ceremonial sea-officer's armour green with verdigris and crusted with coral. Cold blue grave-light burns in his hollowed eyes beneath a barnacled tricorne-style helm, a rusted officer's longsword raised in authority, tattered storm-grey cloak trailing kelp and brine. Painterly digital fantasy character portrait, three-quarter view from the chest up, menacing expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle cold sea-storm rim-lighting, no frame, no text.

<!--TAB:Level 9 : Storm Over Saltmarsh-->
## 🦈 Demo L9 — Storm Over Saltmarsh  ·  *party level 9*

A Tier-2/3 coastal adventure run by the demo's second GM. Sahuagin raiders boil up from a storm-wracked reef.

**Progress: 0 / 10 images generated** — every token below still renders as a plain coloured ring (`image_url=None`). Generate the art, drop it at the listed path, then wire it in `app/demo_campaigns.py`.

| Entity | Drop file at | Status |
|---|---|---|
| 🗺️ The Drowned Reef (map) | `app/static/demo/maps/drowned-reef.png` | ⬜ needs art |
| 🛡️ Vaelith Stormscale (PC) | `app/static/demo/tokens/l9-vaelith.jpg` | ⬜ needs art |
| 🛡️ Lirael Songhaven (PC) | `app/static/demo/tokens/l9-lirael.jpg` | ⬜ needs art |
| 🛡️ Oakheart Mossbrook (PC) | `app/static/demo/tokens/l9-oakheart.jpg` | ⬜ needs art |
| 🛡️ Ser Kadvan Tideward (PC) | `app/static/demo/tokens/l9-kadvan.jpg` | ⬜ needs art |
| 🛡️ Brother Tym (PC) | `app/static/demo/tokens/l9-tym.jpg` | ⬜ needs art |
| 🔱 Sahuagin Raider (NPC) | `app/static/demo/tokens/l9-sahuagin-raider.jpg` | ⬜ needs art |
| 🔱 Sahuagin Priestess (NPC) | `app/static/demo/tokens/l9-sahuagin-priestess.jpg` | ⬜ needs art |
| 🔱 Reef Shark (NPC) | `app/static/demo/tokens/l9-reef-shark.jpg` | ⬜ needs art |
| 🔱 Tide Elemental (NPC) | `app/static/demo/tokens/l9-tide-elemental.jpg` | ⬜ needs art |

### 🗺️ Battle map — The Drowned Reef (1600×1100)

> Top-down tactical battle map of a storm-wracked tidal reef at low tide, painterly digital fantasy style, slight overhead three-quarter pitch. Exposed coral shelves and slick black rock spurs ring scattered glassy tide pools; a half-sunken, barnacle-crusted shipwreck lists across the center with its broken mast bridging two reef plates. Foaming surf and churning grey-green storm swells crash inward at every edge, sea-foam streaking across wet stone. Bioluminescent kelp and anemones glow faint blue-green in the pools, rain-streaked light from a bruised thunderhead sky, lightning glow on the horizon. Crisp 5-foot square grid overlay across the whole playable surface, even lighting for tabletop readability, no characters, no tokens.

Negative prompt: `text, characters, tokens, UI overlay, modern objects`

### 🛡️ Player characters

#### Vaelith Stormscale — Tiefling Sorcerer 9 (Draconic Bloodline)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral imperious expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle stormy sea rim-lighting, no frame, no text. A storm-born tiefling sorceress of draconic frost bloodline: pale blue-grey skin faintly scaled at the cheekbones and temples, curving silver-blue horns, frost rimes her dark hair and breath, glacial pale eyes glowing cold. A sinuous draconic tail curls into frame. Layered dark teal-and-silver arcane robes with frost-crystal embroidery, a rime-edged dagger sheathed at her hip, wisps of cold mist and snowflakes drifting from one raised hand.

#### Lirael Songhaven — Half-Elf Bard 9 (College of Lore)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, lively knowing half-smile, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle stormy sea rim-lighting, no frame, no text. A silver-tongued half-elf lore bard with windswept honey-brown hair, slightly pointed ears, bright clever eyes mid-narration. Fine sea-faring finery in deep blues and brass — embroidered coat, ruffled collar, a lute of pale spiral-grained driftwood slung across her chest. A slim rapier and a compact hand crossbow at her belt, a small open notebook of drowned songs tucked under one arm, salt spray glinting in her hair.

#### Oakheart Mossbrook — Firbolg Druid 9 (Circle of the Moon)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, calm watchful expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle stormy sea rim-lighting, no frame, no text. A towering firbolg moon-druid with pale grey-blue bovine-ish features — long soft ears, a broad gentle muzzle, small mossy horns, deep amber eyes. Living moss, kelp, and barnacle clusters grow across his shoulders and natural druidic garb of woven sea-grass and weathered leather. A curved scimitar of antler-and-stone at his side, a faint silver moonglow shimmering at the edges of his fur as if mid-transformation into a storm-beast.

#### Ser Kadvan Tideward — Human Paladin 9 (Oath of Vengeance)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, grim unsmiling expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle stormy sea rim-lighting, no frame, no text. A grim oath-bound human knight, weathered scarred face, short rain-soaked dark hair, hard hunter's eyes fixed on a distant prey. Heavy full plate (AC 20) in storm-grey steel etched with vengeance sigils, a tabard of dark sea-blue, salt and seawater beaded on the armour. A longsword drawn low and a javelin sheathed at his back, faint cold divine light tracing the plate's edges, the relentless air of a man hunting a raider-lord across the tides.

#### Brother Tym — Water Genasi Monk 9 (Way of the Open Hand)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, eerily serene expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle stormy sea rim-lighting, no frame, no text. A water genasi monk with translucent sea-blue skin marbled by faint flowing currents, hair like rippling water frozen mid-motion, calm pale-aqua eyes with no whites, a thin sheen of moisture always on his skin. Simple undyed sea-grey monk robes belted with rope, a slender driftwood shortspear held loosely. Beads of water orbit one open palm, his stance balanced and weightless as if poised to run across a wave.

### 🔱 NPCs — the encounter

#### Sahuagin Raider

> Painterly digital fantasy character portrait, three-quarter view from the chest up, hostile snarling expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle stormy sea rim-lighting, no frame, no text. A vicious sahuagin sea-devil raider: glistening blue-green scaled hide, a finned ridge running over its skull, black bulging shark-like eyes, a jaw crammed with needle teeth, gill slits flaring at its neck. Webbed clawed hands grip a barbed bone trident and a net of woven kelp and sinew. Coral-shard and shark-tooth ornaments, dripping seawater, the feral predatory posture of a reef-born raider mid-attack.

#### Sahuagin Priestess

> Painterly digital fantasy character portrait, three-quarter view from the chest up, cold zealous expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle stormy sea rim-lighting, no frame, no text. A sahuagin priestess of the shark-god: deep indigo-and-teal scaled hide, an elaborate crest of dorsal fins and spines, four arms ending in webbed claws, baleful luminous eyes. Draped in regalia of black pearls, shark-jaw fetishes, and bleached bone, clutching a coral-and-bone ritual staff topped with a glowing abyssal pearl. Tendrils of dark water magic coil around her, the eerie authority of a deep-sea cult leader.

#### Reef Shark

> Painterly digital fantasy creature portrait, three-quarter view, predatory side-on framing of head and forebody, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle stormy sea rim-lighting, no frame, no text. A sleek grey reef shark surging through churning green water: countershaded slate-grey back fading to pale underbelly, a blunt powerful snout, lifeless black eye, gill slits and jagged tooth-lined jaw slightly agape. Sharp pectoral and dorsal fins cutting the current, motion blur of foam and bubbles trailing its tail, the cold mindless menace of a storm-driven hunter.

#### Tide Elemental (Water Elemental)

> Painterly digital fantasy creature portrait, three-quarter view from the chest up, faceless elemental presence, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, subtle stormy sea rim-lighting, no frame, no text. A towering tide elemental — a roiling humanoid mass of translucent storm-green seawater, foam, and torn kelp, its form constantly collapsing and reforming into surging waves. Two faint glowing whitecap "eyes" hint at a face within the churn; spray, brine, and small swept-up shells swirl through its body. Rivulets of water arc off its crest, the raw oceanic fury of the storm given shape and will.

<!--TAB:Level 13 : Shadowfell Spire-->
## 🌑 Demo L13 — The Shadowfell Spire  ·  *party level 13*

A Tier-3 dark-fantasy siege. A spire of black glass bleeds the Shadowfell into the world; undead and worse spill out.

**Progress: 0 / 9 images generated** — every token below still renders as a plain coloured ring (`image_url=None`). Generate the art, drop it at the listed path, then wire it in `app/demo_campaigns.py`.

| Entity | Drop file at | Status |
|---|---|---|
| 🗺️ The Shadowfell Spire (map) | `app/static/demo/maps/shadowfell-spire.png` | ⬜ needs art |
| 🛡️ Maelen Farsight — High Elf Wizard 13 | `app/static/demo/tokens/l13-maelen.jpg` | ⬜ needs art |
| 🛡️ Cassius Emberbinder — Tiefling Warlock 13 | `app/static/demo/tokens/l13-cassius.jpg` | ⬜ needs art |
| 🛡️ High Cleric Doran — Goliath Cleric 13 | `app/static/demo/tokens/l13-doran.jpg` | ⬜ needs art |
| 🛡️ Hruld Skullcleaver — Half-Orc Barbarian 13 | `app/static/demo/tokens/l13-hruld.jpg` | ⬜ needs art |
| 🛡️ Wisp Underbough — Forest Gnome Rogue 13 | `app/static/demo/tokens/l13-wisp.jpg` | ⬜ needs art |
| 💀 Spire Wraith | `app/static/demo/tokens/l13-spire-wraith.jpg` | ⬜ needs art |
| 💀 Vampire Spawn ×2 (shared file) | `app/static/demo/tokens/l13-vampire-spawn.jpg` | ⬜ needs art |
| 💀 Illithid Adept (Mind Flayer) | `app/static/demo/tokens/l13-illithid-adept.jpg` | ⬜ needs art |

### 🗺️ Battle map — The Shadowfell Spire (1600×1200)

> Top-down tabletop battle map, 1600×1200 px, slight overhead angle: the cracked threshold plaza at the foot of a colossal spire of black volcanic glass that rears up off the top edge of the frame, its obsidian flanks fractured and bleeding ribbons of violet shadow-mist. Floor of shattered obsidian flagstones streaked with frost-grey ash; jagged shadow-rifts split the ground, glowing cold violet and venting smoke. Withered grey thorn-vegetation and leafless skeletal trees cling to the edges; scattered bleached bones, broken weapons, and a toppled funerary statue litter the stone. A faint 5-foot square grid overlay across the whole map. Muted desaturated palette — black, slate, bone-white, bruised violet. Painterly dark-fantasy cartography, even top-down lighting, no characters, no tokens.

Negative prompt: `text, characters, tokens, UI overlay, modern objects`

### 🛡️ Player characters

#### Maelen Farsight — High Elf Wizard 13 (School of Divination)

> Painterly digital dark-fantasy character portrait, three-quarter view from the chest up, neutral serene expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, cold violet shadowfell rim-lighting, no frame, no text. An ice-calm high elf diviner with pale luminous skin, sharp angular features, and long silver-white hair; pale glacial-blue eyes that seem to look past the viewer. Faint glowing third-eye sigil shimmering on his brow. Fine layered robes of frost-white and deep indigo trimmed with silver astrological glyphs. Holds a slender pale-wood quarterstaff topped with a floating crystalline foresight-rune. Aura of quiet certainty. 1:1 square, 1024×1024.

#### Cassius Emberbinder — Tiefling Warlock 13 (The Fiend)

> Painterly digital dark-fantasy character portrait, three-quarter view from the chest up, glib half-smile, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, cold violet shadowfell rim-lighting, no frame, no text. A charismatic crimson-skinned tiefling warlock with curling black infernal horns, slit golden eyes, and a barbed tail flicking into frame. Dark finery — a high-collared black-and-burgundy coat with infernal brass clasps. Wisps of eldritch force-energy crackle violet-and-ember around one upraised hand, lit from within as if paying a debt. Roguish confident set to the mouth. 1:1 square, 1024×1024.

#### High Cleric Doran — Goliath Cleric 13 (War Domain)

> Painterly digital dark-fantasy character portrait, three-quarter view from the chest up, fearless resolute expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, cold violet shadowfell rim-lighting, no frame, no text. A mountainous goliath war-priest with grey-stone skin marked by darker lithoderm patterns, a bald scarred head, and a heavy jaw. Clad in dented radiant heavy plate armor inlaid with a glowing golden warding sun-sigil at the chest that pushes warm holy light back against the violet gloom. One huge hand rests on the haft of a massive warhammer maul slung over a shoulder. Booming, immovable presence. 1:1 square, 1024×1024.

#### Hruld Skullcleaver — Half-Orc Barbarian 13 (Path of the Totem Warrior)

> Painterly digital dark-fantasy character portrait, three-quarter view from the chest up, grim defiant expression with a flicker of a wild grin, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, cold violet shadowfell rim-lighting, no frame, no text. A towering half-orc totem barbarian with weathered green-grey skin, jutting lower tusks, and a face crossed with old battle scars. Wild dark hair bound back; bear-totem fetishes — claws, teeth, a small carved bear skull — hung from leather straps across a bare scarred chest. Hefts a brutal worn greataxe over one shoulder, knuckles white on the haft. Sweat and old blood; unstoppable presence. 1:1 square, 1024×1024.

#### Wisp Underbough — Forest Gnome Rogue 13 (Arcane Trickster)

> Painterly digital dark-fantasy character portrait, three-quarter view from the chest up, impish sidelong smirk, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, cold violet shadowfell rim-lighting, no frame, no text. A small quick forest gnome arcane trickster with warm brown skin, bright mischievous eyes, and a tousled mop of mossy-brown hair. Snug dark leather armor and a hooded half-cloak. A faint arcane shimmer of pale violet runes drifts around her fingers; she half-turns as if already slipping out of frame. Carries a slender rapier and a compact hand crossbow tucked at her hip, with a tiny spellbook chained to her belt. 1:1 square, 1024×1024.

### 💀 NPCs — the encounter

#### Spire Wraith

> Painterly digital dark-fantasy character portrait, three-quarter view from the chest up, malevolent hollow expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, cold violet shadowfell rim-lighting, no frame, no text. An incorporeal undead wraith born of the spire — a hooded, tattered shroud of frayed black shadow-cloth that dissolves into drifting violet smoke where a body should be. Beneath the cowl, a void of darkness pierced by two burning points of cold pale light for eyes. Skeletal smoke-wreathed hands reaching from ragged sleeves, fingers tipped with frost. Trailing ribbons of shadowstuff. Menacing, weightless, draining presence. 1:1 square, 1024×1024.

#### Vampire Spawn ×2 — two identical tokens, generate once, reuse for both

> Painterly digital dark-fantasy character portrait, three-quarter view from the chest up, feral hungry snarl baring fangs, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, cold violet shadowfell rim-lighting, no frame, no text. A newly-risen vampire spawn — corpse-pale grey-white skin stretched tight over gaunt features, bloodshot crimson eyes, and elongated fangs. Lank dark hair and a smear of dried blood at the lips. Wears the torn, grave-stained remnants of fine clothing — a ruined dark doublet, frayed collar. Clawed hands raised, half-crouched and predatory. Cruel, ravenous, recently-dead pallor. 1:1 square, 1024×1024.

#### Illithid Adept (Mind Flayer)

> Painterly digital dark-fantasy character portrait, three-quarter view from the chest up, coldly impassive alien expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, cold violet shadowfell rim-lighting, no frame, no text. A mind flayer adept with a bulbous mauve-and-violet octopoid head, four writhing facial tentacles framing a lamprey maw, and milky pupil-less white eyes. Slick rubbery amphibian skin glistening with mucus. Robed in elaborate dark psionic-priest vestments of deep purple and tarnished bronze, set with a faintly glowing soul-gem at the throat. One slender clawed hand raised as if exerting psychic dominance, faint violet mind-energy haloing the skull. Utterly alien, calculating menace. 1:1 square, 1024×1024.

<!--TAB:Level 18 : Dragon's Apotheosis-->
## 🐉 Demo L18 — The Dragon's Apotheosis  ·  *party level 18*

A Tier-4 capstone. An ancient red wyrm is ascending to godhood atop a volcano; the party has one shot to stop it.

**Progress: 0 / 9 images generated** — every token below still renders as a plain coloured ring (`image_url=None`). Generate the art, drop it at the listed path, then wire it in `app/demo_campaigns.py`.

| Entity | Drop file at | Status |
|---|---|---|
| 🗺️ The Caldera Throne (map) | `app/static/demo/maps/caldera-throne.png` | ⬜ needs art |
| 🛡️ Archmagus Selene — High Elf Wizard 18 | `app/static/demo/tokens/l18-selene.jpg` | ⬜ needs art |
| 🛡️ Ignar Flamesoul — Dragonborn Sorcerer 18 | `app/static/demo/tokens/l18-ignar.jpg` | ⬜ needs art |
| 🛡️ Dame Aurelia Dawnward — Aasimar Paladin 18 | `app/static/demo/tokens/l18-aurelia.jpg` | ⬜ needs art |
| 🛡️ Bryn Ironwall — Goliath Fighter 18 | `app/static/demo/tokens/l18-bryn.jpg` | ⬜ needs art |
| 🛡️ Thornroot Elder — Firbolg Druid 18 | `app/static/demo/tokens/l18-thornroot.jpg` | ⬜ needs art |
| 🐉 Pyraxis the Ascendant — Adult Red Dragon (boss) | `app/static/demo/tokens/l18-pyraxis.jpg` | ⬜ needs art |
| 🔥 Fire Giant Honor Guard ×2 (shared file) | `app/static/demo/tokens/l18-fire-giant.jpg` | ⬜ needs art |
| 🔮 Cult Archmage | `app/static/demo/tokens/l18-cult-archmage.jpg` | ⬜ needs art |

### 🗺️ Battle map — The Caldera Throne (1800×1300)

> Top-down tactical battle map of a volcanic caldera throne, 1800×1300. A massive rune-carved obsidian dais sits dead-centre, its black glass surface etched with glowing draconic sigils that pulse molten-orange. Rivers and channels of bright magma snake outward from the dais, splitting a cracked basalt floor into jagged islands of stone that glow orange along every fissure. Rising heat-shimmer and drifting ash haze soften the edges; pools of liquid fire cast warm light upward across the rock. Faint sulfur-yellow vents and cooling lava crusts add texture at the rim. Painterly digital fantasy cartography, slight overhead three-quarter tilt, crisp readable terrain, a subtle 5-foot square grid overlay aligned to the floor, no characters, no tokens, no UI.

Negative prompt: `text, characters, tokens, UI overlay, modern objects`

### 🛡️ Player characters

#### Archmagus Selene — High Elf Wizard 18 (Evocation)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, hot volcanic ember rim-lighting, no frame, no text. A high elf archmage of a century's preparation: sharp ageless features, pale luminous skin, long silver-white hair bound in an elaborate braided coronet, faintly glowing pale-gold eyes, calm and detached. Layered archmage robes of deep midnight-blue and violet, threaded with silver evocation runes and a high collar set with cold starlight gems. One open hand cradles a spark of incandescent meteor-fire, embers and tiny falling motes of flame orbiting her fingers. No weapon. Square 1:1, 1024×1024.

#### Ignar Flamesoul — Dragonborn Sorcerer 18 (Draconic Bloodline)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, neutral expression with a proud theatrical tilt, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, hot volcanic ember rim-lighting, no frame, no text. A draconic-bloodline dragonborn sorcerer: scaled red-and-bronze draconic head, ridged brow and curved horns, slit golden eyes, smoke curling from his nostrils. Rich sorcerer's robes of crimson and burnished bronze with flame-shaped trim, sleeves rolled to show scaled forearms wreathed in living fire. One clawed hand raised, a sphere of roaring dragon-fire crackling in his palm as he answers a dragon-god in kind. Square 1:1, 1024×1024.

#### Dame Aurelia Dawnward — Aasimar Paladin 18 (Oath of Devotion)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, serene expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, hot volcanic ember rim-lighting, no frame, no text. A radiant aasimar paladin, the party's unbreakable anchor: flawless luminous skin with faint glowing celestial markings tracing her cheekbones, calm pale eyes lit from within, a soft golden halo and half-furled radiant wings of light behind her shoulders. Gleaming silver-and-gold plate armour catching warm divine light, a white tabard. She holds aloft a Holy Avenger longsword whose blade burns with clean golden-white radiance that pushes back the surrounding ember glow. Square 1:1, 1024×1024.

#### Bryn Ironwall — Goliath Fighter 18 (Champion)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, a faint hard grin (he only smiles when outnumbered), isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, hot volcanic ember rim-lighting, no frame, no text. A goliath champion built like a mountain: massive grey stony skin marbled with darker lithoderm patches and tribal markings, bald head, heavy brow, pale grey eyes. Battered heavy plate armour scarred from outlasting dragons, pauldrons like boulders. He rests an enormous greatsword over one shoulder, its steel reflecting the molten orange around him. Stoic, immovable, unafraid. Square 1:1, 1024×1024.

#### Thornroot Elder — Firbolg Druid 18 (Circle of the Moon)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, grave elemental expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, hot volcanic ember rim-lighting, no frame, no text. An ancient firbolg archdruid who speaks for a mountain that hates the wyrm: tall, broad, with a long blunt bovine nose, mossy blue-grey skin like weathered bark, deep-set ageless eyes, lichen and small leaves growing along his brow, modest branching antlers. Robes of woven bark, root, and stone, hung with riverstones and bone fetishes. He grips a glowing Shillelagh quarterstaff sheathed in soft green druidic light that stands defiant against the surrounding fire. Square 1:1, 1024×1024.

### 🔥 NPCs — the encounter

#### Pyraxis the Ascendant — Adult Red Dragon (the boss)

> Painterly digital fantasy creature token, FULL BODY (not a portrait) of an adult red dragon, posed for a top-down-friendly three-quarter overhead view so the whole serpentine form reads inside a circular token, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, hot volcanic ember rim-lighting, no frame, no text. Pyraxis the Ascendant, an ancient red wyrm mid-apotheosis into godhood: coiled and menacing, crimson and blackened-scarlet scales running molten-gold at the seams as divine fire wells up beneath them, vast spread wings, sweeping horns and frilled crest, jaws parted around a glow of building flame, claws gripping obsidian. An aura of ascending godfire and rising sparks haloes the body. Enormous, predatory, triumphant. Square 1:1, 1024×1024.

#### Fire Giant Honor Guard ×2 (two identical tokens — generate once, reuse for both)

> Painterly digital fantasy character portrait, three-quarter view from the chest up, stern expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, hot volcanic ember rim-lighting, no frame, no text. A fire giant honor guard sworn to the ascending wyrm: charcoal-grey skin with a dull glowing-coal undertone, fiery orange flame-like hair and beard, smoldering ember eyes, heavy jaw. Soot-blackened iron plate armour trimmed with brass and volcanic glass, draconic cult sigils burned into the breastplate. A massive iron-and-obsidian sword rests against one shoulder, its edge faintly red-hot. Square 1:1, 1024×1024.

#### Cult Archmage — Archmage

> Painterly digital fantasy character portrait, three-quarter view from the chest up, cold zealot's expression, isolated against a fully transparent background, suitable for cropping to a 256×256 circular virtual-tabletop token, hot volcanic ember rim-lighting, no frame, no text. A human cult archmage devoted to the dragon's ascension: gaunt face, shaved or close-cropped head marked with branded draconic sigils, fervent fire-lit eyes. Dark scarlet-and-charcoal mage robes layered with scale-patterned mantle and a high asymmetric collar, gold dragon-claw clasps. One hand wreathed in violet-and-orange arcane fire, the air around him distorting with heat as he channels power to fuel the wyrm's apotheosis. Square 1:1, 1024×1024.

<!--TAB:ARCHIVE : The Sundered Vault-->
## 🗄️ Archive — The Sundered Vault  ·  *flagship · the original hand-built demo*

The original hand-built demo (`app/demo_seed.py`). All nine character tokens
ship as jpgs at `app/static/demo/tokens/` and are wired into `seed_tokens`;
the tavern map is a working placeholder you can regenerate for polish.

**Progress: 10 / 10 shipped** — every token is live; the only optional
regen is the placeholder battle map.

| Entity | File | Status |
|---|---|---|
| 🗺️ The Sundered Tavern (map) | `app/static/demo/maps/tavern.png` | 🟡 placeholder — regen optional |
| 🗡️ Pip Quickfingers | `app/static/demo/tokens/rogue.jpg` | ✅ shipped + wired |
| ✨ Thalindra Moonwhisper | `app/static/demo/tokens/wizard.jpg` | ✅ shipped + wired |
| ☀️ Brother Tavik Stonebrow | `app/static/demo/tokens/cleric.jpg` | ✅ shipped + wired |
| 🩸 Vex (Bandit Captain) | `app/static/demo/tokens/bandit-captain.jpg` | ✅ shipped + wired |
| 👺 Grixxa (Goblin Captain) | `app/static/demo/tokens/goblin-captain.jpg` | ✅ shipped + wired |
| 🏴 Bandit Alpha | `app/static/demo/tokens/bandit-alpha.jpg` | ✅ shipped + wired |
| 🏴 Bandit Beta | `app/static/demo/tokens/bandit-beta.jpg` | ✅ shipped + wired |
| 🏴 Bandit Gamma | `app/static/demo/tokens/bandit-gamma.jpg` | ✅ shipped + wired |
| 🪓 Thug | `app/static/demo/tokens/thug.jpg` | ✅ shipped + wired |

### 🛡️ Player characters

#### Pip Quickfingers — Halfling Rogue 5 (Thief)

> A young halfling rogue, female, three feet tall, slim and nimble.
> Shoulder-length copper-red hair tied back with a leather cord,
> mischievous emerald-green eyes, lightly freckled tan skin, a
> small smirk. Wearing dark brown studded-leather armor over a
> forest-green hooded tunic, a short sword sheathed at her hip,
> two daggers crossed on a leather bandolier across her chest,
> a small pouch of thieves' tools at her belt. Confident ready
> stance, one hand resting on the dagger hilt, the other casually
> at her side. Warm tavern firelight from below-left. Painterly
> fantasy character portrait, three-quarter view, isolated against
> a transparent background, suitable for a 256-pixel circular
> token. Halfling Chaotic Good. Mood: roguish, watchful, just
> waiting for an opening.

#### Thalindra Moonwhisper — Elf Wizard 5 (School of Evocation)

> An elf wizard, female, slender and elegant. Long silver-white hair
> flowing past her shoulders, calm violet eyes, pale luminous skin
> with a faint silver sheen at the temples. Wearing flowing midnight-
> blue spellcaster robes embroidered with silver constellations and
> evocation runes around the cuffs, a delicate silver circlet
> across her brow. An open spellbook tucked under one arm; her free
> hand cradles a small floating arcane sigil pulsing soft blue-purple
> light. Neutral composed expression, intellectual and patient.
> Subtle ambient moonlight aesthetic. Painterly fantasy character
> portrait, three-quarter view, isolated against a transparent
> background, suitable for a 256-pixel circular token. Elf Neutral
> Good. Mood: scholarly, precise, quietly powerful.

#### Brother Tavik Stonebrow — Hill Dwarf Cleric 5 (Life Domain)

> A hill dwarf cleric, male, mid-life, four and a half feet tall,
> stocky and broad-shouldered. Thick braided rust-red beard with
> two iron beads at the end, kind weathered face, deep brown eyes,
> sun-tanned skin. Wearing well-maintained chain mail under a
> leather tabard bearing an embossed golden sunburst holy symbol,
> a heavy war hammer strapped across his back, a small leather
> healer's kit at his belt. One hand raised in a benediction
> gesture (palm up, two fingers extended), the other resting
> calmly on the rim of a wooden round shield. Warm amber light
> suggesting a holy presence rises from the holy symbol. Painterly
> fantasy character portrait, three-quarter view, isolated against
> a transparent background, suitable for a 256-pixel circular
> token. Hill Dwarf Lawful Good. Mood: stoic, dependable, quietly
> radiant.

### 👹 NPCs — Tavern Brawl encounter

#### Vex Vance — Bandit Captain (CR 2)

> A human bandit captain, female, late thirties, lean and scarred.
> Raven-black hair pulled into a tight high braid, sharp grey eyes,
> a single thin scar from her right cheekbone down to her jaw, weathered
> olive skin. Wearing dark studded-leather armor with a crimson sash
> across the waist, a curved scimitar at her hip and a throwing
> dagger at her belt. Standing with weight on one hip, one hand
> resting on the scimitar's hilt, the other gesturing as if mid-
> bark — issuing a command. Dim warm tavern firelight reflecting
> off the leather. Painterly fantasy character portrait, three-
> quarter view, isolated against a transparent background, suitable
> for a 256-pixel circular token. Human, any non-lawful. Mood:
> dangerous leader, in command of a bad situation.

#### Grixxa — Goblin Captain (homebrew CR 1)

> A goblin captain, female, four feet tall, wiry. Mottled green-grey
> skin, oversized pointed ears, bright yellow eyes with vertical
> slit pupils, a wild crown of jet-black hair tied with bones and
> red feathers. Wearing battered studded-leather armor stitched with
> patches taken from bandit-spoils (a fragment of a tabard, a torn
> sleeve), a curved scimitar gripped in one hand and a bone-tipped
> javelin in the other. Standing on top of a wooden tavern table
> mid-shout, mouth open in a battle-cry showing pointed teeth.
> Firelight from below dramatizing the silhouette. Painterly
> fantasy character portrait, dynamic three-quarter pose, isolated
> against a transparent background, suitable for a 256-pixel
> circular token. Small Humanoid, neutral evil. Mood: fierce,
> cunning, the dangerous brain of a band that punches above its
> weight.

#### Thug

> A burly human thug, male, mid-thirties, six feet tall, heavily
> muscled. Shaved head with stubble shadow, a broken-and-set nose,
> knuckle tattoos (one letter per finger reading "PAID" on the
> right hand), a thick raised scar across his left bicep, dark
> brown eyes that never quite reach his smile. Wearing brown
> leather armor with reinforced metal-studded gauntlets, a heavy
> mace gripped in one hand and a heavy crossbow slung across his
> back. Cracking his knuckles, head tilted, leering with cruel
> anticipation. Painterly fantasy character portrait, three-quarter
> view, isolated against a transparent background, suitable for a
> 256-pixel circular token. Human, any non-good. Mood: imposing
> brute, enjoys his work.

#### Bandits — three variants (Alpha / Beta / Gamma)

The encounter places three identical-stat bandits as mooks; give each a
slightly different look so the GM can tell them apart at a glance.

**Bandit Alpha** (`bandit-alpha.jpg`):

> A human bandit, male, late twenties, lean and unkempt. Chin-
> length brown hair and a short scruffy beard, sun-browned skin,
> a faint scar across the bridge of his nose. Wearing battered
> dark-brown leather armor over rough commoner clothes, a curved
> scimitar at the hip, a light crossbow slung over the shoulder.
> Standing in a wary half-crouch ready to spring forward. Dim
> tavern firelight. Painterly fantasy character portrait, three-
> quarter view, isolated against a transparent background, suitable
> for a 256-pixel circular token. Mood: opportunistic, jumpy,
> looking for an opening.

**Bandit Beta** (`bandit-beta.jpg`) — *re-roll Alpha with: wheat-blond hair
tied back in a stubby ponytail, no beard, a missing front tooth visible when
his lip pulls back. Keep everything else so the trio feels like a unit.*

**Bandit Gamma** (`bandit-gamma.jpg`) — *re-roll Alpha with: short-cropped
black hair, a thick black beard streaked with grey, a leather eyepatch over
the left eye.*

### 🗺️ Battle map — The Sundered Tavern

> Top-down isometric battle map of a medieval roadside tavern
> interior, mid-day warm interior lighting filtering through narrow
> shuttered windows. Layout: a long oak bar along the east wall
> with a row of pewter mugs and bottles, four round wooden tables
> with stools scattered across the main floor (one stool on its
> side, one knocked-over chair near the door), a heavy wooden
> double-door on the west wall (currently closed), a stone fireplace
> with low burning logs on the north wall, a small staircase
> banking left to right in the southeast leading to upstairs rooms.
> Wooden plank floor with subtle 5-foot grid overlay (faint dark
> lines, not intrusive). Atmosphere: spilled mug on the floor near
> the bar, a few playing cards scattered near one table, smoke
> rising from the fireplace. Painterly fantasy battle-map style,
> suitable for a virtual tabletop, 1400×900 pixels, slight overhead
> camera angle (≈80° from horizontal) so the GM can see floor
> details. No characters, no tokens, no UI overlay.

Negative prompt: `text, signage, character figures, modern objects, electric
lights, glowing portals, fantasy ruins, exterior shots, top-down photo realism`.

<!--ENDTABS-->

---

## Style baseline (applies to every character prompt)

These tokens read best as: **painterly digital fantasy art, three-quarter
front-facing pose from the chest up (or full body for small races), neutral
expression unless noted, isolated against a fully transparent background (PNG
with alpha), suitable for cropping to a 256×256 circular token.** Match the
rim-lighting to each demo's setting (warm firelight for the Warrens, cold
sea-storm for the coastal demos, violet for the Shadowfell, ember-orange for
the Caldera). No frame, no text, no caption.

If your image model accepts negative prompts, append: `--no text, watermark,
signature, frame, busy background, multiple characters, action shot, motion
blur, low quality`.

Recommended aspect ratio: **1:1 (square)**, **1024×1024**, then downscale to
256×256 for the token. Battle maps render at the per-map pixel dimensions
listed in each tab.

## Model-specific notes

- **Midjourney**: append `--ar 1:1 --style raw` for character tokens and the
  map's aspect ratio (e.g. `--ar 14:10`) for the maps. Use `--v 6` or later.
  The "transparent background" hint doesn't actually produce a transparent
  PNG — background-remove in Photoshop / GIMP / `rembg` afterward.
- **DALL·E 3** (ChatGPT or API): paste the prompt verbatim. Ask for "PNG with
  transparent background"; you'll still get a solid background to alpha-key.
- **Stable Diffusion (any UI)**: use a portrait-tuned checkpoint (RealVisXL,
  AnimagineXL, or similar). Add the negative-prompt block. Higher CFG (8–10)
  for tighter prompt adherence. ControlNet OpenPose keeps identical-creature
  variants (the bandits, vampire spawn, fire giants) in a shared pose.
- **Hand-painted look**: append "in the style of Tony DiTerlizzi" (tokens) or
  "in the style of Jared Blando" (maps). Adjust to taste.

## After generation — drop + wire

1. (Optional) Background-remove for a transparent PNG — the tabletop renderer
   crops to a circle either way, so a solid background that matches the token
   colour swatch works fine.
2. Crop to a 1:1 square centered on the head and shoulders.
3. Downscale to 256×256 (the shipped tokens' size). jpg or png both work —
   the seed sets `image_url` to whatever filename you reference.
4. Save to the path listed in the demo's progress table (tokens under
   `app/static/demo/tokens/`, maps under `app/static/demo/maps/`).
5. **Wire it in.** The flagship Sundered Vault tokens are set in
   `app/demo_seed.py seed_tokens()`. The five leveled demos build their
   tokens/maps in `app/demo_campaigns.py::_seed_one()`, which reads an optional
   `image` web-path off each spec entry (default `None` → plain coloured ring).
   To show your art, add that path to the matching spec in `app/demo_campaigns.py`:
   - **Map:** add `"image": "/static/demo/maps/<file>.png"` to the demo's `map` dict.
   - **Player character:** add `"image": "/static/demo/tokens/<file>.jpg"` to the PC's dict in `party`.
   - **NPC token:** add a 4th element to the `npc_tokens` tuple — `(slug, label, color, "/static/demo/tokens/<file>.jpg")`.
6. Bump the version, add a CHANGELOG entry, rebuild the app container. The
   demo's hourly reseed picks up the new images automatically. Then flip the
   matching row in the progress table above from ⬜ to ✅.
