/* Coverage diagnostic — answer "do we have a local working version of
 * this Open5e thing?" for the race / class / subclass on a sheet.
 *
 * Three curated tables ship alongside the sheet, each covering a
 * different mechanical surface:
 *
 *   window._INNATE_DEFENSES   — race / class / subclass → auto-applied
 *                                damage and condition (im)munities.
 *   window._CLASS_RESOURCES   — class / subclass → trackable feature
 *                                counters (Rage, Channel Divinity, …).
 *   window._SUBCLASS_SPELLS   — subclass → always-prepared spell grants
 *                                (Cleric domain spells, Paladin oath
 *                                spells, Circle of the Land circle
 *                                spells, …).
 *
 * Each table covers a different slice; missing coverage in one doesn't
 * mean the race/class is unsupported — most races have no defenses,
 * most classes' resources are PHB-only, etc. So this helper REPORTS
 * coverage rather than blocking on missing entries.
 *
 * Usage from the JS console (open the sheet, then):
 *
 *   Open5eCoverage.inspect()                   // current sheet
 *   Open5eCoverage.inspect(snapshot)           // explicit
 *   Open5eCoverage.summarize()                 // one-line console.log
 *   Open5eCoverage.isCurated('race-defenses', 'tiefling')   // bool
 *
 * The intent is a developer tool — surface coverage gaps so we can
 * grow the curated tables over time. Not user-facing UI (yet).
 */
