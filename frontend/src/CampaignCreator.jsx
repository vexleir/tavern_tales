import { useEffect, useState } from 'react';
import { apiFetch, describeApiError, parseErrorResponse } from './lib/api';

function buildInitialSetup(draft) {
  const seed = draft?.campaignSeed || {};
  const globalContext = draft?.preferenceSnapshot?.globalContext || {};
  const seedLorebook = seed.lorebook && typeof seed.lorebook === 'object'
    ? Object.entries(seed.lorebook).map(([keyword, rule]) => ({ keyword, rule: String(rule) }))
    : [];
  return {
    protagonist: {
      name: 'Traveler',
      location: 'The Ember & Ash Tavern',
      gender: globalContext.gender || 'Unspecified',
      appearance: '',
      description: draft ? [
        globalContext.orientation ? `Orientation: ${globalContext.orientation}` : '',
        globalContext.relationshipStyle ? `Relationship style: ${globalContext.relationshipStyle}` : '',
        seed.protagonistGuidance
      ].filter(Boolean).join('\n') : ''
    },
    worldPrompt: draft?.seedPrompt || '',
    storySummary: draft?.synopsis || draft?.title || '',
    worldDescription: draft ? [
      seed.worldConcept,
      draft.synopsis,
      draft.content
    ].filter(Boolean).join('\n\n') : '',
    startingScene: seed.startingScene || draft?.synopsis || '',
    lorebook: draft ? [
      ...seedLorebook,
      { keyword: 'SavedFantasyDraft', rule: `Campaign setup was seeded from saved fantasy draft ${draft.id} at profile version ${draft.createdFromProfileVersion}.` },
      { keyword: 'ConsentBoundary', rule: 'Fantasy preference data guides fictional roleplay only and must not be treated as real-world consent.' }
    ] : []
  };
}

function buildPreferenceContext(draft) {
  if (!draft?.preferenceSnapshot) return {};
  const snapshot = draft.preferenceSnapshot;
  return {
    enabled: true,
    source: 'saved_fantasy',
    profile_id: snapshot.profileId || draft.ownerProfileId || '',
    profile_version: snapshot.profileVersion ?? draft.createdFromProfileVersion ?? null,
    draft_id: draft.id || '',
    draft_title: draft.title || '',
    selected_themes: snapshot.selectedThemes || [],
    fantasy_only_theme_ids: snapshot.fantasyOnlyThemeIds || [],
    real_world_hard_no_theme_ids: snapshot.realWorldHardNoThemeIds || [],
    global_context: snapshot.globalContext || {},
    safety_principle: 'Fantasy interest is not real-world consent.'
  };
}

