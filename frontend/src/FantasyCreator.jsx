import { useEffect, useMemo, useState } from 'react';
import { apiFetch, describeApiError, parseErrorResponse } from './lib/api';

const ARCHETYPES = [
  { value: 'romantic', label: 'Romantic', summary: 'Sensual and intimate. Emotional connection over intensity.' },
  { value: 'playful', label: 'Playful', summary: 'Fun, teasing, light-hearted. Roleplay as flirtation.' },
  { value: 'power_exchange', label: 'Power Exchange', summary: 'Dominant/submissive dynamic. Authority and surrender as scene texture.' },
  { value: 'taboo_light', label: 'Taboo (Light)', summary: 'Forbidden or secret-feeling scenarios. Mild transgression as fiction.' },
  { value: 'cnc', label: 'Consensual Non-Consent', summary: 'Resistance played as fiction. Both partners consented in advance.' },
  { value: 'dark', label: 'Dark', summary: 'Psychological intensity, fear-as-play, deeper emotional stakes.' },
];

const SETTINGS = [
  { value: 'domestic', label: 'Domestic' },
  { value: 'professional', label: 'Professional' },
  { value: 'fantasy', label: 'Fantasy' },
  { value: 'outdoor', label: 'Outdoor' },
  { value: 'hotel', label: 'Hotel' },
  { value: 'custom', label: 'Custom…' },
];

const TONES = [
  { value: 'tender', label: 'Tender' },
  { value: 'playful', label: 'Playful' },
  { value: 'intense', label: 'Intense' },
  { value: 'serious', label: 'Serious' },
];

const PACINGS = [
  { value: 'slow_burn', label: 'Slow Burn' },
  { value: 'direct', label: 'Direct' },
  { value: 'escalating', label: 'Escalating' },
];

const REQUIRES_ACK = new Set(['cnc', 'dark']);
const PROMINENT_BANNER = new Set(['cnc', 'dark']);
const ELEVATED_BANNER = new Set(['cnc', 'dark', 'power_exchange', 'taboo_light']);

function ConsentBanner({ archetype }) {
  const prominent = PROMINENT_BANNER.has(archetype);
  const elevated = ELEVATED_BANNER.has(archetype);
  const cls = prominent
    ? 'bg-red-950/40 border-red-700/60 text-red-100'
    : elevated
      ? 'bg-amber-950/30 border-amber-700/50 text-amber-100'
      : 'bg-slate-800/60 border-slate-600/50 text-slate-200';
  return (
    <div className={`border rounded-lg px-4 py-3 text-sm ${cls}`}>
      <div className="font-bold uppercase tracking-widest text-xs mb-1">Consent Notice</div>
      This is a consensual fantasy between adults. All content represents fictional scenarios both
      partners agreed to enact in advance. Fantasy interest is not real-world consent.
    </div>
  );
}