;(function () {
    function _slug(s) {
        return String(s || '').trim().toLowerCase().replace(/\s+/g, '-');
    }

    // Build coverage predicates lazily so the file loads regardless of
    // which curated tables are present on the page.
    function _raceDefensesCurated(slug) {
        const map = (window._INNATE_DEFENSES && window._INNATE_DEFENSES.race) || {};
        return !!map[slug];
    }
    function _classDefensesCurated(slug) {
        const map = (window._INNATE_DEFENSES && window._INNATE_DEFENSES.class) || {};
        return !!map[slug];
    }
    function _subclassDefensesCurated(slug) {
        const map = (window._INNATE_DEFENSES && window._INNATE_DEFENSES.subclass) || {};
        return !!map[slug];
    }
    function _classResourcesCurated(slug) {
        const list = window._CLASS_RESOURCES || [];
        return list.some(r => r.class === slug && !r.subclass);
    }
    function _subclassResourcesCurated(slug) {
        const list = window._CLASS_RESOURCES || [];
        return list.some(r => r.subclass === slug);
    }
    function _subclassSpellsCurated(slug) {
        const map = window._SUBCLASS_SPELLS || {};
        return !!map[slug];
    }

    // One-shot probe — pass either a sheet-shaped object
    // ``{race, classes:[{class, subclass, level, _subclass_slug?}, …]}``
    // or omit and we'll synthesize one from the live DOM.
    function _readLiveSheet() {
        const raceInp = document.querySelector('[name="race"]');
        const race = raceInp ? raceInp.value : '';
        let classes = [];
        if (typeof window._mcRoster === 'function') {
            try { classes = window._mcRoster() || []; } catch { classes = []; }
        }
        if (!classes.length) {
            // Fall back to the hidden classes_json textarea
            const ta = document.getElementById('classes-data');
            if (ta) {
                try { classes = JSON.parse(ta.value || '[]') || []; } catch { classes = []; }
            }
        }
        return { race, classes };
    }

    function inspect(sheet) {
        const snap = sheet || _readLiveSheet();
        const out = {
            race: null,
            classes: [],
            subclasses: [],
            missing: [],   // flat list of {kind, slug, label} for easy iteration
        };

        // Race
        const rSlug = _slug(snap.race);
        if (rSlug) {
            const defensesOk = _raceDefensesCurated(rSlug);
            out.race = { slug: rSlug, label: snap.race, defenses: defensesOk };
            if (!defensesOk) out.missing.push({ kind: 'race-defenses', slug: rSlug, label: snap.race });
        }

        // Classes & subclasses
        const roster = Array.isArray(snap.classes) ? snap.classes : [];
        roster.forEach(c => {
            if (!c || !c.class) return;
            const cSlug = _slug(c.class);
            const lvl = parseInt(c.level, 10) || 0;
            const classCov = {
                slug: cSlug,
                label: c.class,
                level: lvl,
                resources: _classResourcesCurated(cSlug),
                defenses: _classDefensesCurated(cSlug),
            };
            out.classes.push(classCov);
            if (!classCov.resources && !classCov.defenses) {
                out.missing.push({ kind: 'class-any', slug: cSlug, label: c.class });
            }

            const subSlug = c._subclass_slug
                ? _slug(c._subclass_slug)
                : _slug(c.subclass);
            if (subSlug) {
                const subCov = {
                    slug: subSlug,
                    label: c.subclass,
                    class_slug: cSlug,
                    level: lvl,
                    spells: _subclassSpellsCurated(subSlug),
                    resources: _subclassResourcesCurated(subSlug),
                    defenses: _subclassDefensesCurated(subSlug),
                };
                out.subclasses.push(subCov);
                if (!subCov.spells && !subCov.resources && !subCov.defenses) {
                    out.missing.push({ kind: 'subclass-any', slug: subSlug, label: c.subclass });
                }
            }
        });

        return out;
    }

    function summarize(sheet) {
        const r = inspect(sheet);
        const lines = [];
        if (r.race) {
            lines.push(`Race: ${r.race.label || r.race.slug} — defenses: ${r.race.defenses ? '✓' : '○ not curated'}`);
        } else {
            lines.push('Race: (none selected)');
        }
        r.classes.forEach(c => {
            const tags = [
                c.resources ? '✓ resources' : '○ resources',
                c.defenses  ? '✓ defenses'  : '○ defenses',
            ];
            lines.push(`Class: ${c.label} Lv ${c.level} — ${tags.join(', ')}`);
        });
        r.subclasses.forEach(s => {
            const tags = [
                s.spells    ? '✓ spells'    : '○ spells',
                s.resources ? '✓ resources' : '○ resources',
                s.defenses  ? '✓ defenses'  : '○ defenses',
            ];
            lines.push(`  Subclass: ${s.label} (${s.slug}) — ${tags.join(', ')}`);
        });
        if (r.missing.length) {
            lines.push(`Missing local coverage (${r.missing.length}): ${r.missing.map(m => `${m.kind}:${m.slug}`).join(', ')}`);
        } else {
            lines.push('All selected items have at least one curated entry.');
        }
        const report = lines.join('\n');
        // Friendly auto-print when called from console.
        console.log(report);
        return report;
    }

    function isCurated(kind, slug) {
        const s = _slug(slug);
        switch (kind) {
            case 'race-defenses':       return _raceDefensesCurated(s);
            case 'class-defenses':      return _classDefensesCurated(s);
            case 'subclass-defenses':   return _subclassDefensesCurated(s);
            case 'class-resources':     return _classResourcesCurated(s);
            case 'subclass-resources':  return _subclassResourcesCurated(s);
            case 'subclass-spells':     return _subclassSpellsCurated(s);
            default:
                console.warn('Open5eCoverage.isCurated: unknown kind', kind,
                    '(expected one of: race-defenses, class-defenses, subclass-defenses, '
                    + 'class-resources, subclass-resources, subclass-spells)');
                return false;
        }
    }

    window.Open5eCoverage = { inspect, summarize, isCurated };

    // Auto-print on every sheet load when the debug flag is set in
    // localStorage. Opt-in so the console stays clean in normal use:
    //
    //   localStorage.setItem('simplevtt_coverage_debug', '1')
    //
    // Refresh the sheet to see the coverage report on every load.
    try {
        if (typeof localStorage !== 'undefined'
            && localStorage.getItem('simplevtt_coverage_debug') === '1') {
            const _run = () => {
                // Wait a tick so _mcRoster() is wired by sheet.js.
                setTimeout(() => {
                    console.groupCollapsed('Open5eCoverage report');
                    summarize();
                    console.groupEnd();
                }, 200);
            };
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', _run, { once: true });
            } else {
                _run();
            }
        }
    } catch { /* localStorage unavailable */ }
})();