export default function CampaignCreator({ campaignId, initialFantasyDraft, onComplete }) {
  const initialSetup = useState(() => buildInitialSetup(initialFantasyDraft))[0];
  const [protagonist, setProtagonist] = useState(initialSetup.protagonist);

  const [stats, setStats] = useState([{ name: 'Health', value: 100 }, { name: 'Gold', value: 50 }]);
  const [newStat, setNewStat] = useState({ name: '', value: 10 });

  const [inventory, setInventory] = useState(['Rusty Sword']);
  const [newItem, setNewItem] = useState('');

  const [lorebook, setLorebook] = useState(initialSetup.lorebook);
  const [newLore, setNewLore] = useState({ keyword: '', rule: '' });

  const [npcs, setNpcs] = useState([]);
  const [newNpc, setNewNpc] = useState({
    name: '',
    disposition: 'Neutral',
    gender: 'Unspecified',
    appearance: '',
    description: '',
    secret: ''
  });

  const [worldPrompt, setWorldPrompt] = useState(initialSetup.worldPrompt);
  const [isGenerating, setIsGenerating] = useState(false);
  const [storySummary, setStorySummary] = useState(initialSetup.storySummary);
  const [worldDescription, setWorldDescription] = useState(initialSetup.worldDescription);
  const [startingScene, setStartingScene] = useState(initialSetup.startingScene);

  // Model configuration (A11)
  const [availableModels, setAvailableModels] = useState([]);
  const [gmModel, setGmModel] = useState('');
  const [utilityModel, setUtilityModel] = useState('');
  const [gmFilter, setGmFilter] = useState('');
  const [utilityFilter, setUtilityFilter] = useState('');
  const [submitError, setSubmitError] = useState('');

  useEffect(() => {
    try {
      window.localStorage?.removeItem('tt_preferred_gm');
      window.localStorage?.removeItem('tt_preferred_utility');
    } catch {
      // Privacy mode or disabled storage: nothing to clear.
    }

    apiFetch('/api/models')
      .then(r => r.json())
      .then(data => {
        setAvailableModels(data);
        const utilityPreferences = [
          'llama3.1:8b-instruct',
          'llama3.1:8b-instruct:latest',
          'llama3.1:8b',
          'llama3.1:8b:latest',
          'qwen2.5:7b-instruct',
          'qwen2.5:7b-instruct:latest',
          'qwen2.5:7b',
          'qwen2.5:7b:latest',
          'llama3:8b',
          'llama3:8b:latest',
          'llama3',
          'llama3:latest'
        ];
        const gmChoice = data[0] || '';
        setGmModel(gmChoice);

        const match = utilityPreferences.find(m => data.includes(m));
        setUtilityModel(match || '');
      })
      .catch(err => console.error('Model list fetch failed:', err));
  }, []);

  const handleGenerateWorld = async () => {
    if (!worldPrompt.trim()) return;
    if (availableModels.length === 0) {
      setSubmitError('No models found — make sure Ollama is running and you have pulled at least one model (e.g. ollama pull llama3.1:8b-instruct).');
      return;
    }
    setSubmitError('');
    setIsGenerating(true);
    try {
       const res = await apiFetch('/api/world/generate', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({
             prompt: worldPrompt,
             nsfw: false,
             gm_model: gmModel || null,
             utility_model: utilityModel || null
          })
       });
       if(res.ok) {
          const data = await res.json();
          setProtagonist(p => ({
            ...p,
            location: data.player_starting_location || p.location,
            gender: data.player_gender || p.gender,
            appearance: data.player_appearance || p.appearance,
            description: data.player_description || p.description
          }));
          if(data.npcs) setNpcs(data.npcs.map(n => ({
             name: n.name,
             disposition: n.disposition,
             gender: n.gender || 'Unspecified',
             appearance: n.appearance || '',
             description: n.description || '',
             secrets_known: n.secrets_known || []
          })));
          if(data.lorebook) setLorebook(data.lorebook);
          if(data.story_summary) setStorySummary(data.story_summary);
          if(data.world_description) setWorldDescription(data.world_description);
          if(data.starting_scene) setStartingScene(data.starting_scene);
       } else {
          const msg = await parseErrorResponse(res);
          setSubmitError(`World generation failed (${res.status}): ${msg}`);
       }
    } catch(e) {
       setSubmitError(`World generation failed: ${describeApiError(e)}`);
    } finally {
       setIsGenerating(false);
    }
  };

  const handleGmModelChange = (value) => {
    setGmModel(value);
  };

  const handleUtilityModelChange = (value) => {
    setUtilityModel(value);
  };

  const addNpc = () => {
    if (!newNpc.name.trim()) return;
    setNpcs([...npcs, {
      name: newNpc.name,
      disposition: newNpc.disposition,
      gender: newNpc.gender,
      appearance: newNpc.appearance,
      description: newNpc.description,
      secrets_known: newNpc.secret ? [newNpc.secret] : []
    }]);
    setNewNpc({ name: '', disposition: 'Neutral', gender: 'Unspecified', appearance: '', description: '', secret: '' });
  };

  const removeNpc = (idx) => setNpcs(npcs.filter((_, i) => i !== idx));

  const handleStart = async () => {
    setSubmitError('');
    if (!gmModel) {
      setSubmitError('Select a GM (narrator) model before starting.');
      return;
    }
    try {
      const payload = {
        campaign_id: campaignId || `campaign_${Date.now()}`,
        player_name: protagonist.name,
        starting_location: protagonist.location,
        player_gender: protagonist.gender || 'Unspecified',
        player_appearance: protagonist.appearance || '',
        player_description: protagonist.description || '',
        stats: stats.reduce((acc, s) => ({ ...acc, [s.name]: s.value }), {}),
        inventory: inventory,
        npcs: npcs,
        lorebook: lorebook.reduce((acc, l) => ({ ...acc, [l.keyword]: l.rule }), {}),
        story_summary: storySummary,
        world_description: worldDescription,
        starting_scene: startingScene,
        preference_context: buildPreferenceContext(initialFantasyDraft),
        gm_model: gmModel,
        utility_model: utilityModel || null,
        nsfw_world_gen: false
      };

      const res = await apiFetch('/api/campaign/init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        onComplete();
      } else {
        const err = await res.json().catch(() => ({detail: 'unknown'}));
        setSubmitError(`Failed to start campaign: ${err.detail || res.statusText}`);
      }
    } catch (e) {
      setSubmitError(`Failed to start campaign: ${describeApiError(e)}`);
    }
  };

  return (
    <div className="min-h-screen bg-fantasy-dark text-fantasy-text font-sans p-8 md:p-16 flex justify-center">
      <div className="max-w-4xl w-full flex flex-col gap-8">

        <header className="text-center border-b border-slate-700/50 pb-8">
          <h1 className="text-4xl font-serif text-fantasy-accent mb-2 drop-shadow-md">Forge Your World</h1>
          <p className="text-slate-400 italic font-serif">Define the active cast, relationships, and secrets before the story begins.</p>
        </header>

        {submitError && (
          <div className="bg-red-900/40 border border-red-700 rounded p-3 text-red-200 text-sm">
            {submitError}
          </div>
        )}

        {initialFantasyDraft && (
          <section className="bg-emerald-950/30 border border-emerald-800 rounded-lg p-4 text-sm text-emerald-100">
            <div className="font-bold text-emerald-300">Loaded from saved fantasy draft</div>
            <div className="text-emerald-200/80 mt-1">{initialFantasyDraft.title}</div>
            <div className="text-xs text-emerald-300/70 mt-2">Fantasy preferences seed the campaign setup, but they are not real-world consent.</div>
          </section>
        )}

        {/* Model configuration (A11) */}
        <section className="bg-fantasy-panel/40 border border-slate-700/50 rounded-xl p-6 shadow-md backdrop-blur">
          <h2 className="text-xl font-serif text-amber-500 mb-4 border-b border-slate-700/50 pb-2">Models</h2>
          {availableModels.length === 0 && (
            <div className="mb-4 bg-amber-950/40 border border-amber-700 rounded p-3 text-xs text-amber-200">
              No models found — make sure Ollama is running, then pull a model in a terminal:
              <pre className="mt-1 font-mono text-amber-300 text-xs">ollama pull llama3.1:8b-instruct</pre>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Narrator Model (GM)</label>
              {availableModels.length > 4 && (
                <input
                  type="text"
                  value={gmFilter}
                  onChange={e => setGmFilter(e.target.value)}
                  placeholder="Filter models..."
                  className="w-full bg-fantasy-dark border border-slate-600 rounded px-2 py-1 text-xs focus:border-fantasy-accent focus:outline-none mb-1 text-slate-300 placeholder:text-slate-500"
                />
              )}
              <select value={gmModel} onChange={e=>handleGmModelChange(e.target.value)} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm">
                {availableModels.length === 0 && <option value="">(no models found — start Ollama)</option>}
                {availableModels
                  .filter(m => m.toLowerCase().includes(gmFilter.toLowerCase()))
                  .map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <p className="text-xs text-slate-500 mt-1 italic">The AI that writes your story. Larger models = richer narration.</p>
            </div>
            <div>
              <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Utility Model (summary + state extraction)</label>
              {availableModels.length > 4 && (
                <input
                  type="text"
                  value={utilityFilter}
                  onChange={e => setUtilityFilter(e.target.value)}
                  placeholder="Filter models..."
                  className="w-full bg-fantasy-dark border border-slate-600 rounded px-2 py-1 text-xs focus:border-fantasy-accent focus:outline-none mb-1 text-slate-300 placeholder:text-slate-500"
                />
              )}
              <select value={utilityModel} onChange={e=>handleUtilityModelChange(e.target.value)} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm">
                <option value="">(auto — falls back through llama3.1:8b → qwen2.5:7b → mistral)</option>
                {availableModels
                  .filter(m => m.toLowerCase().includes(utilityFilter.toLowerCase()))
                  .map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <p className="text-xs text-slate-500 mt-1 italic">Used for world generation, summaries, and state tracking. Leave on auto if unsure — or pick the same model as the Narrator.</p>
            </div>
          </div>
        </section>

        {/* World Generation */}
        <section className="bg-fantasy-panel/40 border border-slate-700/50 rounded-xl p-6 shadow-md backdrop-blur">
           <h2 className="text-xl font-serif text-amber-500 mb-4 border-b border-slate-700/50 pb-2">Auto-Forge World (AI)</h2>
           <div className="flex flex-col md:flex-row gap-3 items-start">
             <textarea
                value={worldPrompt}
                onChange={e=>setWorldPrompt(e.target.value)}
                placeholder="Describe your world... (e.g. 'A cyberpunk city ruled by vampire corporations', 'A floating island of rogue mages')"
                className="flex-1 w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 font-serif focus:border-fantasy-accent focus:outline-none text-sm min-h-[80px]"
             />
             <button
                onClick={handleGenerateWorld}
                disabled={isGenerating || !worldPrompt.trim()}
                className="bg-indigo-700 hover:bg-indigo-600 text-white w-full md:w-auto px-6 py-2 rounded md:h-[80px] font-semibold transition disabled:opacity-50"
             >
                {isGenerating ? 'Dreaming...' : 'Generate World'}
             </button>
           </div>

            <div className="mt-6 flex flex-col gap-4">
               <div>
                  <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">World Description & Lore</label>
                  <textarea
                     value={worldDescription}
                     onChange={e=>setWorldDescription(e.target.value)}
                     placeholder="The expanded history and setting will appear here..."
                     className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 font-serif focus:border-fantasy-accent focus:outline-none text-sm min-h-[120px]"
                  />
               </div>
               <div>
                  <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Starting Scene</label>
                  <textarea
                     value={startingScene}
                     onChange={e=>setStartingScene(e.target.value)}
                     placeholder="The opening hook of your adventure will appear here..."
                     className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 font-serif focus:border-fantasy-accent focus:outline-none text-sm min-h-[80px]"
                  />
               </div>
            </div>
        </section>

        <section className="bg-fantasy-panel/40 border border-slate-700/50 rounded-xl p-6 shadow-md backdrop-blur">
           <h2 className="text-xl font-serif text-amber-500 mb-4 border-b border-slate-700/50 pb-2">1. The Protagonist</h2>
           <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div className="md:col-span-2">
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Name</label>
                 <input type="text" value={protagonist.name} onChange={e=>setProtagonist({...protagonist, name: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm" />
              </div>
              <div>
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Gender</label>
                 <select value={protagonist.gender} onChange={e=>setProtagonist({...protagonist, gender: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm">
                    <option value="Unspecified">Unspecified</option>
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                    <option value="NB">Non-binary</option>
                 </select>
              </div>
           </div>
           <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Starting Location</label>
                 <input type="text" value={protagonist.location} onChange={e=>setProtagonist({...protagonist, location: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm" />
              </div>
           </div>
           <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              <div>
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Appearance</label>
                 <textarea value={protagonist.appearance} onChange={e=>setProtagonist({...protagonist, appearance: e.target.value})} placeholder="Visible traits, build, clothing, distinguishing marks..." className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 font-serif focus:border-fantasy-accent focus:outline-none text-sm min-h-[80px]" />
              </div>
              <div>
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Details (Personality / Backstory)</label>
                 <textarea value={protagonist.description} onChange={e=>setProtagonist({...protagonist, description: e.target.value})} placeholder="Disposition, motivations, history the GM should remember..." className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 font-serif focus:border-fantasy-accent focus:outline-none text-sm min-h-[80px]" />
              </div>
           </div>

           <div className="flex flex-col md:flex-row gap-6 border-t border-slate-700/50 pt-4">
              <div className="flex-1">
                 <h3 className="text-sm font-serif text-amber-400 mb-2">Stats & Attributes</h3>
                 <div className="flex flex-wrap gap-2 mb-3">
                    {stats.map((s, idx) => (
                       <span key={idx} className="bg-fantasy-dark border border-slate-600 rounded px-2 py-1 text-sm flex gap-2 items-center">
                          <span className="text-slate-300">{s.name}:</span>
                          <span className="font-bold text-amber-500">{s.value}</span>
                          <button onClick={() => setStats(stats.filter((_, i) => i !== idx))} className="text-red-400 hover:text-red-300 ml-1">×</button>
                       </span>
                    ))}
                 </div>
                 <div className="flex gap-2">
                    <input type="text" placeholder="e.g. Sanity" value={newStat.name} onChange={e=>setNewStat({...newStat, name: e.target.value})} className="w-24 bg-fantasy-dark border border-slate-600 rounded px-2 py-1 focus:outline-none text-sm" />
                    <input type="number" value={newStat.value} onChange={e=>setNewStat({...newStat, value: parseInt(e.target.value) || 0})} className="w-16 bg-fantasy-dark border border-slate-600 rounded px-2 py-1 focus:outline-none text-sm" />
                    <button onClick={() => { if(newStat.name) setStats([...stats, newStat]); setNewStat({name:'', value: 10}); }} className="bg-slate-700 px-3 py-1 rounded text-sm hover:bg-slate-600">+</button>
                 </div>
              </div>

              <div className="flex-1">
                 <h3 className="text-sm font-serif text-amber-400 mb-2">Starting Inventory</h3>
                 <div className="flex flex-wrap gap-2 mb-3">
                    {inventory.map((item, idx) => (
                       <span key={idx} className="bg-fantasy-dark border border-slate-600 rounded px-2 py-1 text-sm flex gap-2 items-center text-slate-300">
                          {item}
                          <button onClick={() => setInventory(inventory.filter((_, i) => i !== idx))} className="text-red-400 hover:text-red-300 ml-1">×</button>
                       </span>
                    ))}
                 </div>
                 <div className="flex gap-2">
                    <input type="text" placeholder="e.g. Health Potion" value={newItem} onChange={e=>setNewItem(e.target.value)} className="flex-1 bg-fantasy-dark border border-slate-600 rounded px-2 py-1 focus:outline-none text-sm" />
                    <button onClick={() => { if(newItem) setInventory([...inventory, newItem]); setNewItem(''); }} className="bg-slate-700 px-3 py-1 rounded text-sm hover:bg-slate-600">+</button>
                 </div>
              </div>
           </div>
        </section>

        <section className="bg-fantasy-panel/40 border border-slate-700/50 rounded-xl p-6 shadow-md backdrop-blur">
           <h2 className="text-xl font-serif text-amber-500 mb-4 border-b border-slate-700/50 pb-2">2. The Cast & Secrets (Pre-defined NPCs)</h2>

           <div className="flex flex-col gap-4 mb-6">
             {npcs.map((n, idx) => (
                <div key={idx} className="bg-fantasy-dark/60 border border-slate-600 rounded p-4 group shadow-sm">
                   <div className="flex justify-between items-start gap-4">
                      <div className="flex-1">
                         <h4 className="font-serif text-amber-400 text-lg">
                           {n.name}
                           <span className="text-sm font-sans text-slate-400 ml-2">Disposition: {n.disposition}</span>
                           {n.gender && n.gender !== 'Unspecified' && <span className="text-sm font-sans text-slate-400 ml-2">· {n.gender}</span>}
                         </h4>
                         {n.appearance && <p className="text-xs text-slate-300 mt-1"><span className="text-slate-500 uppercase tracking-wider mr-1">Appearance:</span>{n.appearance}</p>}
                         {n.description && <p className="text-xs text-slate-300 mt-1"><span className="text-slate-500 uppercase tracking-wider mr-1">Details:</span>{n.description}</p>}
                         {n.secrets_known && n.secrets_known.length > 0 && <p className="text-xs text-slate-300 italic mt-1">Secret: {n.secrets_known[0]}</p>}
                      </div>
                      <button onClick={() => removeNpc(idx)} className="text-red-400 hover:text-red-300 opacity-0 group-hover:opacity-100 transition text-sm">Remove</button>
                   </div>
                </div>
             ))}
           </div>

           <div className="bg-fantasy-dark/30 p-4 rounded border border-dashed border-slate-600 flex flex-col gap-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                 <div>
                    <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">NPC Name</label>
                    <input type="text" placeholder="e.g. Elena" value={newNpc.name} onChange={e=>setNewNpc({...newNpc, name: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm" />
                 </div>
                 <div>
                    <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Disposition</label>
                    <select value={newNpc.disposition} onChange={e=>setNewNpc({...newNpc, disposition: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm">
                       <option>Friendly</option>
                       <option>Neutral</option>
                       <option>Suspicious</option>
                       <option>Hostile</option>
                    </select>
                 </div>
                 <div>
                    <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Gender</label>
                    <select value={newNpc.gender} onChange={e=>setNewNpc({...newNpc, gender: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm">
                       <option value="Unspecified">Unspecified</option>
                       <option value="M">Male</option>
                       <option value="F">Female</option>
                       <option value="NB">Non-binary</option>
                    </select>
                 </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                 <div>
                    <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Appearance</label>
                    <textarea placeholder="Visible traits, clothing, distinguishing marks..." value={newNpc.appearance} onChange={e=>setNewNpc({...newNpc, appearance: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm min-h-[60px]" />
                 </div>
                 <div>
                    <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Details</label>
                    <textarea placeholder="Personality, role, history..." value={newNpc.description} onChange={e=>setNewNpc({...newNpc, description: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm min-h-[60px]" />
                 </div>
              </div>
              <div className="flex flex-col md:flex-row gap-3 items-end">
                 <div className="flex-1 w-full">
                    <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Secret (Optional)</label>
                    <input type="text" placeholder="e.g. She holds a grudge." value={newNpc.secret} onChange={e=>setNewNpc({...newNpc, secret: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm" />
                 </div>
                 <button
                     onClick={addNpc}
                     disabled={!newNpc.name.trim()}
                     className="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded font-semibold transition disabled:opacity-50 text-sm h-[38px] w-full md:w-auto"
                 >
                    Add Character
                 </button>
              </div>
           </div>
        </section>

        <section className="bg-fantasy-panel/40 border border-slate-700/50 rounded-xl p-6 shadow-md backdrop-blur">
           <h2 className="text-xl font-serif text-amber-500 mb-4 border-b border-slate-700/50 pb-2">3. The Lorebook</h2>
           <p className="text-xs text-slate-400 mb-4">Define absolute rules for the world. The full lorebook is included in every turn — keywords are for your own organization.</p>

           <div className="flex flex-col gap-3 mb-4">
              {lorebook.map((l, idx) => (
                 <div key={idx} className="flex gap-2 items-center bg-fantasy-dark/60 p-2 rounded border border-slate-600">
                    <span className="text-amber-500 font-bold bg-slate-800 px-2 rounded text-sm">[{l.keyword}]</span>
                    <span className="text-slate-300 text-sm flex-1">{l.rule}</span>
                    <button onClick={() => setLorebook(lorebook.filter((_, i) => i !== idx))} className="text-red-400 hover:text-red-300 px-2 text-xl">×</button>
                 </div>
              ))}
           </div>

           <div className="flex flex-col md:flex-row gap-3 items-end bg-fantasy-dark/30 p-4 rounded border border-dashed border-slate-600">
              <div className="w-48">
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Keyword</label>
                 <input type="text" placeholder="e.g. Magic" value={newLore.keyword} onChange={e=>setNewLore({...newLore, keyword: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm" />
              </div>
              <div className="flex-1">
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Rule / Enforcement</label>
                 <input type="text" placeholder="e.g. Magic is extremely illegal and heavily punished." value={newLore.rule} onChange={e=>setNewLore({...newLore, rule: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm" />
              </div>
              <button
                  onClick={() => { if(newLore.keyword) setLorebook([...lorebook, newLore]); setNewLore({keyword:'', rule:''}); }}
                  disabled={!newLore.keyword.trim()}
                  className="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded font-semibold transition disabled:opacity-50 text-sm h-[38px]"
              >
                 Add Rule
              </button>
           </div>
        </section>

        <div className="flex justify-center mt-4 pb-12">
           <button
             onClick={handleStart}
             className="bg-gradient-to-b from-fantasy-accent to-amber-700 hover:from-amber-600 hover:to-amber-800 text-white px-12 py-4 rounded-xl font-bold tracking-widest uppercase shadow-lg transition transform hover:scale-[1.02]"
           >
             Begin Adventure
           </button>
        </div>

      </div>
    </div>
  );
}
