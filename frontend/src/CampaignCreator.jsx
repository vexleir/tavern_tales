import { useEffect, useState } from 'react';

export default function CampaignCreator({ campaignId, onComplete }) {
  const [protagonist, setProtagonist] = useState({
    name: 'Traveler',
    location: 'The Ember & Ash Tavern'
  });

  const [stats, setStats] = useState([{ name: 'Health', value: 100 }, { name: 'Gold', value: 50 }]);
  const [newStat, setNewStat] = useState({ name: '', value: 10 });

  const [inventory, setInventory] = useState(['Rusty Sword']);
  const [newItem, setNewItem] = useState('');

  const [lorebook, setLorebook] = useState([]);
  const [newLore, setNewLore] = useState({ keyword: '', rule: '' });

  const [npcs, setNpcs] = useState([]);
  const [newNpc, setNewNpc] = useState({ name: '', disposition: 'Neutral', secret: '' });

  const [worldPrompt, setWorldPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [storySummary, setStorySummary] = useState('');
  const [worldDescription, setWorldDescription] = useState('');
  const [startingScene, setStartingScene] = useState('');

  // Model configuration (A11)
  const [availableModels, setAvailableModels] = useState([]);
  const [gmModel, setGmModel] = useState('');
  const [utilityModel, setUtilityModel] = useState('');
  const [nsfwWorldGen, setNsfwWorldGen] = useState(false);
  const [submitError, setSubmitError] = useState('');

  useEffect(() => {
    fetch('http://localhost:8000/api/models')
      .then(r => r.json())
      .then(data => {
        setAvailableModels(data);
        const savedGm = localStorage.getItem('tt_preferred_gm');
        const savedUtil = localStorage.getItem('tt_preferred_utility');
        const utilityPreferences = [
          'llama3.1:8b-instruct',
          'llama3.1:8b-instruct:latest',
          'qwen2.5:7b-instruct',
          'qwen2.5:7b-instruct:latest',
          'llama3:8b'
        ];
        if (savedGm && data.includes(savedGm)) setGmModel(savedGm);
        else if (data.length > 0) setGmModel(data[0]);

        if (savedUtil && data.includes(savedUtil)) setUtilityModel(savedUtil);
        else {
          const match = utilityPreferences.find(m => data.includes(m));
          setUtilityModel(match || (data[0] || ''));
        }
      })
      .catch(err => console.error('Model list fetch failed:', err));
  }, []);

  const handleGenerateWorld = async () => {
    if (!worldPrompt.trim()) return;
    setIsGenerating(true);
    try {
       const res = await fetch('http://localhost:8000/api/world/generate', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ prompt: worldPrompt, nsfw: nsfwWorldGen })
       });
       if(res.ok) {
          const data = await res.json();
          if(data.player_starting_location) setProtagonist(p => ({...p, location: data.player_starting_location}));
          if(data.npcs) setNpcs(data.npcs.map(n => ({
             name: n.name,
             disposition: n.disposition,
             secrets_known: n.secrets_known || []
          })));
          if(data.lorebook) setLorebook(data.lorebook);
          if(data.story_summary) setStorySummary(data.story_summary);
          if(data.world_description) setWorldDescription(data.world_description);
          if(data.starting_scene) setStartingScene(data.starting_scene);
       } else {
          const err = await res.json().catch(() => ({detail: res.statusText}));
          let msg;
          if (Array.isArray(err.detail)) {
             msg = err.detail.map(e => {
                const where = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : '';
                return where ? `${where}: ${e.msg}` : e.msg;
             }).join('; ');
          } else if (typeof err.detail === 'string') {
             msg = err.detail;
          } else {
             msg = JSON.stringify(err.detail);
          }
          setSubmitError(`World generation failed (${res.status}): ${msg}`);
       }
    } catch(e) {
       setSubmitError(`World generation failed: ${e.message}`);
    } finally {
       setIsGenerating(false);
    }
  };

  const addNpc = () => {
    if (!newNpc.name.trim()) return;
    setNpcs([...npcs, {
      name: newNpc.name,
      disposition: newNpc.disposition,
      secrets_known: newNpc.secret ? [newNpc.secret] : []
    }]);
    setNewNpc({ name: '', disposition: 'Neutral', secret: '' });
  };

  const removeNpc = (idx) => setNpcs(npcs.filter((_, i) => i !== idx));

  const handleStart = async () => {
    setSubmitError('');
    if (!gmModel) {
      setSubmitError('Select a GM (narrator) model before starting.');
      return;
    }
    try {
      localStorage.setItem('tt_preferred_gm', gmModel);
      if (utilityModel) localStorage.setItem('tt_preferred_utility', utilityModel);

      const payload = {
        campaign_id: campaignId || `campaign_${Date.now()}`,
        player_name: protagonist.name,
        starting_location: protagonist.location,
        stats: stats.reduce((acc, s) => ({ ...acc, [s.name]: s.value }), {}),
        inventory: inventory,
        npcs: npcs,
        lorebook: lorebook.reduce((acc, l) => ({ ...acc, [l.keyword]: l.rule }), {}),
        story_summary: storySummary,
        world_description: worldDescription,
        starting_scene: startingScene,
        gm_model: gmModel,
        utility_model: utilityModel || null,
        nsfw_world_gen: nsfwWorldGen
      };

      const res = await fetch('http://localhost:8000/api/campaign/init', {
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
      setSubmitError(`Failed to start campaign: ${e.message}. Is the backend running?`);
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

        {/* Model configuration (A11) */}
        <section className="bg-fantasy-panel/40 border border-slate-700/50 rounded-xl p-6 shadow-md backdrop-blur">
          <h2 className="text-xl font-serif text-amber-500 mb-4 border-b border-slate-700/50 pb-2">Models</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Narrator Model (GM)</label>
              <select value={gmModel} onChange={e=>setGmModel(e.target.value)} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm">
                {availableModels.length === 0 && <option value="">(no models found — start Ollama)</option>}
                {availableModels.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <p className="text-xs text-slate-500 mt-1 italic">Generates the narration.</p>
            </div>
            <div>
              <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Utility Model (summary + state extraction)</label>
              <select value={utilityModel} onChange={e=>setUtilityModel(e.target.value)} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm">
                <option value="">(auto — fall back through llama3.1:8b, qwen2.5:7b, …)</option>
                {availableModels.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <p className="text-xs text-slate-500 mt-1 italic">Small instruct model recommended.</p>
            </div>
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm text-slate-300 cursor-pointer select-none">
            <input type="checkbox" checked={nsfwWorldGen} onChange={e=>setNsfwWorldGen(e.target.checked)} className="accent-amber-500" />
            Use uncensored creative model for world generation (NSFW)
          </label>
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
           <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              <div>
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Name</label>
                 <input type="text" value={protagonist.name} onChange={e=>setProtagonist({...protagonist, name: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm" />
              </div>
              <div>
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Starting Location</label>
                 <input type="text" value={protagonist.location} onChange={e=>setProtagonist({...protagonist, location: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm" />
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
                <div key={idx} className="bg-fantasy-dark/60 border border-slate-600 rounded p-4 flex justify-between items-center group shadow-sm">
                   <div>
                      <h4 className="font-serif text-amber-400 text-lg">{n.name} <span className="text-sm font-sans text-slate-400 ml-2">Disposition: {n.disposition}</span></h4>
                      {n.secrets_known && n.secrets_known.length > 0 && <p className="text-xs text-slate-300 italic mt-1">Secret: {n.secrets_known[0]}</p>}
                   </div>
                   <button onClick={() => removeNpc(idx)} className="text-red-400 hover:text-red-300 opacity-0 group-hover:opacity-100 transition text-sm">Remove</button>
                </div>
             ))}
           </div>

           <div className="flex flex-col md:flex-row gap-3 items-end bg-fantasy-dark/30 p-4 rounded border border-dashed border-slate-600">
              <div className="flex-1">
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">NPC Name</label>
                 <input type="text" placeholder="e.g. Elena" value={newNpc.name} onChange={e=>setNewNpc({...newNpc, name: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm" />
              </div>
              <div className="w-32">
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Disposition</label>
                 <select value={newNpc.disposition} onChange={e=>setNewNpc({...newNpc, disposition: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm">
                    <option>Friendly</option>
                    <option>Neutral</option>
                    <option>Suspicious</option>
                    <option>Hostile</option>
                 </select>
              </div>
              <div className="flex-1">
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Secret (Optional)</label>
                 <input type="text" placeholder="e.g. She holds a grudge." value={newNpc.secret} onChange={e=>setNewNpc({...newNpc, secret: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none text-sm" />
              </div>
              <button
                  onClick={addNpc}
                  disabled={!newNpc.name.trim()}
                  className="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded font-semibold transition disabled:opacity-50 text-sm h-[38px]"
              >
                 Add Character
              </button>
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
