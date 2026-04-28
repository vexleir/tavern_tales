import { useState } from 'react';

const TABS = ['Getting Started', 'Models', 'How to Play', 'Director Mode', 'Lorebook & Cast', 'Preference Profiles'];

const content = {
  'Getting Started': (
    <div className="space-y-4 text-sm text-slate-300">
      <p className="text-slate-200 font-semibold">Before you can play, you need three things running:</p>
      <ol className="list-decimal list-inside space-y-2">
        <li>
          <span className="text-amber-400 font-semibold">Ollama</span> — the local AI engine.
          Download from <span className="font-mono text-slate-400">https://ollama.com/download</span> and install it.
        </li>
        <li>
          <span className="text-amber-400 font-semibold">A language model</span> — pulled via Ollama.
          Open any terminal and run:
          <pre className="mt-1 bg-fantasy-dark rounded p-2 font-mono text-xs text-emerald-300">ollama pull llama3.1:8b-instruct</pre>
          Any 7–8B instruct model works. The same model can be used for both Narrator and Utility roles.
        </li>
        <li>
          <span className="text-amber-400 font-semibold">The backend server</span> — must be running on port 8000.
          If you see API errors, check that <span className="font-mono text-xs">python -m uvicorn main:app --reload --port 8000</span> is running in the <span className="font-mono text-xs">backend/</span> folder.
        </li>
      </ol>
      <p className="text-slate-400 italic text-xs">See README.md in the project root for a complete install guide.</p>
    </div>
  ),

  'Models': (
    <div className="space-y-4 text-sm text-slate-300">
      <div className="space-y-2">
        <p className="text-amber-400 font-semibold">Narrator Model (GM)</p>
        <p>The main storytelling model. It reads the world state, your action, and dice results, then writes the next beat of the story. A larger, smarter model gives richer narration.</p>
        <p className="text-slate-400 italic">Required. If the dropdown is empty, Ollama is not running or you have no models pulled.</p>
      </div>
      <div className="space-y-2">
        <p className="text-amber-400 font-semibold">Utility Model</p>
        <p>A background model used for three tasks:</p>
        <ul className="list-disc list-inside space-y-1 pl-2 text-slate-400">
          <li>Generating the world when you click "Generate World"</li>
          <li>Summarizing the story every 5 turns (so long campaigns stay coherent)</li>
          <li>Extracting state changes from the GM's responses (stat updates, NPC changes)</li>
        </ul>
        <p className="mt-2">Leave it on <span className="font-mono text-xs">(auto)</span> and it will pick the best available small model automatically — <span className="font-mono text-xs">llama3.1:8b</span>, then <span className="font-mono text-xs">qwen2.5:7b</span>, then <span className="font-mono text-xs">mistral</span>.</p>
        <p className="text-slate-400 italic">If world generation fails with a 400 error, either no Utility model is available or Ollama is not running.</p>
      </div>
      <div className="bg-slate-800/60 rounded p-3 text-xs text-slate-400">
        <span className="text-slate-300 font-semibold">Tip:</span> If in doubt, select the same model for both. A single 8B model handles everything well enough for most sessions.
      </div>
    </div>
  ),

  'How to Play': (
    <div className="space-y-4 text-sm text-slate-300">
      <div className="space-y-2">
        <p className="text-amber-400 font-semibold">The basic loop</p>
        <ol className="list-decimal list-inside space-y-2">
          <li>Type what your character does in the box at the bottom of the screen.</li>
          <li>Press <span className="font-mono text-xs bg-slate-700 px-1 rounded">Enter</span> or click <span className="font-mono text-xs bg-slate-700 px-1 rounded">Commit</span>.</li>
          <li>The GM writes the next beat of the story.</li>
          <li>Repeat.</li>
        </ol>
        <p className="text-slate-400 italic text-xs">Shift+Enter adds a line break without sending your action.</p>
      </div>
      <div className="space-y-2">
        <p className="text-amber-400 font-semibold">Dice checks</p>
        <p>If your action involves risk (attacking, sneaking, persuading, searching), the game rolls a d20 automatically. You don't need to ask for a roll — just describe the action. The result appears as a badge in the header and shapes the GM's response.</p>
        <p className="text-slate-400 italic text-xs">Stat values of 50 = +0 modifier. Each 10 points above or below 50 adds or subtracts 1 from the roll.</p>
      </div>
      <div className="space-y-2">
        <p className="text-amber-400 font-semibold">Post-turn buttons</p>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-slate-800/60 rounded p-2">
            <span className="text-amber-400 font-bold">↻ Reroll</span>
            <p className="text-slate-400 mt-1">Discards the GM's last response and generates a new one from the same player action.</p>
          </div>
          <div className="bg-slate-800/60 rounded p-2">
            <span className="text-emerald-400 font-bold">→ Continue</span>
            <p className="text-slate-400 mt-1">Asks the GM to keep writing without a new player action. Good for cliffhangers.</p>
          </div>
        </div>
      </div>
      <div className="space-y-2">
        <p className="text-amber-400 font-semibold">Quick Actions bar</p>
        <p>Click the <span className="font-mono text-xs bg-slate-700 px-1 rounded">⚡ Actions</span> toggle above the input to open preset action buttons. Each one pre-fills the input with a template you can edit before sending.</p>
      </div>
    </div>
  ),

  'Director Mode': (
    <div className="space-y-4 text-sm text-slate-300">
      <p>Director Mode turns you into a narrator with a GM's toolkit. Toggle it with the <span className="font-mono text-xs bg-slate-700 px-1 rounded">Director Mode</span> button in the top-right of the story screen. The sidebar becomes editable.</p>
      <div className="space-y-3">
        <div>
          <p className="text-amber-400 font-semibold">What you can edit</p>
          <ul className="list-disc list-inside space-y-1 pl-2 text-slate-400 text-xs mt-1">
            <li>Protagonist stats, location, appearance, inventory</li>
            <li>NPC dispositions, appearance, details, and secrets</li>
            <li>Add or remove NPCs entirely</li>
            <li>Lorebook entries (add, edit, remove world rules)</li>
          </ul>
          <p className="text-slate-400 italic text-xs mt-2">All changes take effect on the next GM turn — the prompt is rebuilt from live state every time.</p>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-slate-800/60 rounded p-2">
            <span className="text-slate-200 font-bold">Undo (Ctrl+Z)</span>
            <p className="text-slate-400 mt-1">Reverses the last director edit, including stat and NPC changes.</p>
          </div>
          <div className="bg-amber-900/30 border border-amber-700/40 rounded p-2">
            <span className="text-amber-400 font-bold">Fork Timeline</span>
            <p className="text-slate-400 mt-1">Duplicates the campaign right now. Explore an alternate path without losing the original story.</p>
          </div>
          <div className="bg-slate-800/60 rounded p-2">
            <span className="text-slate-200 font-bold">Inspect Prompt</span>
            <p className="text-slate-400 mt-1">Shows the full system prompt the AI received last turn — useful for debugging why the GM made a choice.</p>
          </div>
          <div className="bg-slate-800/60 rounded p-2">
            <span className="text-slate-200 font-bold">Debug Bundle</span>
            <p className="text-slate-400 mt-1">Exports a full JSON snapshot of campaign state, prompt, and memories.</p>
          </div>
        </div>
        <div>
          <p className="text-amber-400 font-semibold text-xs">Deleting turns</p>
          <p className="text-slate-400 text-xs mt-1">Hover any message in Director Mode to reveal a red Delete button. Deleting a turn removes both the player action and the GM response, and reverses any state changes (stat updates, NPC changes) that the GM extracted from that turn.</p>
        </div>
      </div>
    </div>
  ),

  'Lorebook & Cast': (
    <div className="space-y-4 text-sm text-slate-300">
      <div className="space-y-2">
        <p className="text-amber-400 font-semibold">Lorebook</p>
        <p>A set of <strong>absolute rules the GM must always follow</strong>. Every entry is included in the system prompt on every turn — the GM cannot ignore them.</p>
        <p className="text-slate-400 italic text-xs">Examples: "Magic is fueled by the caster's life force.", "The king is dead — do not resurrect him.", "This world has no gunpowder."</p>
        <p className="text-slate-400 text-xs mt-2">The keyword field is for your own organization. The GM sees the rule text, not the keyword.</p>
      </div>
      <div className="space-y-2">
        <p className="text-amber-400 font-semibold">Cast (NPCs)</p>
        <p>Pre-defined characters in the world. Each NPC's <strong>full profile</strong> — name, disposition, appearance, description, and secrets — is included in every GM prompt.</p>
        <div className="text-xs text-slate-400 space-y-1 mt-1">
          <p><span className="text-slate-300">Disposition:</span> Sets the NPC's attitude toward the protagonist at the start.</p>
          <p><span className="text-slate-300">Secrets:</span> Facts the NPC knows but hasn't shared. The GM can use these to drive drama and revelation.</p>
          <p><span className="text-slate-300">Details:</span> Personality, motivations, backstory the GM should remember.</p>
        </div>
        <p className="text-slate-400 italic text-xs mt-2">Use Director Mode to change dispositions mid-story as relationships evolve.</p>
      </div>
      <div className="bg-slate-800/60 rounded p-3 text-xs text-slate-400">
        <span className="text-slate-300 font-semibold">Token budget note:</span> The Cast section is capped at ~900 tokens and the Lorebook at ~1,200. If you have many NPCs or many lore entries, the GM summarizes the overflow rather than dropping them.
      </div>
    </div>
  ),

  'Preference Profiles': (
    <div className="space-y-4 text-sm text-slate-300">
      <div className="bg-amber-950/30 border border-amber-800/50 rounded p-3 text-xs text-amber-200">
        <strong>Safety note:</strong> Fantasy preferences recorded here are not real-world consent. The system is designed to keep these dimensions clearly separate.
      </div>
      <div className="space-y-2">
        <p className="text-amber-400 font-semibold">What Preference Profiles do</p>
        <p>They let you record your roleplay interests — themes, power dynamics, tone, intensity — in a structured, consent-aware way. Profiles can then <strong>seed a campaign setup</strong> with matching world concepts, NPC dynamics, and lorebook entries.</p>
        <p className="text-slate-400 italic text-xs">A profile doesn't run silently in the background during gameplay. Its influence comes from what it contributed to the campaign setup.</p>
      </div>
      <div className="space-y-1 text-xs text-slate-400">
        <p className="text-slate-300 font-semibold">Key concepts:</p>
        <p><span className="text-slate-300">Fantasy Interest</span> — how interested you are in a theme as fiction.</p>
        <p><span className="text-slate-300">Text Roleplay Willingness</span> — whether you want to actually play it in a session.</p>
        <p><span className="text-slate-300">Fade to Black</span> — tells the GM to skip explicit content and cut to the aftermath.</p>
        <p><span className="text-slate-300">Reality Bridge</span> — an optional space for noting real-world-adjacent interests, kept private unless you choose to share.</p>
        <p><span className="text-slate-300">Fantasy Drafts</span> — AI-generated story concepts based on your profile that can be imported directly into campaign setup.</p>
      </div>
      <p className="text-slate-400 italic text-xs">Access Preference Profiles from the main menu. Profiles are stored locally on your machine.</p>
    </div>
  )
};

export default function HelpModal({ onClose }) {
  const [activeTab, setActiveTab] = useState(TABS[0]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-fantasy-panel border border-slate-600 rounded-lg shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 border-b border-slate-700 flex justify-between items-center flex-shrink-0">
          <h2 className="font-serif text-lg text-fantasy-accent">Help & Guide</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-xl leading-none">✗</button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-4 pt-3 flex-wrap flex-shrink-0 border-b border-slate-700/50 pb-0">
          {TABS.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-1.5 text-xs font-sans rounded-t transition mb-0 ${
                activeTab === tab
                  ? 'bg-fantasy-dark text-amber-400 border border-slate-600 border-b-fantasy-dark -mb-px'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1">
          {content[activeTab]}
        </div>
      </div>
    </div>
  );
}
