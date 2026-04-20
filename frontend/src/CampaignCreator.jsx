import { useState } from 'react';

export default function CampaignCreator({ onComplete }) {
  const [protagonist, setProtagonist] = useState({
    name: 'Traveler',
    location: 'The Ember & Ash Tavern',
    health: 100,
    gold: 50
  });

  const [npcs, setNpcs] = useState([]);
  const [newNpc, setNewNpc] = useState({ name: '', disposition: 'Neutral', secret: '' });

  const addNpc = () => {
    if (!newNpc.name.trim()) return;
    setNpcs([...npcs, {
      name: newNpc.name,
      disposition: newNpc.disposition,
      secrets_known: newNpc.secret ? [newNpc.secret] : []
    }]);
    setNewNpc({ name: '', disposition: 'Neutral', secret: '' });
  };

  const removeNpc = (idx) => {
    setNpcs(npcs.filter((_, i) => i !== idx));
  };

  const handleStart = async () => {
    try {
      const payload = {
        campaign_id: 'default_campaign',
        player_name: protagonist.name,
        starting_health: protagonist.health,
        starting_gold: protagonist.gold,
        starting_location: protagonist.location,
        npcs: npcs,
      };

      const res = await fetch('http://localhost:8000/api/campaign/init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (res.ok) {
        onComplete();
      }
    } catch (e) {
      console.error(e);
      alert('Failed to start campaign. Is backend running?');
    }
  };

  return (
    <div className="min-h-screen bg-fantasy-dark text-fantasy-text font-sans p-8 md:p-16 flex justify-center">
      <div className="max-w-4xl w-full flex flex-col gap-8">
        
        <header className="text-center border-b border-slate-700/50 pb-8">
          <h1 className="text-4xl font-serif text-fantasy-accent mb-2 drop-shadow-md">Forge Your World</h1>
          <p className="text-slate-400 italic font-serif">Define the active cast, relationships, and secrets before the story begins.</p>
        </header>

        <section className="bg-fantasy-panel/40 border border-slate-700/50 rounded-xl p-6 shadow-md backdrop-blur">
           <h2 className="text-xl font-serif text-amber-500 mb-4 border-b border-slate-700/50 pb-2">1. The Protagonist</h2>
           <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Name</label>
                 <input type="text" value={protagonist.name} onChange={e=>setProtagonist({...protagonist, name: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none" />
              </div>
              <div>
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Starting Location</label>
                 <input type="text" value={protagonist.location} onChange={e=>setProtagonist({...protagonist, location: e.target.value})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none" />
              </div>
              <div>
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Starting Health</label>
                 <input type="number" value={protagonist.health} onChange={e=>setProtagonist({...protagonist, health: parseInt(e.target.value)})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none" />
              </div>
              <div>
                 <label className="block text-xs uppercase tracking-widest text-slate-400 mb-1">Starting Gold</label>
                 <input type="number" value={protagonist.gold} onChange={e=>setProtagonist({...protagonist, gold: parseInt(e.target.value)})} className="w-full bg-fantasy-dark border border-slate-600 rounded px-3 py-2 focus:border-fantasy-accent focus:outline-none" />
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
                      {n.secrets_known.length > 0 && <p className="text-xs text-slate-300 italic mt-1">Secret: {n.secrets_known[0]}</p>}
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