function StepBadge({ n, active, done }) {
  const cls = done
    ? 'bg-emerald-700 text-white'
    : active
      ? 'bg-fantasy-accent text-white'
      : 'bg-slate-700 text-slate-300';
  return <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${cls}`}>{n}</span>;
}

export default function FantasyCreator({ onBack }) {
  const [step, setStep] = useState(1);
  const [profiles, setProfiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [models, setModels] = useState([]);

  // Step 1
  const [firstProfileId, setFirstProfileId] = useState('');
  const [secondProfileId, setSecondProfileId] = useState('');
  const [aliasA, setAliasA] = useState('');
  const [aliasB, setAliasB] = useState('');

  // Step 2
  const [comparison, setComparison] = useState(null);

  // Step 3
  const [archetype, setArchetype] = useState('romantic');
  const [setting, setSetting] = useState('domestic');
  const [customSetting, setCustomSetting] = useState('');
  const [tone, setTone] = useState('playful');
  const [pacing, setPacing] = useState('slow_burn');
  const [intensityOverride, setIntensityOverride] = useState('');
  const [includeAftercare, setIncludeAftercare] = useState(true);
  const [includeSafeWords, setIncludeSafeWords] = useState(true);
  const [includeDebrief, setIncludeDebrief] = useState(true);
  const [cncAcknowledged, setCncAcknowledged] = useState(false);
  const [model, setModel] = useState('');

  // Step 5
  const [fantasy, setFantasy] = useState(null);
  const [initialTab, setInitialTab] = useState('story');

  const reloadProfiles = async () => {
    try {
      const res = await apiFetch('/api/preference-profiles');
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      setProfiles(await res.json());
    } catch (e) {
      setError(`Could not load profiles: ${describeApiError(e)}`);
    }
  };

  useEffect(() => {
    let cancelled = false;
    apiFetch('/api/preference-profiles')
      .then(async (res) => {
        if (!res.ok) throw new Error(await parseErrorResponse(res));
        return res.json();
      })
      .then((list) => { if (!cancelled) setProfiles(Array.isArray(list) ? list : []); })
      .catch((e) => { if (!cancelled) setError(`Could not load profiles: ${describeApiError(e)}`); });
    apiFetch('/api/models')
      .then(r => r.ok ? r.json() : [])
      .then((list) => { if (!cancelled) setModels(Array.isArray(list) ? list : []); })
      .catch(() => { if (!cancelled) setModels([]); });
    return () => { cancelled = true; };
  }, []);

  const importPartnerProfile = async (file) => {
    if (!file) return;
    setBusy(true); setError('');
    try {
      const payload = JSON.parse(await file.text());
      const isProtected = payload && payload.passwordProtected === true;
      const body = { profile: payload.passwordProtected ? payload : (payload.profile || payload), displayNameSuffix: '(Partner)' };
      if (isProtected) {
        const password = window.prompt('This partner profile is password-protected. Enter the password to import.');
        if (!password) { setBusy(false); return; }
        body.password = password;
      }
      const res = await apiFetch('/api/preference-profiles/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const imported = await res.json();
      await reloadProfiles();
      setSecondProfileId(imported.profileId);
      if (!aliasB) setAliasB(imported.displayName || 'Person B');
    } catch (e) {
      setError(`Could not import partner profile: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const fetchComparison = async () => {
    if (!firstProfileId || !secondProfileId) return;
    setBusy(true); setError('');
    try {
      const res = await apiFetch('/api/compatibility/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ firstProfileId, secondProfileId, context: 'partner' }),
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      setComparison(await res.json());
    } catch (e) {
      setError(`Could not compare profiles: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    setBusy(true); setError(''); setStep(4);
    try {
      const body = {
        firstProfileId,
        secondProfileId,
        save: true,
        questionnaire: {
          archetype,
          setting,
          customSetting: setting === 'custom' ? customSetting : '',
          tone,
          pacing,
          intensityOverride: intensityOverride || null,
          includeAftercare,
          includeSafeWords,
          includeDebrief,
          personAAlias: aliasA || 'Person A',
          personBAlias: aliasB || 'Person B',
          cncAcknowledged,
        },
      };
      if (model) body.model = model;
      const res = await apiFetch('/api/fantasy-creator/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      setFantasy(await res.json());
      setStep(5);
      setInitialTab(REQUIRES_ACK.has(archetype) || ELEVATED_BANNER.has(archetype) ? 'safety' : 'story');
    } catch (e) {
      setError(`Could not generate fantasy: ${describeApiError(e)}`);
      setStep(3);
    } finally {
      setBusy(false);
    }
  };

  const generateVariant = async (direction) => {
    if (!fantasy) return;
    setBusy(true); setError('');
    try {
      const res = await apiFetch('/api/fantasy-creator/generate-variant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fantasyId: fantasy.id, direction, save: true }),
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      setFantasy(await res.json());
      setInitialTab('story');
    } catch (e) {
      setError(`Could not generate variant: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const compatScore = useMemo(() => {
    if (!comparison) return null;
    const matches = comparison.matches?.length || 0;
    const blocked = comparison.blocked?.length || 0;
    const total = matches + blocked;
    return total === 0 ? 0 : Math.round((matches / total) * 100);
  }, [comparison]);

  const archetypePolicy = useMemo(() => {
    if (PROMINENT_BANNER.has(archetype)) return 'prominent';
    if (ELEVATED_BANNER.has(archetype)) return 'elevated';
    return 'standard';
  }, [archetype]);

  const canStep2 = firstProfileId && secondProfileId && firstProfileId !== secondProfileId;
  const canStep3 = canStep2 && comparison && (comparison.matches?.length || 0) > 0;
  const canGenerate = canStep3 && (!REQUIRES_ACK.has(archetype) || cncAcknowledged) && (setting !== 'custom' || customSetting.trim().length > 0);

  return (
    <div className="min-h-screen bg-fantasy-dark text-fantasy-text font-sans">
      <header className="sticky top-0 z-20 bg-fantasy-panel/95 border-b border-slate-700/70 px-5 py-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-serif text-fantasy-accent">Fantasy Creator</h1>
          <p className="text-xs uppercase tracking-widest text-slate-500 mt-1">A consent-aware roleplay scene builder for two</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <StepBadge n={1} active={step === 1} done={step > 1} /><span>Profiles</span>
            <span>›</span>
            <StepBadge n={2} active={step === 2} done={step > 2} /><span>Compatibility</span>
            <span>›</span>
            <StepBadge n={3} active={step === 3} done={step > 3} /><span>Scene</span>
            <span>›</span>
            <StepBadge n={4} active={step === 4} done={step > 4} /><span>Generate</span>
            <span>›</span>
            <StepBadge n={5} active={step === 5} done={false} /><span>Result</span>
          </div>
          <button onClick={onBack} className="bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-200 rounded px-4 py-2 text-sm">Menu</button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-6 flex flex-col gap-5">
        {error && (
          <div className="bg-red-950/40 border border-red-700/60 text-red-100 rounded-lg px-4 py-3 text-sm">
            {error}
          </div>
        )}

        {/* Step 1: profile selection */}
        {step === 1 && (
          <section className="bg-fantasy-panel/60 border border-slate-700/60 rounded-lg p-5 flex flex-col gap-4">
            <h2 className="font-serif text-xl text-amber-400">Step 1 — Choose two profiles</h2>
            <p className="text-sm text-slate-300">
              Pick your own profile and a partner&apos;s. The partner can be someone whose profile
              you&apos;ve already imported, or you can import a fresh export below.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className="flex flex-col gap-2">
                <span className="text-xs uppercase tracking-widest text-slate-400">Your profile</span>
                <select
                  value={firstProfileId}
                  onChange={(e) => {
                    setFirstProfileId(e.target.value);
                    const p = profiles.find(x => x.profileId === e.target.value);
                    if (p && !aliasA) setAliasA(p.displayName || 'Person A');
                  }}
                  className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-fantasy-accent"
                >
                  <option value="">— select —</option>
                  {profiles.map(p => (
                    <option key={p.profileId} value={p.profileId}>{p.displayName} (v{p.profileVersion})</option>
                  ))}
                </select>
                <input
                  value={aliasA}
                  onChange={(e) => setAliasA(e.target.value)}
                  placeholder="Alias for Person A in the scene"
                  className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-fantasy-accent"
                />
              </label>

              <label className="flex flex-col gap-2">
                <span className="text-xs uppercase tracking-widest text-slate-400">Partner&apos;s profile</span>
                <select
                  value={secondProfileId}
                  onChange={(e) => {
                    setSecondProfileId(e.target.value);
                    const p = profiles.find(x => x.profileId === e.target.value);
                    if (p && !aliasB) setAliasB(p.displayName || 'Person B');
                  }}
                  className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-fantasy-accent"
                >
                  <option value="">— select —</option>
                  {profiles.filter(p => p.profileId !== firstProfileId).map(p => (
                    <option key={p.profileId} value={p.profileId}>{p.displayName} (v{p.profileVersion})</option>
                  ))}
                </select>
                <input
                  value={aliasB}
                  onChange={(e) => setAliasB(e.target.value)}
                  placeholder="Alias for Person B in the scene"
                  className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-fantasy-accent"
                />
                <label className="text-xs text-slate-400 mt-1">
                  …or import a new partner profile (.json):
                  <input
                    type="file"
                    accept="application/json"
                    onChange={(e) => importPartnerProfile(e.target.files?.[0])}
                    className="block mt-1 w-full text-xs text-slate-300 file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:bg-slate-700 file:text-slate-200 hover:file:bg-slate-600"
                  />
                </label>
              </label>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => { fetchComparison(); setStep(2); }}
                disabled={!canStep2 || busy}
                className="bg-fantasy-accent hover:bg-amber-600 disabled:opacity-40 text-white rounded px-5 py-2 text-sm font-bold"
              >Next: see compatibility →</button>
            </div>
          </section>
        )}

        {/* Step 2: compatibility */}
        {step === 2 && (
          <section className="bg-fantasy-panel/60 border border-slate-700/60 rounded-lg p-5 flex flex-col gap-4">
            <h2 className="font-serif text-xl text-amber-400">Step 2 — Compatibility</h2>
            {!comparison && <p className="text-sm text-slate-400 italic">Loading…</p>}
            {comparison && (
              <>
                <div className="flex flex-wrap items-center gap-6">
                  <div className="flex flex-col items-center">
                    <div className="text-4xl font-bold text-emerald-400">{compatScore}%</div>
                    <div className="text-xs uppercase tracking-widest text-slate-400">match</div>
                  </div>
                  <div className="flex gap-3 text-sm">
                    <span className="bg-emerald-950/40 border border-emerald-700/40 rounded px-3 py-2">{comparison.matches?.length || 0} matched</span>
                    <span className="bg-amber-950/40 border border-amber-700/40 rounded px-3 py-2">
                      {(comparison.matches || []).filter(m => ['discuss_only', 'maybe', 'soft_no'].includes(m.realWorldWillingness)).length} to discuss first
                    </span>
                    <span className="bg-red-950/40 border border-red-700/40 rounded px-3 py-2">{comparison.blocked?.length || 0} not included</span>
                  </div>
                </div>

                {comparison.matches?.length > 0 && (
                  <div>
                    <h3 className="text-xs uppercase tracking-widest text-slate-400 mb-2">Matched themes (top 5)</h3>
                    <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {comparison.matches.slice(0, 5).map(m => (
                        <li key={m.id} className="bg-fantasy-dark/50 border border-slate-700 rounded px-3 py-2 text-sm">
                          <div className="font-bold text-amber-400">{m.label}</div>
                          <div className="text-xs text-slate-400 mt-1">
                            interest: {m.fantasyInterest} · intensity: {m.intensityPreference} · real-world: {m.realWorldWillingness}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="flex justify-between">
                  <button onClick={() => setStep(1)} className="bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded px-4 py-2 text-sm">← Back</button>
                  <button
                    onClick={() => setStep(3)}
                    disabled={!canStep3}
                    className="bg-fantasy-accent hover:bg-amber-600 disabled:opacity-40 text-white rounded px-5 py-2 text-sm font-bold"
                  >Next: scene questions →</button>
                </div>
              </>
            )}
          </section>
        )}

        {/* Step 3: questionnaire */}
        {step === 3 && (
          <section className="bg-fantasy-panel/60 border border-slate-700/60 rounded-lg p-5 flex flex-col gap-5">
            <h2 className="font-serif text-xl text-amber-400">Step 3 — Scene questions</h2>
            <ConsentBanner archetype={archetype} />

            <div>
              <h3 className="text-xs uppercase tracking-widest text-slate-400 mb-2">Archetype</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {ARCHETYPES.map(a => (
                  <button
                    key={a.value}
                    onClick={() => { setArchetype(a.value); if (!REQUIRES_ACK.has(a.value)) setCncAcknowledged(false); }}
                    className={`text-left rounded border px-3 py-3 transition ${
                      archetype === a.value
                        ? 'bg-fantasy-accent/15 border-fantasy-accent'
                        : 'bg-fantasy-dark/60 border-slate-700 hover:border-slate-500'
                    }`}
                  >
                    <div className="text-sm font-bold text-amber-400">{a.label}</div>
                    <div className="text-xs text-slate-400 mt-1">{a.summary}</div>
                  </button>
                ))}
              </div>
              {REQUIRES_ACK.has(archetype) && (
                <label className="mt-3 flex items-start gap-2 text-sm text-red-100 bg-red-950/40 border border-red-700/60 rounded px-3 py-2">
                  <input type="checkbox" checked={cncAcknowledged} onChange={(e) => setCncAcknowledged(e.target.checked)} className="mt-1 accent-red-500" />
                  <span>I confirm both partners have agreed in advance to enact this archetype, and that any resistance or fear in the scene will be performed roleplay only. Real distress ends the scene immediately.</span>
                </label>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className="flex flex-col gap-1">
                <span className="text-xs uppercase tracking-widest text-slate-400">Setting</span>
                <select value={setting} onChange={(e) => setSetting(e.target.value)} className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm">
                  {SETTINGS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
                {setting === 'custom' && (
                  <input
                    value={customSetting}
                    onChange={(e) => setCustomSetting(e.target.value)}
                    placeholder="Describe the setting…"
                    className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm mt-1"
                  />
                )}
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs uppercase tracking-widest text-slate-400">Tone</span>
                <select value={tone} onChange={(e) => setTone(e.target.value)} className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm">
                  {TONES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs uppercase tracking-widest text-slate-400">Pacing</span>
                <select value={pacing} onChange={(e) => setPacing(e.target.value)} className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm">
                  {PACINGS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs uppercase tracking-widest text-slate-400">Intensity ceiling (override)</span>
                <select value={intensityOverride} onChange={(e) => setIntensityOverride(e.target.value)} className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm">
                  <option value="">— use merged default —</option>
                  <option value="light">Light</option>
                  <option value="moderate">Moderate</option>
                  <option value="intense">Intense</option>
                </select>
              </label>
            </div>

            <div>
              <h3 className="text-xs uppercase tracking-widest text-slate-400 mb-2">Safety options</h3>
              <div className="flex flex-col gap-2 text-sm">
                <label className="flex items-center gap-2"><input type="checkbox" checked={includeAftercare} onChange={(e) => setIncludeAftercare(e.target.checked)} className="accent-amber-500" />Include aftercare guide</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={includeSafeWords} onChange={(e) => setIncludeSafeWords(e.target.checked)} disabled={archetypePolicy === 'prominent'} className="accent-amber-500" />Include safe word recommendations {archetypePolicy === 'prominent' && <span className="text-xs text-red-300">(required for this archetype)</span>}</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={includeDebrief} onChange={(e) => setIncludeDebrief(e.target.checked)} className="accent-amber-500" />Include post-scene debrief template</label>
              </div>
            </div>

            {models.length > 0 && (
              <label className="flex flex-col gap-1">
                <span className="text-xs uppercase tracking-widest text-slate-400">Generation model (optional)</span>
                <select value={model} onChange={(e) => setModel(e.target.value)} className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm">
                  <option value="">— default (NSFW creative) —</option>
                  {models.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </label>
            )}

            <div className="flex justify-between">
              <button onClick={() => setStep(2)} className="bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded px-4 py-2 text-sm">← Back</button>
              <button
                onClick={generate}
                disabled={!canGenerate || busy}
                className="bg-fantasy-accent hover:bg-amber-600 disabled:opacity-40 text-white rounded px-5 py-2 text-sm font-bold"
              >Generate fantasy →</button>
            </div>
          </section>
        )}

        {/* Step 4: loading */}
        {step === 4 && (
          <section className="bg-fantasy-panel/60 border border-slate-700/60 rounded-lg p-8 flex flex-col items-center gap-4">
            <h2 className="font-serif text-xl text-amber-400">Generating…</h2>
            <p className="text-sm text-slate-400 italic">
              Building compatibility checklist · crafting roles and setting · writing the script · adding finishing touches…
            </p>
            <div className="w-full max-w-xs h-2 bg-slate-800 rounded overflow-hidden">
              <div className="h-full bg-fantasy-accent animate-pulse" style={{ width: '60%' }}></div>
            </div>
          </section>
        )}

        {/* Step 5: output */}
        {step === 5 && fantasy && (
          <FantasyOutput
            fantasy={fantasy}
            onBack={() => setStep(3)}
            onVariant={generateVariant}
            busy={busy}
            initialTab={initialTab}
          />
        )}
      </main>
    </div>
  );
}

function FantasyOutput({ fantasy, onBack, onVariant, busy, initialTab = 'story' }) {
  const [tab, setTab] = useState(initialTab);
  const archetype = fantasy.archetype || fantasy.sceneQuestionnaire?.archetype || 'romantic';
  const requiresProminent = PROMINENT_BANNER.has(archetype);
  const requiresElevated = ELEVATED_BANNER.has(archetype);
  const mustDiscussCount = (fantasy.negotiationChecklist || []).filter(n => n.priority === 'must_discuss').length;

  const tabs = [
    { id: 'story', label: 'Story' },
    ...(requiresElevated ? [{ id: 'aftercare', label: 'Aftercare', highlight: true }] : []),
    { id: 'roles', label: 'Roles' },
    { id: 'script', label: 'Script' },
    { id: 'prep', label: 'Prep' },
    { id: 'safety', label: `Safety${mustDiscussCount > 0 ? ` (${mustDiscussCount})` : ''}` },
    ...(!requiresElevated ? [{ id: 'aftercare', label: 'Aftercare' }] : []),
  ];

  return (
    <section className="bg-fantasy-panel/60 border border-slate-700/60 rounded-lg p-5 flex flex-col gap-4">
      <div className="flex justify-between items-start gap-3 flex-wrap">
        <div>
          <h2 className="font-serif text-2xl text-amber-400">{fantasy.title}</h2>
          {fantasy.compatibilityScore !== null && fantasy.compatibilityScore !== undefined && (
            <p className="text-xs text-slate-400 uppercase tracking-widest mt-1">
              Compatibility {Math.round((fantasy.compatibilityScore || 0) * 100)}% · archetype: {archetype}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={onBack} className="bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm">Edit Scene</button>
          <button onClick={() => onVariant('lighter')} disabled={busy} className="bg-emerald-900/40 hover:bg-emerald-800/60 disabled:opacity-40 border border-emerald-700/50 rounded px-3 py-2 text-sm">Lighter Variant</button>
          <button onClick={() => onVariant('darker')} disabled={busy} className="bg-red-900/40 hover:bg-red-800/60 disabled:opacity-40 border border-red-700/50 rounded px-3 py-2 text-sm">Darker Variant</button>
          <button onClick={() => window.print()} className="bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm">Print</button>
        </div>
      </div>

      <ConsentBanner archetype={archetype} />

      <div className="flex flex-wrap gap-1 border-b border-slate-700">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm border-b-2 transition ${
              tab === t.id
                ? 'border-fantasy-accent text-amber-400'
                : t.highlight
                  ? 'border-transparent text-amber-300 hover:text-amber-200'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >{t.label}</button>
        ))}
      </div>

      {tab === 'story' && (
        <div className="prose prose-invert max-w-none">
          <p className="text-sm text-slate-300 italic">{fantasy.synopsis}</p>
          <div className="text-sm text-slate-200 whitespace-pre-line mt-3">{fantasy.content}</div>
        </div>
      )}

      {tab === 'roles' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {(fantasy.roles || []).map((r, idx) => (
            <div key={idx} className="bg-fantasy-dark/50 border border-slate-700 rounded-lg p-4">
              <div className="text-xs uppercase tracking-widest text-slate-400">{r.personAlias}</div>
              <h3 className="font-bold text-amber-400 text-lg mt-1">{r.roleName}</h3>
              {r.powerPosition && (
                <div className="inline-block mt-2 text-xs uppercase tracking-widest bg-slate-800 border border-slate-600 rounded px-2 py-0.5">{r.powerPosition}</div>
              )}
              {r.characterDescription && <p className="text-sm text-slate-300 mt-3">{r.characterDescription}</p>}
              {r.guidance && (
                <div className="mt-3 text-sm text-slate-200 bg-slate-900/40 border border-slate-700/60 rounded p-3">
                  <div className="text-xs uppercase tracking-widest text-slate-400 mb-1">How to play</div>
                  {r.guidance}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === 'script' && (
        <div className="flex flex-col gap-4">
          {(fantasy.scriptPhases || []).map((phase, idx) => (
            <div key={idx} className="bg-fantasy-dark/50 border border-slate-700 rounded-lg p-4">
              <div className="flex items-baseline justify-between">
                <h3 className="font-bold text-amber-400">{phase.phaseName}</h3>
                <div className="text-xs uppercase tracking-widest text-slate-500">{phase.phaseType}</div>
              </div>
              <ol className="mt-3 flex flex-col gap-2 text-sm">
                {phase.lines.map((line, lidx) => {
                  if (line.lineType === 'safe_word_check') {
                    return (
                      <li key={lidx} className="bg-amber-950/40 border-l-4 border-amber-500 pl-3 py-2 text-amber-100 italic">
                        ⚑ {line.text}
                      </li>
                    );
                  }
                  return (
                    <li key={lidx} className="flex gap-2">
                      <span className="text-xs uppercase tracking-widest text-slate-500 min-w-[80px]">{line.speaker}</span>
                      <span className={line.lineType === 'action' ? 'italic text-slate-400' : 'text-slate-200'}>
                        {line.lineType === 'action' || line.lineType === 'direction' ? `(${line.text})` : line.text}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </div>
          ))}
          {(fantasy.scriptPhases || []).length === 0 && (
            <p className="text-sm text-slate-400 italic">No script phases were generated.</p>
          )}
        </div>
      )}

      {tab === 'prep' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <h3 className="text-xs uppercase tracking-widest text-slate-400 mb-2">Props</h3>
            {['required', 'nice_to_have', 'advanced'].map(tier => {
              const items = (fantasy.props || []).filter(p => p.tier === tier);
              if (items.length === 0) return null;
              const tierLabel = { required: 'Required', nice_to_have: 'Nice to have', advanced: 'Advanced' }[tier];
              const tierCls = { required: 'text-red-300', nice_to_have: 'text-emerald-300', advanced: 'text-indigo-300' }[tier];
              return (
                <div key={tier} className="mb-3">
                  <div className={`text-xs uppercase tracking-widest ${tierCls}`}>{tierLabel}</div>
                  <ul className="mt-1 flex flex-col gap-1 text-sm">
                    {items.map((p, i) => (
                      <li key={i} className="bg-fantasy-dark/50 border border-slate-700 rounded px-3 py-2">
                        <span className="text-slate-200">{p.item}</span>
                        {p.note && <span className="text-xs text-slate-400 block mt-1">{p.note}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
            {(fantasy.props || []).length === 0 && <p className="text-sm text-slate-400 italic">No props listed.</p>}
          </div>

          <div>
            <h3 className="text-xs uppercase tracking-widest text-slate-400 mb-2">Mood tips</h3>
            {['ambiance', 'sensory', 'timing', 'apparel', 'digital'].map(cat => {
              const items = (fantasy.moodTips || []).filter(m => m.category === cat);
              if (items.length === 0) return null;
              return (
                <div key={cat} className="mb-3">
                  <div className="text-xs uppercase tracking-widest text-slate-400">{cat}</div>
                  <ul className="mt-1 flex flex-col gap-1 text-sm text-slate-200">
                    {items.map((m, i) => <li key={i} className="bg-fantasy-dark/50 border border-slate-700 rounded px-3 py-2">{m.tip}</li>)}
                  </ul>
                </div>
              );
            })}
            {(fantasy.moodTips || []).length === 0 && <p className="text-sm text-slate-400 italic">No mood tips listed.</p>}
          </div>
        </div>
      )}

      {tab === 'safety' && (
        <div className="flex flex-col gap-5">
          {(requiresElevated || requiresProminent) && (
            <div className={`rounded-lg border px-4 py-3 text-sm ${requiresProminent ? 'bg-red-950/40 border-red-700/60 text-red-100' : 'bg-amber-950/40 border-amber-700/60 text-amber-100'}`}>
              <strong>Read this section before starting the scene.</strong> Items marked
              &ldquo;must discuss&rdquo; have been flagged from one or both partners&apos; preferences.
            </div>
          )}
          <div>
            <h3 className="text-xs uppercase tracking-widest text-slate-400 mb-2">Pre-scene negotiation checklist</h3>
            <ol className="flex flex-col gap-2 text-sm">
              {(fantasy.negotiationChecklist || []).map((n, i) => (
                <li key={i} className={`rounded-lg border px-3 py-2 ${
                  n.priority === 'must_discuss'
                    ? 'bg-red-950/30 border-red-700/50'
                    : n.priority === 'recommended'
                      ? 'bg-amber-950/20 border-amber-700/40'
                      : 'bg-fantasy-dark/50 border-slate-700'
                }`}>
                  <div className="flex justify-between items-baseline gap-2">
                    <span className="font-bold text-amber-300">{n.topic}</span>
                    <span className={`text-xs uppercase tracking-widest ${
                      n.priority === 'must_discuss' ? 'text-red-300' : n.priority === 'recommended' ? 'text-amber-300' : 'text-slate-400'
                    }`}>{n.priority.replace('_', ' ')}</span>
                  </div>
                  <p className="text-slate-200 mt-1">{n.question}</p>
                  {n.context && <p className="text-xs text-slate-400 mt-1">{n.context}</p>}
                </li>
              ))}
            </ol>
          </div>

          {(fantasy.safeWordRecommendations || []).length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-widest text-slate-400 mb-2">Safe words</h3>
              <ul className="flex flex-col gap-2 text-sm">
                {fantasy.safeWordRecommendations.map((s, i) => (
                  <li key={i} className="bg-fantasy-dark/50 border border-slate-700 rounded-lg px-3 py-2">
                    <div className="flex gap-2 items-baseline">
                      <span className="font-bold text-amber-300">&ldquo;{s.word}&rdquo;</span>
                      {s.gesture && <span className="text-xs text-slate-400">— {s.gesture}</span>}
                    </div>
                    {s.useCase && <p className="text-slate-200 mt-1">{s.useCase}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {tab === 'aftercare' && (
        <div className="flex flex-col gap-5">
          {['immediate', 'within_hour', 'next_day'].map(timing => {
            const items = (fantasy.aftercareGuide || []).filter(a => a.timing === timing);
            if (items.length === 0) return null;
            const label = { immediate: 'Immediately', within_hour: 'Within the hour', next_day: 'Next day' }[timing];
            return (
              <div key={timing}>
                <h3 className="text-xs uppercase tracking-widest text-slate-400 mb-2">{label}</h3>
                <ul className="flex flex-col gap-2 text-sm">
                  {items.map((a, i) => (
                    <li key={i} className="bg-fantasy-dark/50 border border-slate-700 rounded px-3 py-2 text-slate-200">{a.suggestion}</li>
                  ))}
                </ul>
              </div>
            );
          })}
          {(fantasy.aftercareGuide || []).length === 0 && <p className="text-sm text-slate-400 italic">No aftercare guidance was generated.</p>}

          {(fantasy.debriefTemplate || []).length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-widest text-slate-400 mb-2">Debrief questions</h3>
              <ul className="flex flex-col gap-2 text-sm">
                {fantasy.debriefTemplate.map((d, i) => (
                  <li key={i} className="bg-fantasy-dark/50 border border-slate-700 rounded px-3 py-2">
                    <span className="text-xs uppercase tracking-widest text-slate-500 mr-2">{d.category}</span>
                    <span className="text-slate-200">{d.question}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
