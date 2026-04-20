import { useState, useEffect } from 'react'
import CampaignCreator from './CampaignCreator'

function App() {
  const [appMode, setAppMode] = useState('setup');
  const [messages, setMessages] = useState([
    { role: 'gm', content: 'Welcome to Tavern Tales. The hearth is warm, but the shadows are long. What brings you to this place?' }
  ]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [directorMode, setDirectorMode] = useState(false);
  
  const [campaignState, setCampaignState] = useState({
    player: { health: 100, gold: 50, location: 'The Ember & Ash Tavern' },
    npcs: []
  });

  const fetchState = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/state/default_campaign');
      if (res.ok) {
        const data = await res.json();
        setCampaignState(data);
      }
    } catch (e) {
      console.error("Could not fetch state", e);
    }
  };

  useEffect(() => {
    fetchState();
  }, []);

  const handleSend = async (messageOverwrite = null) => {
    if (isStreaming) return;
    
    // If messageOverwrite is provided, we use it (as it might be from a regenerate or edit)
    const userMessage = messageOverwrite 
        ? messageOverwrite 
        : { role: 'player', content: input };
        
    if (!messageOverwrite && !input.trim()) return;

    const newMessages = messageOverwrite ? messages : [...messages, userMessage];
    if (!messageOverwrite) {
      setMessages(newMessages);
      setInput('');
    }
    
    setIsStreaming(true);
    
    // Empty GM message to stream into
    setMessages((prev) => [...prev, { role: 'gm', content: '' }]);

    try {
      const apiMessages = newMessages.map(m => ({
        role: m.role === 'player' ? 'user' : 'assistant',
        content: m.content
      }));

      apiMessages.unshift({
        role: 'system',
        content: 'You are the Game Master in Tavern Tales, a dark fantasy open-world text RPG. The user is a player character. Respond in second-person present tense ("You look around..."). Be atmospheric, evocative, and reactive. Provide options if appropriate, or wait for the player\'s action. It is extremely important that you do NOT write large blocks of internal thinking. Always stay in character.'
      });

      const response = await fetch('http://localhost:8000/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: apiMessages,
          model: 'fluffy/l3-8b-stheno-v3.2:latest',
          turn: newMessages.length
        })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        
        setMessages((prev) => {
          const updated = [...prev];
          const lastIndex = updated.length - 1;
          updated[lastIndex] = { ...updated[lastIndex], content: updated[lastIndex].content + chunk };
          return updated;
        });
      }
      
      // Fetch state after generation is complete to get extracted info
      setTimeout(fetchState, 3000); 
      
    } catch (err) {
      console.error(err);
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1].content += '\n[Connection Error: Please ensure Backend is running on port 8000.]';
        return updated;
      });
    } finally {
      setIsStreaming(false);
    }
  };

  const handleRegenerate = () => {
    // Drop the last GM message
    if (messages.length < 2) return;
    const previousMessages = messages.slice(0, messages.length - 1);
    
    const playerMsg = previousMessages[previousMessages.length - 1];
    if(playerMsg.role === 'player') {
       const historyBeforePlayer = previousMessages.slice(0, previousMessages.length - 1);
       setMessages(historyBeforePlayer); // rewind
       handleSend(playerMsg); // resend it as the "new" message
    }
  };
  
  const handleDelete = (index) => {
     const updated = [...messages];
     updated.splice(index, 1);
     setMessages(updated);
  };

  if (appMode === 'setup') {
    return <CampaignCreator onComplete={() => {
       fetchState();
       setAppMode('play');
    }} />;
  }

  return (
    <div className="min-h-screen flex text-fantasy-text bg-fantasy-dark">
      {/* Sidebar: Cast and Codex */}
      <aside className="w-72 bg-fantasy-panel border-r border-slate-700/50 p-4 hidden md:flex flex-col gap-6 overflow-y-auto">
        <h2 className="text-2xl font-serif text-fantasy-accent font-bold">Tavern Tales Reborn</h2>
        
        {/* Player State Block */}
        <div>
          <h3 className="text-xs uppercase text-fantasy-dim font-bold tracking-widest mb-3 border-b border-slate-700 pb-1">Protagonist</h3>
          <div className="bg-fantasy-dark/40 rounded border border-slate-700/50 p-3 text-sm flex flex-col gap-2 shadow-inner">
             <div className="flex justify-between">
                <span className="text-slate-400">Health:</span>
                <span className={campaignState.player.health < 50 ? 'text-red-400 font-bold' : 'text-emerald-400 font-bold'}>
                    {campaignState.player.health}
                </span>
             </div>
             <div className="flex justify-between">
                <span className="text-slate-400">Gold:</span>
                <span className="text-amber-400 font-semibold">{campaignState.player.gold}</span>
             </div>
             <div>
                <span className="text-slate-400 block text-xs mb-1">Current Location:</span>
                <span className="text-slate-200 italic">{campaignState.player.location}</span>
             </div>
          </div>
        </div>

        {/* NPC Codex Block */}
        <div>
          <h3 className="text-xs uppercase text-fantasy-dim font-bold tracking-widest mb-3 border-b border-slate-700 pb-1">The Cast Codex</h3>
          {(!campaignState.npcs || campaignState.npcs.length === 0) ? (
             <div className="text-xs text-slate-500 italic p-2">No characters encountered yet.</div>
          ) : (
            <div className="flex flex-col gap-3">
              {campaignState.npcs.map((npc, idx) => (
                 <div key={idx} className="bg-fantasy-dark/40 rounded border border-slate-700/50 p-3 text-sm">
                    <div className="font-serif text-fantasy-accent font-bold text-base border-b border-slate-700 pb-1 mb-2">
                       {npc.name}
                    </div>
                    <div className="text-xs text-slate-400 mb-1">
                       Disposition: 
                       <span className="ml-1 text-slate-200">{npc.disposition}</span>
                    </div>
                    {npc.secrets_known && npc.secrets_known.length > 0 && (
                       <div className="mt-2 pt-2 border-t border-slate-700/50">
                          <span className="text-xs text-amber-600 font-bold flex items-center gap-1 mb-1">
                             <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.522 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
                             Secrets / Notes
                          </span>
                          <ul className="list-disc pl-4 text-xs text-slate-300 italic">
                             {npc.secrets_known.map((s, i) => <li key={i}>{s}</li>)}
                          </ul>
                       </div>
                    )}
                 </div>
              ))}
            </div>
          )}
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col h-screen relative">
        <header className="p-4 border-b border-slate-700/50 flex justify-between items-center bg-fantasy-panel/90 backdrop-blur sticky top-0 z-10 shadow-sm">
          <h1 className="font-serif text-xl text-fantasy-accent drop-shadow-sm">The Story</h1>
          <button 
             onClick={() => setDirectorMode(!directorMode)}
             className={`text-sm px-4 py-1.5 rounded transition shadow-sm font-semibold border ${directorMode ? 'bg-amber-600/20 text-amber-500 border-amber-600/50' : 'bg-fantasy-dark text-slate-300 border-slate-600 hover:bg-slate-700'}`}
          >
            {directorMode ? 'Exit Director Mode' : 'Director Mode'}
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4 md:p-8 flex flex-col gap-6 scroll-smooth">
          {messages.map((m, idx) => (
            <div key={idx} className={`flex ${m.role === 'player' ? 'justify-end' : 'justify-start'} group relative`}>
              {directorMode && (
                 <div className="absolute top-[-10px] right-2 bg-fantasy-panel border border-slate-600 rounded flex gap-1 p-1 opacity-0 group-hover:opacity-100 transition shadow-lg z-20">
                    <button onClick={() => handleDelete(idx)} className="text-red-400 hover:bg-slate-700 px-2 py-0.5 rounded text-xs">Delete</button>
                    {m.role === 'gm' && idx === messages.length - 1 && !isStreaming && (
                       <button onClick={handleRegenerate} className="text-amber-400 hover:bg-slate-700 px-2 py-0.5 rounded text-xs">Regenerate</button>
                    )}
                 </div>
              )}
              
              <div className={`max-w-[85%] rounded-xl p-6 font-serif text-[1.1rem] leading-relaxed shadow-md whitespace-pre-wrap ${
                m.role === 'player' 
                  ? 'bg-gradient-to-br from-fantasy-accent/20 to-fantasy-accent/10 border border-fantasy-accent/30 text-amber-50 rounded-br-sm' 
                  : 'bg-fantasy-panel border border-slate-700/50 text-slate-200 rounded-bl-sm drop-shadow-lg'
              }`}>
                {m.content}
              </div>
            </div>
          ))}
          {isStreaming && <div className="text-sm text-amber-600/70 italic animate-pulse font-serif px-2">The storyteller is weaving the thread...</div>}
        </div>

        <div className="p-4 bg-fantasy-panel border-t border-slate-700/50 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)]">
          <div className="max-w-4xl mx-auto flex gap-3">
            <input 
              type="text" 
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              disabled={isStreaming}
              placeholder="Describe your next action..." 
              className="flex-1 bg-fantasy-dark border border-slate-600 rounded-lg px-5 py-4 focus:outline-none focus:border-fantasy-accent text-fantasy-text focus:ring-2 focus:ring-fantasy-accent/50 transition shadow-inner placeholder:text-slate-500 font-serif text-lg"
            />
            <button 
              onClick={() => handleSend(null)}
              disabled={isStreaming || !input.trim()}
              className="bg-gradient-to-b from-fantasy-accent to-amber-700 hover:from-amber-600 hover:to-amber-800 text-white px-8 py-4 rounded-lg font-bold tracking-wide transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed uppercase text-sm"
            >
              Commit
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
